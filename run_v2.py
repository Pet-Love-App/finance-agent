from __future__ import annotations

import json
from pathlib import Path

from agent import EventBus, TaskDispatcher


def _print_event(payload: dict) -> None:
    try:
        print("[EVENT]", json.dumps(payload, ensure_ascii=False))
    except UnicodeEncodeError:
        # 当遇到编码错误时，使用 ensure_ascii=True 来输出
        print("[EVENT]", json.dumps(payload, ensure_ascii=True))


def main() -> None:
    bus = EventBus()
    bus.subscribe("task_start", _print_event)
    bus.subscribe("task_progress", _print_event)
    bus.subscribe("task_done", _print_event)
    bus.subscribe("task_error", _print_event)

    dispatcher = TaskDispatcher(bus)

    # 设置测试路径为 docs/test
    test_path = str(Path("docs/test").resolve())
    print(f"测试路径: {test_path}")
    
    # 打印测试路径中的文件
    import os
    files = os.listdir(test_path)
    print(f"测试路径中的文件: {files}")
    
    sample_payload = {
        "paths": [test_path],
        "activity_text": "2026-03-18 在学生中心举办活动，产生交通与物料支出。",
        "activity": {
            "student_name": "叶思萌",
            "student_id": "2023012164",
            "contact": "13800138000",
            "participants": "叶思萌、张奥淇",
            "organization": "学生会",
            "activity_date": "2026-03-18",
            "location": "学生中心",
            "description": "学生会午餐会活动"
        },
        "rules": {"max_amount": 50000, "required_activity_date": True},
        "output_dir": test_path,
    }
    result = dispatcher.dispatch("reimburse", sample_payload)
    
    # 打印从真实发票中提取的信息
    print("\n从真实发票中提取的信息:")
    invoices = result.get("invoices", [])
    print(f"发票数量: {len(invoices)}")
    total_amount = result.get("total_amount", 0.0)
    print(f"总金额: {total_amount}")
    for i, inv in enumerate(invoices, 1):
        print(f"发票 {i}: 编号={inv.get('invoice_no', '')}, 金额={inv.get('amount', 0)}, 日期={inv.get('date', '')}, 内容={inv.get('content', '')}")
    
    print("\nRESULT:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
