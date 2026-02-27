"""Main Textual App for nostr-tui."""

from __future__ import annotations

import asyncio
import json
import logging

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from nostr_tui.compose import ComposeWidget
from nostr_tui.config import load_config
from nostr_tui.events import (
    event_to_json,
    make_text_note,
    nsec_to_privkey_bytes,
    verify_event,
)
from nostr_tui.feed import FeedWidget, NoteWidget
from nostr_tui.images import upload_image_nip96
from nostr_tui.relay import RelayPool
from nostr_tui.zaps import build_zap_request, fetch_lnurl

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------


class ImagePathModal(ModalScreen):
    """Overlay prompt for entering a local image file path."""

    DEFAULT_CSS = """
    ImagePathModal {
        align: center middle;
    }
    ImagePathModal #im-dialog {
        width: 64;
        height: auto;
        padding: 2 4;
        background: $surface;
        border: tall $primary;
    }
    ImagePathModal Label {
        margin-bottom: 1;
    }
    ImagePathModal #im-buttons {
        margin-top: 1;
        align: right middle;
        height: auto;
    }
    """

    BINDINGS = [("escape", "dismiss_cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="im-dialog"):
            yield Label("📎 Attach Image")
            yield Label("Enter the local file path to your image:")
            yield Input(placeholder="/path/to/image.jpg", id="im-path-input")
            with Horizontal(id="im-buttons"):
                yield Button("Cancel", id="im-cancel", variant="default")
                yield Button("Attach", id="im-attach", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#im-path-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "im-cancel":
            self.dismiss(None)
        elif event.button.id == "im-attach":
            path = self.query_one("#im-path-input", Input).value.strip()
            self.dismiss(path or None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip()
        self.dismiss(path or None)

    def action_dismiss_cancel(self) -> None:
        self.dismiss(None)


class ZapModal(ModalScreen):
    """Overlay prompt for sending a zap (NIP-57)."""

    DEFAULT_CSS = """
    ZapModal {
        align: center middle;
    }
    ZapModal #zap-dialog {
        width: 64;
        height: auto;
        padding: 2 4;
        background: $surface;
        border: tall $primary;
    }
    ZapModal Label {
        margin-bottom: 1;
    }
    ZapModal Input {
        margin-bottom: 1;
    }
    ZapModal #zap-buttons {
        margin-top: 1;
        align: right middle;
        height: auto;
    }
    """

    BINDINGS = [("escape", "dismiss_cancel", "Cancel")]

    def __init__(self, pubkey: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_pubkey = pubkey

    def compose(self) -> ComposeResult:
        with Vertical(id="zap-dialog"):
            yield Label("⚡ Send Zap")
            yield Label("Recipient pubkey (hex):")
            yield Input(
                value=self._initial_pubkey,
                placeholder="hex pubkey of recipient",
                id="zap-pubkey",
            )
            yield Label("Amount (sats):")
            yield Input(placeholder="21", id="zap-amount")
            with Horizontal(id="zap-buttons"):
                yield Button("Cancel", id="zap-cancel", variant="default")
                yield Button("⚡ Zap", id="zap-send", variant="primary")

    def on_mount(self) -> None:
        # Pre-focus amount if pubkey already filled
        target = "#zap-amount" if self._initial_pubkey else "#zap-pubkey"
        self.query_one(target, Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "zap-cancel":
            self.dismiss(None)
        elif event.button.id == "zap-send":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Tab from pubkey to amount; submit from amount
        if event.input.id == "zap-pubkey":
            self.query_one("#zap-amount", Input).focus()
        else:
            self._submit()

    def _submit(self) -> None:
        pubkey = self.query_one("#zap-pubkey", Input).value.strip()
        raw_amount = self.query_one("#zap-amount", Input).value.strip()
        try:
            sats = int(raw_amount or "0")
        except ValueError:
            sats = 0
        if pubkey and sats > 0:
            self.dismiss((pubkey, sats))
        else:
            self.notify("Enter a valid pubkey and amount > 0", severity="warning")

    def action_dismiss_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


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
        Binding("i", "attach_image", "Attach Image"),
        Binding("z", "zap_note", "Zap"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = load_config()
        self._privkey_bytes: bytes | None = None
        self._pool: RelayPool | None = None
        self._selected_note_pubkey: str | None = None

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
                if not verify_event(event):
                    self.log.warning(
                        "Dropped event with invalid signature: id=%s",
                        event.get("id", "<unknown>"),
                    )
                    return
                feed = self.query_one("#feed", FeedWidget)
                feed.add_note(event)

    # ------------------------------------------------------------------
    # Post handler
    # ------------------------------------------------------------------

    async def on_compose_widget_post_requested(
        self, event: ComposeWidget.PostRequested
    ) -> None:
        """Handle a post request from the compose widget."""
        if not self._privkey_bytes:
            self.notify("No private key configured (set nsec in config)", severity="error")
            return
        if not self._pool:
            self.notify("Not connected to any relay", severity="error")
            return

        content = event.content

        # If image was attached, upload first and append URL
        if event.image_path:
            try:
                self.notify("Uploading image...")
                url = await asyncio.to_thread(
                    upload_image_nip96,
                    event.image_path,
                    self.config.upload.server,
                )
                content = f"{content}\n{url}"
                self.notify("Image uploaded")
            except Exception as e:
                self.notify(f"Image upload failed: {e}", severity="error")

        note = make_text_note(content, self._privkey_bytes)
        event_json = event_to_json(note)
        await self._pool.publish(event_json)
        self.notify("Note posted!")

        # Optimistically add to local feed
        feed = self.query_one("#feed", FeedWidget)
        feed.add_note({
            "id": note.id,
            "pubkey": note.pubkey,
            "created_at": note.created_at,
            "kind": note.kind,
            "tags": note.tags,
            "content": note.content,
        })

    # ------------------------------------------------------------------
    # Image attach — Fix 2: modal wired to ComposeWidget.set_image_path
    # ------------------------------------------------------------------

    async def on_compose_widget_image_attach_requested(
        self, event: ComposeWidget.ImageAttachRequested
    ) -> None:
        """Show image path modal and pass result to compose widget."""
        path: str | None = await self.push_screen_wait(ImagePathModal())
        if path:
            self.query_one(ComposeWidget).set_image_path(path)

    # ------------------------------------------------------------------
    # Note selection — tracks clicked note for zap targeting
    # ------------------------------------------------------------------

    def on_note_widget_note_selected(self, event: NoteWidget.NoteSelected) -> None:
        """Track which note was last clicked (used to pre-fill zap pubkey)."""
        self._selected_note_pubkey = event.note_event.get("pubkey", "")
        pubkey_short = self._selected_note_pubkey[:12] if self._selected_note_pubkey else "?"
        self.notify(f"Note selected: {pubkey_short}…  (press z to zap)", timeout=2)

    # ------------------------------------------------------------------
    # App-level actions
    # ------------------------------------------------------------------

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
            self.notify("Refreshing feed…")

    async def action_attach_image(self) -> None:
        """Open image path modal (app-level shortcut, mirrors compose button)."""
        path: str | None = await self.push_screen_wait(ImagePathModal())
        if path:
            self.query_one(ComposeWidget).set_image_path(path)

    async def action_zap_note(self) -> None:
        """Open zap modal. Pre-fills pubkey if a note has been clicked."""
        if not self._privkey_bytes:
            self.notify("No private key configured (set nsec in config)", severity="error")
            return
        if not self._pool:
            self.notify("Not connected to any relay", severity="error")
            return

        result = await self.push_screen_wait(
            ZapModal(pubkey=self._selected_note_pubkey or "")
        )
        if not result:
            return

        recipient_pubkey, sats = result
        amount_msat = sats * 1000

        self.notify(f"⚡ Looking up Lightning address for {recipient_pubkey[:12]}…")

        # Fix 4: fetch_lnurl is synchronous — run in thread pool
        try:
            lnurl = await asyncio.to_thread(
                fetch_lnurl, recipient_pubkey, self.config.relays or None
            )
        except RuntimeError as e:
            self.notify(f"Zap lookup failed: {e}", severity="error")
            return

        # Build and publish NIP-57 zap request (kind 9734)
        zap_req = build_zap_request(
            recipient_pubkey,
            amount_msat,
            self.config.relays,
            self._privkey_bytes,
        )
        zap_json = json.dumps(["EVENT", zap_req])
        await self._pool.publish(zap_json)

        self.notify(f"⚡ Zap request sent! Pay to: {lnurl}")

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
