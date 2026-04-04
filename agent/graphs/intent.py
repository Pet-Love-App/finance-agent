from __future__ import annotations

from typing import Any, Dict

from agent.graphs.state import AppState


TASK_QA = "qa"
TASK_REIMBURSE = "reimburse"
TASK_FINAL = "final_account"
TASK_BUDGET = "budget"


def intent_node(state: AppState) -> AppState:
    payload: Dict[str, Any] = state.get("payload", {})
    task_type = str(state.get("task_type", "")).strip().lower()
    if task_type:
        return {
            "task_type": task_type,
            "task_progress": state.get("task_progress", [])
            + [{"step": "intent", "tool_name": "intent_detect", "task_type": task_type}],
        }

    query = str(payload.get("query", ""))
    if any(key in query for key in ["预算", "budget"]):
        inferred = TASK_BUDGET
    elif any(key in query for key in ["决算", "汇总", "年度"]):
        inferred = TASK_FINAL
    elif any(key in query for key in ["报销", "发票", "附件", "规则"]):
        inferred = TASK_QA
    else:
        inferred = TASK_REIMBURSE

    return {
        "task_type": inferred,
        "task_progress": state.get("task_progress", [])
        + [{"step": "intent", "tool_name": "intent_detect", "task_type": inferred}],
    }


def route_by_task(state: AppState) -> str:
    task_type = str(state.get("task_type", TASK_REIMBURSE))
    if task_type == TASK_QA:
        return "QAStartNode"
    if task_type == TASK_FINAL:
        return "FinalStartNode"
    if task_type == TASK_BUDGET:
        return "BudgetStartNode"
    return "ReimburseStartNode"
