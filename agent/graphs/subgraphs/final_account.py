from __future__ import annotations

from agent.graphs.policy import get_bool_policy
from agent.graphs.state import AppState
from agent.tools import aggregate_records, data_clean, generate_final_account, load_records


def final_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "final_start", "tool_name": "start"}]}


def route_after_load_records(state: AppState) -> str:
    payload = state.get("payload", {})
    records = state.get("records", [])
    generate_when_empty = get_bool_policy(payload, "final_generate_when_empty", True)
    if records:
        return "DataCleanNode"
    return "FinalGenerateNode" if generate_when_empty else "DataCleanNode"


def route_after_data_clean(state: AppState) -> str:
    payload = state.get("payload", {})
    records = state.get("records", [])
    generate_when_empty = get_bool_policy(payload, "final_generate_when_empty", True)
    if records:
        return "DataAggregateNode"
    return "FinalGenerateNode" if generate_when_empty else "DataAggregateNode"


def load_records_node(state: AppState) -> AppState:
    res = load_records(state.get("payload", {}).get("filters", {}), state.get("payload", {}).get("db_path"))
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


def final_generate_node(state: AppState) -> AppState:
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
