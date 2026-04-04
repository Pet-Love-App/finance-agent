from __future__ import annotations

from typing import Dict

from agent.core.event_bus import EventBus


class WindowManager:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._windows: Dict[str, bool] = {"pet": True, "panel": False}

    def show(self, name: str) -> None:
        self._windows[name] = True
        self.event_bus.publish("window_changed", {"window": name, "visible": True})

    def hide(self, name: str) -> None:
        self._windows[name] = False
        self.event_bus.publish("window_changed", {"window": name, "visible": False})

    def open_panel(self, page: str) -> None:
        self._windows["panel"] = True
        self.event_bus.publish("open_panel", {"page": page})
