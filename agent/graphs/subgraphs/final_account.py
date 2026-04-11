from __future__ import annotations

from agent.graphs.policy import get_bool_policy
from agent.graphs.state import AppState
from agent.graphs.subgraphs.recon import (
    recon_compare_node,
    recon_compliance_node,
    recon_generate_node,
    recon_load_node,
    recon_material_node,
    recon_normalize_node,
    recon_suggest_node,
)
from agent.tools import aggregate_records, data_clean, generate_final_account, load_records


def final_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "final_start", "tool_name": "start"}]}


def route_after_load_records(state: AppState) -> str:
    payload = state.get("payload", {})
    records = state.get("records", [])
    if state.get("errors") and not records:
        return "FinalFailNode"
    generate_when_empty = get_bool_policy(payload, "final_generate_when_empty", True)
    if records:
        return "DataCleanNode"
    return "FinalGenerateNode" if generate_when_empty else "DataCleanNode"


def route_after_data_clean(state: AppState) -> str:
    payload = state.get("payload", {})
    records = state.get("records", [])
    if state.get("errors") and not records:
        return "FinalFailNode"
    generate_when_empty = get_bool_policy(payload, "final_generate_when_empty", True)
    if records:
        return "DataAggregateNode"
    return "FinalGenerateNode" if generate_when_empty else "DataAggregateNode"


def load_records_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    filters = payload.get("filters", {}) if isinstance(payload.get("filters", {}), dict) else {}
    session_id = str(payload.get("chat_session_id", "")).strip()
    if session_id and not str(filters.get("session_id", filters.get("chat_session_id", "")) or "").strip():
        filters = {**filters, "session_id": session_id}
    res = load_records(filters, payload.get("db_path"))
    return {
        "records": res.data.get("records", []),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "load_records", "tool_name": "load_records"}],
    }


def data_clean_node(state: AppState) -> AppState:
    res = data_clean(state.get("records", []))
    return {
        "records": res.data.get("cleaned", []),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "data_clean", "tool_name": "data_clean"}],
    }


def aggregate_node(state: AppState) -> AppState:
    res = aggregate_records(state.get("records", []))
    return {
        "aggregate": res.data.get("aggregate", {}),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "aggregate", "tool_name": "aggregate_records"}],
    }


def _run_recon_compat_chain(state: AppState) -> AppState:
    # Backward-compatible path: some old calls still route recon to final_generate_node.
    current = dict(state)
    for node in (
        recon_load_node,
        recon_normalize_node,
        recon_compare_node,
        recon_compliance_node,
        recon_suggest_node,
        recon_material_node,
    ):
        update = node(current)
        current = {**current, **update}
    return recon_generate_node(current)


def final_generate_node(state: AppState) -> AppState:
    route_decision = state.get("route_decision", {}) if isinstance(state.get("route_decision", {}), dict) else {}
    route_task_type = str(route_decision.get("task_type", "")).strip().lower()
    if route_task_type == "recon":
        return _run_recon_compat_chain(state)

    aggregate = state.get("aggregate", {"total_amount": 0.0, "count": 0, "by_month": []})
    res = generate_final_account(aggregate, state.get("payload", {}).get("output_dir"))
    errors = state.get("errors", []) + ([res.error] if res.error else [])
    return {
        "outputs": {**state.get("outputs", {}), "final_account_path": res.data.get("final_account_path", "")},
        "result": {
            "type": "final_account",
            "aggregate": aggregate,
            "final_account_path": res.data.get("final_account_path", ""),
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "final_generate", "tool_name": "generate_final_account"}],
    }


def final_fail_node(state: AppState) -> AppState:
    errors = state.get("errors", [])
    return {
        "result": {
            "type": "final_account",
            "status": "failed",
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "final_fail", "tool_name": "fail_fast_guard"}],
    }
