from __future__ import annotations

from typing import Any, Dict, Optional

from agent.core.event_bus import EventBus
from agent.graphs.main_graph import build_main_graph
from agent.graphs.state import AppState


class TaskDispatcher:
    def __init__(self, event_bus: EventBus, graph: Optional[Any] = None) -> None:
        self.event_bus = event_bus
        self.graph = graph or build_main_graph()

    def dispatch(self, task_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.event_bus.publish("task_start", {"task_type": task_type})
        initial_state: AppState = {
            "task_type": task_type,
            "payload": payload,
            "task_progress": [],
            "outputs": {},
            "errors": [],
            "result": {},
        }
        try:
            final_state = self.graph.invoke(initial_state)
            for step in final_state.get("task_progress", []):
                self.event_bus.publish("task_progress", step)
            result = final_state.get("result", {})
            self.event_bus.publish("task_done", {"task_type": task_type, "result": result})
            return result
        except Exception as exc:
            self.event_bus.publish("task_error", {"task_type": task_type, "message": str(exc)})
            raise
