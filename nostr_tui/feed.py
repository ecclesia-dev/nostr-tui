"""Textual widget: scrollable feed of Nostr notes."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

IMAGE_URL_RE = re.compile(
    r"https?://\S+\.(?:png|jpg|jpeg|gif|webp|bmp|svg)(?:\?\S*)?",
    re.IGNORECASE,
)


class NoteWidget(Static):
    """Renders a single Nostr note."""

    DEFAULT_CSS = """
    NoteWidget {
        padding: 1 2;
        margin: 0 0 1 0;
        background: $surface;
        border: solid $primary-background;
    }
    """

    class NoteSelected(Message):
        """Fired when a note is clicked. Bubbles to app for zap targeting."""

        def __init__(self, note_event: dict) -> None:
            super().__init__()
            self.note_event = note_event

    def __init__(self, event: dict, **kwargs) -> None:
        self.event = event
        super().__init__(**kwargs)

    def on_click(self) -> None:
        """Select this note (e.g. for zapping)."""
        self.post_message(self.NoteSelected(self.event))

    def compose(self) -> ComposeResult:
        pubkey = self.event.get("pubkey", "")[:12]
        ts = self.event.get("created_at", 0)
        time_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        content = self.event.get("content", "")

        # Count zap amounts from zap receipts if present
        zap_total = 0
        for tag in self.event.get("tags", []):
            if len(tag) >= 2 and tag[0] == "amount":
                try:
                    zap_total += int(tag[1])
                except ValueError:
                    pass

        # Build display text
        header = f"[bold]{pubkey}...[/bold]  [dim]{time_str}[/dim]"
        parts = [header, "", content]

        # Detect image URLs in content
        image_urls = IMAGE_URL_RE.findall(content)
        if image_urls:
            parts.append("")
            for url in image_urls[:3]:  # Limit to 3 images
                parts.append(f"  [dim][image: {url}][/dim]")

        if zap_total > 0:
            sats = zap_total // 1000
            parts.append(f"\n[yellow]⚡ {sats} sats[/yellow]")

        yield Static("\n".join(parts), markup=True)


class FeedWidget(Widget):
    """Scrollable feed of Nostr notes."""

    DEFAULT_CSS = """
    FeedWidget {
        height: 1fr;
    }
    """

    notes: reactive[list[dict]] = reactive(list, always_update=True)

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="feed-scroll")

    def watch_notes(self, notes: list[dict]) -> None:
        """Re-render when notes list changes."""
        scroll = self.query_one("#feed-scroll", VerticalScroll)
        scroll.remove_children()
        # Sort by created_at descending (newest first)
        sorted_notes = sorted(notes, key=lambda e: e.get("created_at", 0), reverse=True)
        for event in sorted_notes:
            scroll.mount(NoteWidget(event))

    def add_note(self, event: dict) -> None:
        """Append a note and trigger a re-render."""
        current = list(self.notes)
        # Deduplicate by event id
        if any(n.get("id") == event.get("id") for n in current):
            return
        current.append(event)
        self.notes = current
