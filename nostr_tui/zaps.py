"""NIP-57 zap support — build zap requests and resolve LNURL."""

from __future__ import annotations

import json

import requests

from nostr_tui.events import NostrEvent, sign_event


def build_zap_request(
    recipient_pubkey: str,
    amount_msat: int,
    relays: list[str],
    privkey_bytes: bytes,
) -> dict:
    """Build a signed NIP-57 zap request event (kind 9734).

    Args:
        recipient_pubkey: Hex pubkey of the zap recipient.
        amount_msat: Amount in millisatoshis.
        relays: List of relay URLs to include.
        privkey_bytes: 32-byte private key for signing.

    Returns:
        Signed event as a dict ready for JSON serialization.
    """
    tags = [
        ["relays", *relays],
        ["amount", str(amount_msat)],
        ["p", recipient_pubkey],
    ]

    event = NostrEvent(kind=9734, content="", tags=tags)
    signed = sign_event(event, privkey_bytes)

    return {
        "id": signed.id,
        "pubkey": signed.pubkey,
        "created_at": signed.created_at,
        "kind": signed.kind,
        "tags": signed.tags,
        "content": signed.content,
        "sig": signed.sig,
    }


def fetch_lnurl(pubkey: str, relays: list[str] | None = None) -> str:
    """Fetch the LNURL / Lightning address for a pubkey.

    Tries to resolve via NIP-05 style or well-known lud16 from
    the user's kind:0 metadata.

    Args:
        pubkey: Hex pubkey to look up.
        relays: Optional relay URLs to query (uses public relay if empty).

    Returns:
        LNURL or lightning address string.

    Raises:
        RuntimeError: If lookup fails.
    """
    # Query a relay for kind:0 metadata
    query_relays = relays or ["wss://relay.damus.io"]
    import websockets.sync.client as ws_sync

    for relay_url in query_relays:
        try:
            with ws_sync.connect(relay_url, close_timeout=5) as ws:
                req = json.dumps([
                    "REQ", "lnurl-lookup",
                    {"kinds": [0], "authors": [pubkey], "limit": 1},
                ])
                ws.send(req)

                # Read up to 10 messages looking for EVENT
                for _ in range(10):
                    raw = ws.recv(timeout=5)
                    msg = json.loads(raw)
                    if isinstance(msg, list) and msg[0] == "EVENT" and len(msg) >= 3:
                        metadata = json.loads(msg[2].get("content", "{}"))
                        # Check lud16 (lightning address) first, then lud06 (LNURL)
                        if lud16 := metadata.get("lud16"):
                            return lud16
                        if lud06 := metadata.get("lud06"):
                            return lud06
                    elif isinstance(msg, list) and msg[0] == "EOSE":
                        break
        except Exception:
            continue

    raise RuntimeError(f"Could not resolve LNURL for pubkey {pubkey[:16]}...")
