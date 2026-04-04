from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from agent.tools.base import ToolResult, ok


def check_rules(invoice: Dict[str, Any], activity: Dict[str, Any], rules: Dict[str, Any] | None = None) -> ToolResult:
    rules = rules or {}
    max_amount = float(rules.get("max_amount", 100000.0))
    required_activity_date = bool(rules.get("required_activity_date", True))

    violations: List[str] = []
    amount = float(invoice.get("amount", 0.0) or 0.0)
    if amount <= 0:
        violations.append("发票金额无效")
    if amount > max_amount:
        violations.append(f"金额超过上限 {max_amount}")
    if required_activity_date and not str(activity.get("activity_date", "")).strip():
        violations.append("活动说明缺少日期")

    return ok(
        compliance=(len(violations) == 0),
        violations=violations,
        suggestion="请补充缺失字段并重新校验" if violations else "规则校验通过",
    )


def rule_retrieve(query: str, rules_path: str | None = None) -> ToolResult:
    if not query.strip():
        return ok(items=[])

    if rules_path:
        path = Path(rules_path)
        if path.exists() and path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(payload, ensure_ascii=False)
            if query in text:
                return ok(items=[{"source": str(path), "content": query}])

    return ok(items=[])


def rag_retrieve(query: str, kb_path: str | None = None, top_k: int = 4) -> ToolResult:
    from agent.kb.retriever import format_retrieved_context, search_policy

    items = search_policy(query=query, top_k=top_k, kb_path=kb_path)
    context = format_retrieved_context(items)
    result_items = [
        {
            "source": item.source,
            "title": item.title,
            "content": item.content,
            "score": item.score,
        }
        for item in items
    ]
    return ok(items=result_items, context=context)
