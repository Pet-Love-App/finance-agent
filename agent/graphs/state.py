from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class AppState(TypedDict, total=False):
    task_type: str
    payload: Dict[str, Any]

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

    qa_answer: Dict[str, Any]
    sandbox_result: Dict[str, Any]
    outputs: Dict[str, Any]
    result: Dict[str, Any]

    task_progress: List[Dict[str, Any]]
    errors: List[str]
