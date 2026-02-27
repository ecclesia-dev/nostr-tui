"""Textual widget: compose panel for writing and posting notes."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Input, Static


class ComposeWidget(Widget):
    """Compose panel with text input, image attach, and post button."""

    DEFAULT_CSS = """
    ComposeWidget {
        height: auto;
        max-height: 10;
        padding: 1 2;
        background: $surface;
        border: solid $primary-background;
    }
    ComposeWidget #compose-input {
        width: 1fr;
    }
    ComposeWidget #compose-buttons {
        height: 3;
        align: right middle;
    }
    ComposeWidget Button {
        margin: 0 1;
    }
    """

    class PostRequested(Message):
        """Fired when the user wants to publish a note."""
        def __init__(self, content: str, image_path: str | None = None) -> None:
            super().__init__()
            self.content = content
            self.image_path = image_path

    class ImageAttachRequested(Message):
        """Fired when the user wants to attach an image."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._image_path: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("[bold]Compose Note[/bold]", markup=True)
        yield Input(placeholder="What's on your mind?", id="compose-input")
        with Horizontal(id="compose-buttons"):
            yield Button("📎 Image", id="btn-image", variant="default")
            yield Button("Post", id="btn-post", variant="primary")
        yield Static("", id="compose-status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-post":
            self._do_post()
        elif event.button.id == "btn-image":
            self.post_message(self.ImageAttachRequested())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_post()

    def _do_post(self) -> None:
        input_widget = self.query_one("#compose-input", Input)
        content = input_widget.value.strip()
        if not content:
            return
        self.post_message(self.PostRequested(content, self._image_path))
        input_widget.value = ""
        self._image_path = None
        self._update_status("")

    def set_image_path(self, path: str) -> None:
        """Set an attached image path and show status."""
        self._image_path = path
        self._update_status(f"📎 {path}")

    def _update_status(self, text: str) -> None:
        status = self.query_one("#compose-status", Static)
        status.update(text)
