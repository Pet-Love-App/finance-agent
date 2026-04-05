from __future__ import annotations

from agent.graphs.policy import get_bool_policy
from agent.graphs.state import AppState
from agent.tools import budget_calculate, generate_budget, generate_report, load_final_data


def budget_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "budget_start", "tool_name": "start"}]}


def route_after_load_final_data(state: AppState) -> str:
    payload = state.get("payload", {})
    aggregate = state.get("aggregate", {})
    skip_calculate_when_empty = get_bool_policy(payload, "budget_skip_calculate_when_empty", True)
    if aggregate:
        return "BudgetCalculateNode"
    return "BudgetGenerateNode" if skip_calculate_when_empty else "BudgetCalculateNode"


def load_final_data_node(state: AppState) -> AppState:
    res = load_final_data(state.get("payload", {}))
    return {
        "aggregate": res.data.get("final_data", {}),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "load_final_data", "tool_name": "load_final_data"}],
    }


def budget_calculate_node(state: AppState) -> AppState:
    strategy = state.get("payload", {}).get("strategy", {})
    res = budget_calculate(state.get("aggregate", {}), strategy)
    return {
        "budget": res.data.get("budget", {}),
        "errors": state.get("errors", []) + ([res.error] if res.error else []),
        "task_progress": state.get("task_progress", []) + [{"step": "budget_calculate", "tool_name": "budget_calculate"}],
    }


def budget_generate_node(state: AppState) -> AppState:
    budget = state.get("budget", {})
    aggregate = state.get("aggregate", {})
    budget_res = generate_budget(budget, state.get("payload", {}).get("output_dir"))
    report_res = generate_report(aggregate, budget, state.get("payload", {}).get("output_dir"))
    errors = state.get("errors", []) + ([budget_res.error] if budget_res.error else []) + ([report_res.error] if report_res.error else [])
    return {
        "outputs": {
            **state.get("outputs", {}),
            "budget_path": budget_res.data.get("budget_path", ""),
            "report_path": report_res.data.get("report_path", ""),
        },
        "result": {
            "type": "budget",
            "budget": budget,
            "budget_path": budget_res.data.get("budget_path", ""),
            "report_path": report_res.data.get("report_path", ""),
            "errors": errors,
        },
        "errors": errors,
        "task_progress": state.get("task_progress", []) + [{"step": "budget_generate", "tool_name": "generate_budget/generate_report"}],
    }
