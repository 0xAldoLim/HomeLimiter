"""Small terminal helpers shared by device, policy and setup dialogs."""

import unicodedata

from pydantic import ValidationError
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button as TextualButton
from textual.widgets import Static


class Button(TextualButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_effect_duration = 0


def clean(value) -> str:
    """Display external text literally, without terminal controls or bidi overrides."""
    return "".join(c for c in str(value) if unicodedata.category(c) not in {"Cc", "Cf", "Cs"})


def cell(value) -> Text:
    return Text(clean(value))


def error_message(exc) -> str:
    if isinstance(exc, ValidationError):
        item = exc.errors(include_input=False, include_url=False)[0]
        location = " / ".join(str(part).replace("_", " ") for part in item["loc"])
        return clean(f"{location}: {item['msg']}" if location else item["msg"])
    if isinstance(exc, KeyError):
        return "That device or policy is no longer available. Refresh and try again."
    return clean(exc)


class Dialog(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Back")]

    def error(self, message):
        self.query_one("#dialog-error", Static).update(message)
        self.notify(message, severity="error", timeout=6)

    @on(Button.Pressed, "#cancel")
    def cancel(self):
        self.dismiss()


class Confirm(Dialog):
    def __init__(self, title: str, description: str, verb="Confirm"):
        super().__init__()
        self.prompt_title = title
        self.description = description
        self.verb = verb

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Static(self.prompt_title, classes="heading", markup=False)
            yield Static(self.description, markup=False)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel", compact=True)
                yield Button(self.verb, id="confirm", variant="warning", compact=True)

    def on_mount(self):
        self.query_one("#cancel").focus()

    @on(Button.Pressed, "#confirm")
    def confirm(self):
        self.dismiss(True)
