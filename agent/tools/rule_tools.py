from __future__ import annotations

import json
import re
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


def _tokenize_query(query: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", query.strip().lower())
    if not normalized:
        return []
    return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{1,2}", normalized)


def _load_rule_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=False)
    return path.read_text(encoding="utf-8", errors="ignore")


def _score_text(query: str, tokens: List[str], text: str) -> float:
    haystack = text.lower()
    if not haystack.strip():
        return 0.0

    score = 0.0
    phrase = query.strip().lower()
    if phrase and phrase in haystack:
        score += 2.0

    for token in tokens:
        if token and token in haystack:
            score += 1.0

    return score


def rule_retrieve(query: str, rules_path: str | None = None, top_k: int = 5) -> ToolResult:
    normalized_query = query.strip()
    if not normalized_query:
        return ok(items=[])

    if not rules_path:
        return ok(items=[])

    path = Path(rules_path)
    if not path.exists():
        return ok(items=[])

    text = _load_rule_text(path)
    tokens = _tokenize_query(normalized_query)
    blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    if not blocks:
        blocks = [text]

    scored: List[Dict[str, Any]] = []
    for block in blocks:
        score = _score_text(normalized_query, tokens, block)
        if score <= 0:
            continue
        scored.append(
            {
                "source": str(path),
                "title": path.stem,
                "content": block[:800],
                "score": float(score),
            }
        )

    scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return ok(items=scored[: max(1, top_k)])


def rag_retrieve(
    query: str,
    kb_path: str | None = None,
    top_k: int = 4,
    score_threshold: float | None = None,
) -> ToolResult:
    from agent.kb.retriever import RetrievedChunk, format_retrieved_context, retrieve_chunks, search_policy

    try:
        items = search_policy(query=query, top_k=top_k, kb_path=kb_path)
        retrieval = "vector"
    except Exception:
        items = retrieve_chunks(query=query, top_k=top_k, kb_path=kb_path or "data/kb/reimbursement_kb.json")
        retrieval = "keyword_fallback"

    result_items = [
        {
            "source": item.source,
            "title": item.title,
            "content": item.content,
            "score": float(item.score),
        }
        for item in items
    ]
    if score_threshold is not None:
        result_items = [item for item in result_items if float(item.get("score", 0.0)) >= float(score_threshold)]

    context_chunks = [
        RetrievedChunk(
            source=str(item.get("source", "")),
            title=str(item.get("title", "")),
            content=str(item.get("content", "")),
            score=float(item.get("score", 0.0)),
        )
        for item in result_items
    ]
    context = format_retrieved_context(context_chunks)
    return ok(items=result_items, context=context, retrieval=retrieval)
