"""Main Textual App for nostr-tui."""

from __future__ import annotations

import asyncio
import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from nostr_tui.compose import ComposeWidget
from nostr_tui.config import load_config
from nostr_tui.events import (
    event_to_json,
    make_text_note,
    nsec_to_privkey_bytes,
)
from nostr_tui.feed import FeedWidget
from nostr_tui.images import upload_image_nip96
from nostr_tui.relay import RelayPool

log = logging.getLogger(__name__)


class NostrTuiApp(App):
    """A terminal UI client for the Nostr protocol."""

    TITLE = "nostr-tui"
    CSS = """
    Screen {
        layout: vertical;
    }
    #main-container {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "focus_compose", "New Note"),
        Binding("r", "refresh_feed", "Refresh"),
        Binding("i", "upload_image", "Upload Image"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self._privkey_bytes: bytes | None = None
        self._pool: RelayPool | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            yield FeedWidget(id="feed")
            yield ComposeWidget(id="compose")
        yield Footer()

    async def on_mount(self) -> None:
        """Load config, derive keys, connect to relays."""
        if self.config.nsec:
            try:
                self._privkey_bytes = nsec_to_privkey_bytes(self.config.nsec)
            except ValueError:
                self.notify("Invalid nsec in config", severity="error")

        if not self.config.relays:
            self.notify("No relays configured", severity="warning")
            return

        self._pool = RelayPool(self.config.relays)
        self._pool.on_event(self._on_relay_event)
        await self._pool.connect()

        # Wait briefly for a connection, then subscribe
        connected = await self._pool.wait_connected(timeout=5.0)
        if connected:
            await self._pool.subscribe({"kinds": [1], "limit": 50})
        else:
            self.notify("Could not connect to any relay", severity="warning")

    async def _on_relay_event(self, msg) -> None:
        """Handle incoming events from relays."""
        data = msg.data
        if not isinstance(data, list) or len(data) < 2:
            return
        msg_type = data[0]
        if msg_type == "EVENT" and len(data) >= 3:
            event = data[2]
            if isinstance(event, dict) and event.get("kind") == 1:
                feed = self.query_one("#feed", FeedWidget)
                feed.add_note(event)

    async def on_compose_widget_post_requested(self, event: ComposeWidget.PostRequested) -> None:
        """Handle a post request from the compose widget."""
        if not self._privkey_bytes:
            self.notify("No private key configured (set nsec in config)", severity="error")
            return
        if not self._pool:
            self.notify("Not connected to any relay", severity="error")
            return

        content = event.content

        # If image was attached, upload and append URL
        if event.image_path:
            try:
                self.notify("Uploading image...")
                url = await asyncio.to_thread(upload_image_nip96, event.image_path)
                content = f"{content}\n{url}"
                self.notify("Image uploaded")
            except Exception as e:
                self.notify(f"Image upload failed: {e} — post cancelled", severity="error")
                return

        note = make_text_note(content, self._privkey_bytes)
        event_json = event_to_json(note)
        await self._pool.publish(event_json)
        self.notify("Note posted!")

        # Add to local feed immediately
        feed = self.query_one("#feed", FeedWidget)
        feed.add_note({
            "id": note.id,
            "pubkey": note.pubkey,
            "created_at": note.created_at,
            "kind": note.kind,
            "tags": note.tags,
            "content": note.content,
        })

    async def on_compose_widget_image_attach_requested(
        self, event: ComposeWidget.ImageAttachRequested
    ) -> None:
        """Open a simple input for image path (file picker not available in TUI)."""
        self.query_one("#compose-input").focus()
        self.notify("Type image path and press 'i' to upload, or use the compose panel.")

    def action_focus_compose(self) -> None:
        """Focus the compose input."""
        try:
            self.query_one("#compose-input").focus()
        except Exception:
            pass

    async def action_refresh_feed(self) -> None:
        """Re-subscribe to get fresh notes."""
        if self._pool:
            await self._pool.subscribe({"kinds": [1], "limit": 50})
            self.notify("Refreshing feed...")

    async def action_upload_image(self) -> None:
        """Prompt-style image upload via notification."""
        self.notify("Attach image: enter path in compose, or use '📎 Image' button")

    async def on_unmount(self) -> None:
        if self._pool:
            await self._pool.close()


def main() -> None:
    """CLI entrypoint."""
    logging.basicConfig(level=logging.WARNING)
    app = NostrTuiApp()
    app.run()


if __name__ == "__main__":
    main()
