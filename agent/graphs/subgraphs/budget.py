from __future__ import annotations

from agent.graphs.state import AppState
from agent.tools import budget_calculate, generate_budget, generate_report, load_final_data


def budget_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "budget_start", "tool_name": "start"}]}


def load_final_data_node(state: AppState) -> AppState:
    res = load_final_data(state.get("payload", {}))
    return {
        "aggregate": res.data.get("final_data", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "load_final_data", "tool_name": "load_final_data"}],
    }


def budget_calculate_node(state: AppState) -> AppState:
    strategy = state.get("payload", {}).get("strategy", {})
    res = budget_calculate(state.get("aggregate", {}), strategy)
    return {
        "budget": res.data.get("budget", {}),
        "task_progress": state.get("task_progress", []) + [{"step": "budget_calculate", "tool_name": "budget_calculate"}],
    }


def budget_generate_node(state: AppState) -> AppState:
    budget_res = generate_budget(state.get("budget", {}), state.get("payload", {}).get("output_dir"))
    report_res = generate_report(state.get("aggregate", {}), state.get("budget", {}), state.get("payload", {}).get("output_dir"))
    return {
        "outputs": {
            **state.get("outputs", {}),
            "budget_path": budget_res.data.get("budget_path", ""),
            "report_path": report_res.data.get("report_path", ""),
        },
        "result": {
            "type": "budget",
            "budget": state.get("budget", {}),
            "budget_path": budget_res.data.get("budget_path", ""),
            "report_path": report_res.data.get("report_path", ""),
        },
        "task_progress": state.get("task_progress", []) + [{"step": "budget_generate", "tool_name": "generate_budget/generate_report"}],
    }
