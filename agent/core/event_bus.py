from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, List


EventHandler = Callable[[Dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    def publish(self, event_name: str, payload: Dict[str, Any]) -> None:
        for handler in self._handlers.get(event_name, []):
            handler(payload)
