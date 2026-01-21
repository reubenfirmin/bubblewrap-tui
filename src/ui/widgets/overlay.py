"""Overlay configuration widget: OverlayItem."""

from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Static

from model import OverlayConfig


class OverlayItem(Container):
    """A row representing an overlay configuration.

    Modes:
        tmpfs: Empty writable directory (no source needed)
        overlay: Writable layer on existing dir, changes in RAM
        persistent: Writable layer on existing dir, changes saved to disk
    """

    # Mode cycle order and display properties
    MODES = ["tmpfs", "overlay", "persistent"]
    MODE_LABELS = {"tmpfs": "tmpfs", "overlay": "overlay", "persistent": "persist"}
    MODE_VARIANTS = {"tmpfs": "default", "overlay": "primary", "persistent": "warning"}

    def __init__(self, overlay: OverlayConfig, on_update: Callable, on_remove: Callable) -> None:
        super().__init__()
        self.overlay = overlay
        self._on_update = on_update
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        mode = self.overlay.mode
        with Horizontal(classes="overlay-row"):
            yield Button(self.MODE_LABELS.get(mode, mode),
                        classes="overlay-mode-btn",
                        variant=self.MODE_VARIANTS.get(mode, "default"))
            # Source: disabled for tmpfs (not needed), enabled for overlay/persistent
            yield Input(value=self.overlay.source,
                       placeholder="n/a" if mode == "tmpfs" else "Source dir",
                       classes="overlay-src-input",
                       disabled=(mode == "tmpfs"))
            yield Static("→", classes="overlay-arrow")
            yield Input(value=self.overlay.dest, placeholder="Mount point", classes="overlay-dest-input")
            # Write dir: only for persistent mode
            yield Input(
                value=self.overlay.write_dir if mode == "persistent" else "",
                placeholder="Write dir" if mode == "persistent" else "n/a",
                classes="overlay-write-input",
                disabled=(mode != "persistent")
            )
            yield Button("x", classes="overlay-remove-btn", variant="error")

    @on(Button.Pressed, ".overlay-mode-btn")
    def on_mode_toggle(self, event: Button.Pressed) -> None:
        event.stop()
        # Cycle to next mode
        current_idx = self.MODES.index(self.overlay.mode) if self.overlay.mode in self.MODES else 0
        next_idx = (current_idx + 1) % len(self.MODES)
        self.overlay.mode = self.MODES[next_idx]
        mode = self.overlay.mode

        # Update button
        btn = event.button
        btn.label = self.MODE_LABELS.get(mode, mode)
        btn.variant = self.MODE_VARIANTS.get(mode, "default")

        # Update source input (disabled for tmpfs)
        src_input = self.query_one(".overlay-src-input", Input)
        src_input.disabled = (mode == "tmpfs")
        src_input.placeholder = "n/a" if mode == "tmpfs" else "Source dir"
        if mode == "tmpfs":
            src_input.value = ""
            self.overlay.source = ""

        # Update write dir input (only for persistent)
        write_input = self.query_one(".overlay-write-input", Input)
        write_input.disabled = (mode != "persistent")
        write_input.placeholder = "Write dir" if mode == "persistent" else "n/a"
        if mode != "persistent":
            write_input.value = ""
            self.overlay.write_dir = ""

        self._on_update()

    @on(Input.Changed, ".overlay-src-input")
    def on_src_changed(self, event: Input.Changed) -> None:
        old_source = self.overlay.source
        self.overlay.source = event.value
        # Auto-sync dest if it matches source (user hasn't customized it)
        dest_input = self.query_one(".overlay-dest-input", Input)
        if not dest_input.value or dest_input.value == old_source:
            dest_input.value = event.value
            self.overlay.dest = event.value
        self._on_update()

    @on(Input.Changed, ".overlay-dest-input")
    def on_dest_changed(self, event: Input.Changed) -> None:
        self.overlay.dest = event.value
        self._on_update()

    @on(Input.Changed, ".overlay-write-input")
    def on_write_changed(self, event: Input.Changed) -> None:
        self.overlay.write_dir = event.value
        self._on_update()

    @on(Button.Pressed, ".overlay-remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)
