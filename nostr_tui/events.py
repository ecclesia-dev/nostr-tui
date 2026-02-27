"""Nostr event creation, signing, and serialization (NIP-01)."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

import secp256k1
from bech32 import bech32_decode, convertbits


@dataclass
class NostrEvent:
    kind: int
    content: str
    tags: list[list[str]] = field(default_factory=list)
    created_at: int = 0
    pubkey: str = ""
    id: str = ""
    sig: str = ""


def nsec_to_privkey_bytes(nsec: str) -> bytes:
    """Decode a bech32-encoded nsec to raw 32-byte private key."""
    hrp, data = bech32_decode(nsec)
    if hrp != "nsec" or data is None:
        raise ValueError("Invalid nsec")
    raw = convertbits(data, 5, 8, False)
    if raw is None or len(raw) != 32:
        raise ValueError("Invalid nsec data length")
    return bytes(raw)


def privkey_to_pubkey_hex(privkey_bytes: bytes) -> str:
    """Derive the x-only public key hex from a private key."""
    pk = secp256k1.PrivateKey(privkey_bytes)
    # secp256k1 serialize returns 33-byte compressed; strip prefix for x-only
    pubkey_bytes = pk.pubkey.serialize(compressed=True)
    return pubkey_bytes[1:].hex()


def compute_event_id(event: NostrEvent) -> str:
    """Compute the NIP-01 event id (sha256 of serialized array)."""
    serialized = json.dumps(
        [0, event.pubkey, event.created_at, event.kind, event.tags, event.content],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sign_event(event: NostrEvent, privkey_bytes: bytes) -> NostrEvent:
    """Fill in pubkey, id, sig on an event and return it."""
    event.pubkey = privkey_to_pubkey_hex(privkey_bytes)
    if event.created_at == 0:
        event.created_at = int(time.time())
    event.id = compute_event_id(event)
    pk = secp256k1.PrivateKey(privkey_bytes)
    sig = pk.schnorr_sign(bytes.fromhex(event.id), bip340tag=None, raw=True)
    event.sig = sig.hex()
    return event


def event_to_json(event: NostrEvent) -> str:
    """Serialize a signed event to the JSON format relays expect."""
    return json.dumps(
        [
            "EVENT",
            {
                "id": event.id,
                "pubkey": event.pubkey,
                "created_at": event.created_at,
                "kind": event.kind,
                "tags": event.tags,
                "content": event.content,
                "sig": event.sig,
            },
        ],
        separators=(",", ":"),
        ensure_ascii=False,
    )


def make_text_note(content: str, privkey_bytes: bytes) -> NostrEvent:
    """Create and sign a kind:1 text note."""
    event = NostrEvent(kind=1, content=content)
    return sign_event(event, privkey_bytes)


def verify_event(event_dict: dict) -> bool:
    """Verify a NIP-01 event: recompute id and validate Schnorr signature.

    Returns True if the event id and signature are valid, False otherwise.
    """
    try:
        pubkey = event_dict["pubkey"]
        sig_hex = event_dict["sig"]
        event_id = event_dict["id"]

        # Step 1: recompute the event id
        serialized = json.dumps(
            [
                0,
                pubkey,
                event_dict["created_at"],
                event_dict["kind"],
                event_dict["tags"],
                event_dict["content"],
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        computed_id = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        # Step 2: id must match
        if computed_id != event_id:
            return False

        # Step 3: verify Schnorr signature (secp256k1 x-only pubkey — prepend 0x02)
        pub = secp256k1.PublicKey(bytes.fromhex("02" + pubkey), raw=True)
        sig_bytes = bytes.fromhex(sig_hex)
        return pub.schnorr_verify(bytes.fromhex(event_id), sig_bytes, raw=True)
    except Exception:
        return False


def make_reaction(event_id: str, event_pubkey: str, content: str, privkey_bytes: bytes) -> NostrEvent:
    """Create and sign a kind:7 reaction."""
    event = NostrEvent(
        kind=7,
        content=content,
        tags=[["e", event_id], ["p", event_pubkey]],
    )
    return sign_event(event, privkey_bytes)
