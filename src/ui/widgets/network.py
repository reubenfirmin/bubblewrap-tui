"""Network filtering widgets: PastaStatus, FilterModeRadio, FilterList, PortList."""

from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Button, Input, Label, Static


class PastaStatus(Container):
    """Shows pasta installation status and install command if missing."""

    def __init__(self) -> None:
        super().__init__()
        self._installed = False
        self._message = ""

    def compose(self) -> ComposeResult:
        from net import get_pasta_status

        self._installed, self._message = get_pasta_status()
        if self._installed:
            yield Static("pasta: [green]installed[/green]", id="pasta-status")
        else:
            yield Static(
                f"pasta: [red]not found[/red] - {self._message}",
                id="pasta-status",
            )

    @property
    def is_installed(self) -> bool:
        return self._installed


class FilterModeRadio(Container):
    """Radio button group for Off/Whitelist/Blacklist filter mode."""

    def __init__(
        self,
        mode: str = "off",
        on_change: Callable | None = None,
        radio_id: str = "",
    ) -> None:
        super().__init__()
        self._mode = mode
        self._on_change = on_change
        self._radio_id = radio_id

    def compose(self) -> ComposeResult:
        from textual.widgets import RadioButton, RadioSet

        with RadioSet(id=self._radio_id):
            yield RadioButton("Off", value=(self._mode == "off"))
            yield RadioButton("Whitelist", value=(self._mode == "whitelist"))
            yield RadioButton("Blacklist", value=(self._mode == "blacklist"))

    def on_radio_set_changed(self, event) -> None:
        """Handle radio selection change."""
        modes = ["off", "whitelist", "blacklist"]
        if event.pressed:
            self._mode = modes[event.radio_set.pressed_index]
            if self._on_change:
                self._on_change(self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Set the mode programmatically."""
        from textual.widgets import RadioSet

        self._mode = mode
        modes = ["off", "whitelist", "blacklist"]
        if mode in modes:
            idx = modes.index(mode)
            try:
                radio_set = self.query_one(RadioSet)
                radio_set.pressed_index = idx
            except Exception:
                pass


class FilterListItem(Container):
    """A single item in a filter list (hostname or CIDR)."""

    def __init__(self, value: str, on_remove: Callable) -> None:
        super().__init__()
        self.value = value
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        yield Label(self.value, classes="filter-item-label")
        yield Button("x", classes="filter-remove-btn", variant="error")

    @on(Button.Pressed, ".filter-remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)


class FilterList(Container):
    """A list of filter items with add/remove functionality."""

    def __init__(
        self,
        items: list[str],
        on_add: Callable,
        on_remove: Callable,
        placeholder: str = "Enter value...",
        list_id: str = "",
        input_id: str = "",
        add_btn_id: str = "",
        validate_fn: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__()
        self._items = items
        self._on_add = on_add
        self._on_remove = on_remove
        self._placeholder = placeholder
        self._list_id = list_id
        self._input_id = input_id
        self._add_btn_id = add_btn_id
        self._validate_fn = validate_fn

    def compose(self) -> ComposeResult:
        with VerticalScroll(id=self._list_id, classes="filter-list-scroll"):
            for item in self._items:
                yield FilterListItem(item, self._handle_remove)
        with Horizontal(classes="filter-add-row"):
            yield Input(placeholder=self._placeholder, id=self._input_id)
            yield Button("+", id=self._add_btn_id, variant="success")

    def _handle_remove(self, item: FilterListItem) -> None:
        """Handle item removal."""
        if item.value in self._items:
            self._items.remove(item.value)
        item.remove()
        self._on_remove(item.value)

    @on(Button.Pressed)
    def on_add_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == self._add_btn_id:
            event.stop()
            self._add_item()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == self._input_id:
            event.stop()
            self._add_item()

    def _add_item(self) -> None:
        """Add item from input field."""
        try:
            input_widget = self.query_one(f"#{self._input_id}", Input)
            value = input_widget.value.strip()
            if not value:
                return

            # Validate if function provided
            if self._validate_fn and not self._validate_fn(value):
                return

            # Avoid duplicates
            if value in self._items:
                input_widget.value = ""
                return

            self._items.append(value)
            input_widget.value = ""

            # Mount new item
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            list_scroll.mount(FilterListItem(value, self._handle_remove))

            self._on_add(value)
        except Exception:
            pass

    def refresh_items(self, items: list[str]) -> None:
        """Refresh the list with new items."""
        self._items = items
        try:
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            # Remove existing items
            for item in list(list_scroll.query(FilterListItem)):
                item.remove()
            # Add new items
            for value in items:
                list_scroll.mount(FilterListItem(value, self._handle_remove))
        except Exception:
            pass


class PortListItem(Container):
    """A single port item in the port list."""

    def __init__(self, port: int, on_remove: Callable) -> None:
        super().__init__()
        self.port = port
        self._on_remove = on_remove

    def compose(self) -> ComposeResult:
        yield Label(str(self.port), classes="filter-item-label")
        yield Button("x", classes="filter-remove-btn", variant="error")

    @on(Button.Pressed, ".filter-remove-btn")
    def on_remove_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self._on_remove(self)


class PortList(Container):
    """A list of port numbers with add/remove functionality."""

    def __init__(
        self,
        ports: list[int],
        on_add: Callable,
        on_remove: Callable,
        list_id: str = "",
        input_id: str = "",
        add_btn_id: str = "",
    ) -> None:
        super().__init__()
        self._ports = ports
        self._on_add = on_add
        self._on_remove = on_remove
        self._list_id = list_id
        self._input_id = input_id
        self._add_btn_id = add_btn_id

    def compose(self) -> ComposeResult:
        with VerticalScroll(id=self._list_id, classes="filter-list-scroll"):
            for port in self._ports:
                yield PortListItem(port, self._handle_remove)
        with Horizontal(classes="filter-add-row"):
            yield Input(placeholder="Port (1-65535)", id=self._input_id)
            yield Button("+", id=self._add_btn_id, variant="success")

    def _handle_remove(self, item: PortListItem) -> None:
        """Handle port removal."""
        if item.port in self._ports:
            self._ports.remove(item.port)
        item.remove()
        self._on_remove(item.port)

    @on(Button.Pressed)
    def on_add_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == self._add_btn_id:
            event.stop()
            self._add_port()

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == self._input_id:
            event.stop()
            self._add_port()

    def _add_port(self) -> None:
        """Add port from input field."""
        from net import validate_port

        try:
            input_widget = self.query_one(f"#{self._input_id}", Input)
            value = input_widget.value.strip()
            if not value:
                return

            # Validate port
            if not validate_port(value):
                return

            port = int(value)

            # Avoid duplicates
            if port in self._ports:
                input_widget.value = ""
                return

            self._ports.append(port)
            input_widget.value = ""

            # Mount new item
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            list_scroll.mount(PortListItem(port, self._handle_remove))

            self._on_add(port)
        except Exception:
            pass

    def refresh_ports(self, ports: list[int]) -> None:
        """Refresh the list with new ports."""
        self._ports = ports
        try:
            list_scroll = self.query_one(f"#{self._list_id}", VerticalScroll)
            # Remove existing items
            for item in list(list_scroll.query(PortListItem)):
                item.remove()
            # Add new items
            for port in ports:
                list_scroll.mount(PortListItem(port, self._handle_remove))
        except Exception:
            pass
