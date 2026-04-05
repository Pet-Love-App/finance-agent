from __future__ import annotations

from typing import Any, Dict, Optional

from agent.config import get_graph_policy_defaults
from agent.core.event_bus import EventBus
from agent.graphs.state import AppState


def _merge_graph_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    defaults = get_graph_policy_defaults()
    user_policy = payload.get("graph_policy", {})
    if not isinstance(user_policy, dict):
        user_policy = {}
    merged_policy = {**defaults, **user_policy}
    return {**payload, "graph_policy": merged_policy}


class TaskDispatcher:
    def __init__(self, event_bus: EventBus, graph: Optional[Any] = None) -> None:
        self.event_bus = event_bus
        if graph is not None:
            self.graph = graph
        else:
            from agent.graphs.main_graph import build_main_graph

            self.graph = build_main_graph()

    def dispatch(self, task_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self.event_bus.publish("task_start", {"task_type": task_type})
        merged_payload = _merge_graph_policy(payload if isinstance(payload, dict) else {})
        initial_state: AppState = {
            "task_type": task_type,
            "payload": merged_payload,
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
            if final_state.get("errors"):
                result = {**result, "errors": final_state.get("errors", [])}
            self.event_bus.publish("task_done", {"task_type": task_type, "result": result})
            return result
        except Exception as exc:
            self.event_bus.publish("task_error", {"task_type": task_type, "message": str(exc)})
            raise
