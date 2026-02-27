"""Config loader — reads ~/.config/nostr-tui/config.toml."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "nostr-tui"
CONFIG_PATH = CONFIG_DIR / "config.toml"

_DEFAULT_UPLOAD_SERVER = "https://nostr.build/api/v2/upload/files"


@dataclass
class DisplayConfig:
    image_protocol: str = "sixel"
    max_image_height: int = 20


@dataclass
class UploadConfig:
    server: str = _DEFAULT_UPLOAD_SERVER


@dataclass
class AppConfig:
    nsec: str = ""
    relays: list[str] = field(default_factory=list)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    upload: UploadConfig = field(default_factory=UploadConfig)


def load_config() -> AppConfig:
    """Load config from disk. Exits with message if file is missing."""
    if not CONFIG_PATH.exists():
        # F-7: create config dir with restricted permissions if needed
        CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        print(f"Config not found at {CONFIG_PATH}")
        print(f"Copy config.example.toml to {CONFIG_PATH} and fill in your nsec.")
        sys.exit(1)

    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    # F-7: warn if config file is readable/writable by group or other
    mode = CONFIG_PATH.stat().st_mode
    if mode & 0o077:
        print(
            f"WARNING: {CONFIG_PATH} has insecure permissions "
            f"({oct(mode & 0o777)}). Run: chmod 600 {CONFIG_PATH}",
            file=sys.stderr,
        )

    nostr = raw.get("nostr", {})
    display_raw = raw.get("display", {})
    upload_raw = raw.get("upload", {})

    # F-2: validate relay URLs — only wss:// is acceptable
    raw_relays: list[str] = nostr.get("relays", [])
    safe_relays: list[str] = []
    for url in raw_relays:
        if not url.startswith("wss://"):
            print(
                f"WARNING: relay URL rejected (must start with wss://): {url!r}",
                file=sys.stderr,
            )
        else:
            safe_relays.append(url)

    display = DisplayConfig(
        image_protocol=display_raw.get("image_protocol", "sixel"),
        max_image_height=display_raw.get("max_image_height", 20),
    )

    # F-5: validate upload server — must be https://
    upload_server = upload_raw.get("server", _DEFAULT_UPLOAD_SERVER)
    if not upload_server.startswith("https://"):
        print(
            f"WARNING: upload.server must start with https://; "
            f"got {upload_server!r}. Falling back to default.",
            file=sys.stderr,
        )
        upload_server = _DEFAULT_UPLOAD_SERVER

    upload = UploadConfig(server=upload_server)

    return AppConfig(
        nsec=nostr.get("nsec", ""),
        relays=safe_relays,
        display=display,
        upload=upload,
    )
