from __future__ import annotations

from typing import Dict, Optional, TypedDict

from agent.graphs.names import (
    NODE_BUDGET_START,
    NODE_FILE_EDIT_START,
    NODE_FINAL_START,
    NODE_QA_START,
    NODE_REIMBURSE_START,
    NODE_SANDBOX_START,
)


class TaskProfile(TypedDict):
    runtime_task: str
    start_node: str
    risk_level: str
    requires_confirmation_by_default: bool
    is_write_task: bool


TASK_QA = "qa"
TASK_REIMBURSE = "reimburse"
TASK_FINAL = "final_account"
TASK_BUDGET = "budget"
TASK_SANDBOX = "sandbox_exec"
TASK_FILE_EDIT = "file_edit"
TASK_RECON = "recon"
TASK_MATERIAL = "material"
TASK_BUDGET_FILL = "budget_fill"
TASK_FINAL_FILL = "final_fill"


TASK_ALIASES: Dict[str, str] = {
    "t1_qa": TASK_QA,
    "t2_recon": TASK_RECON,
    "t3_material": TASK_MATERIAL,
    "t4_budget_fill": TASK_BUDGET_FILL,
    "t5_final_fill": TASK_FINAL_FILL,
    "t6_file_edit": TASK_FILE_EDIT,
    TASK_QA: TASK_QA,
    TASK_REIMBURSE: TASK_REIMBURSE,
    TASK_FINAL: TASK_FINAL,
    TASK_BUDGET: TASK_BUDGET,
    TASK_SANDBOX: TASK_SANDBOX,
    TASK_FILE_EDIT: TASK_FILE_EDIT,
    TASK_RECON: TASK_RECON,
    TASK_MATERIAL: TASK_MATERIAL,
    TASK_BUDGET_FILL: TASK_BUDGET_FILL,
    TASK_FINAL_FILL: TASK_FINAL_FILL,
}


TASK_PROFILES: Dict[str, TaskProfile] = {
    TASK_QA: {
        "runtime_task": TASK_QA,
        "start_node": NODE_QA_START,
        "risk_level": "medium",
        "requires_confirmation_by_default": False,
        "is_write_task": False,
    },
    TASK_REIMBURSE: {
        "runtime_task": TASK_REIMBURSE,
        "start_node": NODE_REIMBURSE_START,
        "risk_level": "medium",
        "requires_confirmation_by_default": False,
        "is_write_task": False,
    },
    TASK_FINAL: {
        "runtime_task": TASK_FINAL,
        "start_node": NODE_FINAL_START,
        "risk_level": "medium",
        "requires_confirmation_by_default": False,
        "is_write_task": False,
    },
    TASK_BUDGET: {
        "runtime_task": TASK_BUDGET,
        "start_node": NODE_BUDGET_START,
        "risk_level": "medium",
        "requires_confirmation_by_default": False,
        "is_write_task": False,
    },
    TASK_SANDBOX: {
        "runtime_task": TASK_SANDBOX,
        "start_node": NODE_SANDBOX_START,
        "risk_level": "medium",
        "requires_confirmation_by_default": False,
        "is_write_task": False,
    },
    TASK_FILE_EDIT: {
        "runtime_task": TASK_FILE_EDIT,
        "start_node": NODE_FILE_EDIT_START,
        "risk_level": "high",
        "requires_confirmation_by_default": True,
        "is_write_task": True,
    },
    TASK_RECON: {
        "runtime_task": TASK_FINAL,
        "start_node": NODE_FINAL_START,
        "risk_level": "medium",
        "requires_confirmation_by_default": False,
        "is_write_task": False,
    },
    TASK_MATERIAL: {
        "runtime_task": TASK_FILE_EDIT,
        "start_node": NODE_FILE_EDIT_START,
        "risk_level": "high",
        "requires_confirmation_by_default": False,
        "is_write_task": True,
    },
    TASK_BUDGET_FILL: {
        "runtime_task": TASK_BUDGET,
        "start_node": NODE_BUDGET_START,
        "risk_level": "high",
        "requires_confirmation_by_default": True,
        "is_write_task": True,
    },
    TASK_FINAL_FILL: {
        "runtime_task": TASK_FINAL,
        "start_node": NODE_FINAL_START,
        "risk_level": "high",
        "requires_confirmation_by_default": True,
        "is_write_task": True,
    },
}


def normalize_task_alias(task_type: str) -> str:
    text = str(task_type or "").strip().lower()
    if text in {"", "auto"}:
        return ""
    return TASK_ALIASES.get(text, "")


def get_task_profile(task_type: str) -> Optional[TaskProfile]:
    return TASK_PROFILES.get(str(task_type or "").strip().lower())


def get_start_node_for_runtime_task(runtime_task: str) -> str:
    profile = get_task_profile(runtime_task)
    if profile:
        return profile["start_node"]
    # Keep backward-compatible fallback behavior.
    return NODE_REIMBURSE_START
