from __future__ import annotations

from agent.graphs.state import AppState
from agent.tools import aggregate_records, data_clean, generate_final_account, load_records


def final_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "final_start", "tool_name": "start"}]}


def load_records_node(state: AppState) -> AppState:
    res = load_records(state.get("payload", {}).get("filters", {}), state.get("payload", {}).get("db_path"))
    return {
        "records": res.data.get("records", []),
        "task_progress": state.get("task_progress", []) + [{"step": "load_records", "tool_name": "load_records"}],
    }


def data_clean_node(state: AppState) -> AppState:
    res = data_clean(state.get("records", []))
    return {
        "records": res.data.get("cleaned", []),
        "task_progress": state.get("task_progress", []) + [{"step": "data_clean", "tool_name": "data_clean"}],
    }


def aggregate_node(state: AppState) -> AppState:
    res = aggregate_records(state.get("records", []))
    return {
        "aggregate": res.data.get("aggregate", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "aggregate", "tool_name": "aggregate_records"}],
    }


def final_generate_node(state: AppState) -> AppState:
    res = generate_final_account(state.get("aggregate", {}), state.get("payload", {}).get("output_dir"))
    return {
        "outputs": {**state.get("outputs", {}), "final_account_path": res.data.get("final_account_path", "")},
        "result": {
            "type": "final_account",
            "aggregate": state.get("aggregate", {}),
            "final_account_path": res.data.get("final_account_path", ""),
        },
        "task_progress": state.get("task_progress", []) + [{"step": "final_generate", "tool_name": "generate_final_account"}],
    }
