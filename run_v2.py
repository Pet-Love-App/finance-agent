from __future__ import annotations

import json
from pathlib import Path

from agent import EventBus, TaskDispatcher


def _print_event(payload: dict) -> None:
    print("[EVENT]", json.dumps(payload, ensure_ascii=False))


def main() -> None:
    bus = EventBus()
    bus.subscribe("task_start", _print_event)
    bus.subscribe("task_progress", _print_event)
    bus.subscribe("task_done", _print_event)
    bus.subscribe("task_error", _print_event)

    dispatcher = TaskDispatcher(bus)

    sample_payload = {
        "paths": [str(Path("docs/reimbursement").resolve())],
        "activity_text": "2026-03-18 在学生中心举办活动，产生交通与物料支出。",
        "rules": {"max_amount": 50000, "required_activity_date": True},
    }
    result = dispatcher.dispatch("reimburse", sample_payload)
    print("\nRESULT:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
