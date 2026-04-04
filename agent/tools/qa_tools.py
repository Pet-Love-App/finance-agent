from __future__ import annotations

from typing import Any, Dict, List

from agent.tools.base import ToolResult, ok


def question_understand(question: str) -> ToolResult:
    normalized = question.strip()
    intent = "policy"
    if any(key in normalized for key in ["报销", "附件", "发票", "金额", "规则"]):
        intent = "policy"
    elif any(key in normalized for key in ["预算", "决算"]):
        intent = "finance"
    return ok(intent=intent, question=normalized)


def answer_generate(question: str, retrieved_items: List[Dict[str, Any]]) -> ToolResult:
    if not retrieved_items:
        return ok(answer=f"未检索到直接规则依据：{question}。请补充更具体的活动类型、票据类型和金额区间。", citations=[])

    top = retrieved_items[0]
    answer = (
        f"根据本地规则，与你问题最相关的是《{top.get('title', '规则片段')}》。"
        f"建议优先按该条款准备材料并提交。"
    )
    citations = [
        {
            "source": top.get("source", ""),
            "title": top.get("title", ""),
            "score": top.get("score", 0),
        }
    ]
    return ok(answer=answer, citations=citations)
