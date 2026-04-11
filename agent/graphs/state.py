from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class AppState(TypedDict, total=False):
    task_type: str
    payload: Dict[str, Any]
    route_decision: Dict[str, Any]

    files: List[str]
    classified_files: Dict[str, List[str]]
    merged_text: str
    file_text_map: Dict[str, str]

    invoice: Dict[str, Any]
    activity: Dict[str, Any]
    rule_result: Dict[str, Any]
    email_draft: Dict[str, Any]

    records: List[Dict[str, Any]]
    aggregate: Dict[str, Any]
    budget: Dict[str, Any]
    canonical_budget_rows: List[Dict[str, Any]]
    canonical_actual_rows: List[Dict[str, Any]]
    recon_differences: List[Dict[str, Any]]
    compliance_findings: List[Dict[str, Any]]
    fix_suggestions: List[Dict[str, Any]]
    material_checklist: List[Dict[str, Any]]

    qa_answer: Dict[str, Any]
    sandbox_result: Dict[str, Any]
    file_tool_result: Dict[str, Any]
    outputs: Dict[str, Any]
    result: Dict[str, Any]
    graph_trace: List[Dict[str, Any]]

    task_progress: List[Dict[str, Any]]
    errors: List[str]
