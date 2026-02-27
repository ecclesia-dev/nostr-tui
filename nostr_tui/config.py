"""Config loader — reads ~/.config/nostr-tui/config.toml."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "nostr-tui"
CONFIG_PATH = CONFIG_DIR / "config.toml"


@dataclass
class DisplayConfig:
    image_protocol: str = "sixel"
    max_image_height: int = 20


@dataclass
class AppConfig:
    nsec: str = ""
    relays: list[str] = field(default_factory=list)
    display: DisplayConfig = field(default_factory=DisplayConfig)


def load_config() -> AppConfig:
    """Load config from disk. Exits with message if file is missing."""
    if not CONFIG_PATH.exists():
        print(f"Config not found at {CONFIG_PATH}")
        print(f"Copy config.example.toml to {CONFIG_PATH} and fill in your nsec.")
        sys.exit(1)

    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)

    nostr = raw.get("nostr", {})
    display_raw = raw.get("display", {})

    display = DisplayConfig(
        image_protocol=display_raw.get("image_protocol", "sixel"),
        max_image_height=display_raw.get("max_image_height", 20),
    )

    return AppConfig(
        nsec=nostr.get("nsec", ""),
        relays=nostr.get("relays", []),
        display=display,
    )
