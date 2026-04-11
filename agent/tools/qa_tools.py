from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse, urlunparse

from agent.tools.base import ToolResult, ok


def question_understand(question: str) -> ToolResult:
    normalized = question.strip()
    intent = "policy"
    if any(key in normalized for key in ["报销", "附件", "发票", "金额", "规则"]):
        intent = "policy"
    elif any(key in normalized for key in ["预算", "决算", "财务", "报表", "填表"]):
        intent = "finance"
    elif any(key in normalized for key in ["实验", "实验报告", "数据分析", "结论"]):
        intent = "lab_report"
    return ok(intent=intent, question=normalized)


def _build_clarifying_question(intent: str, question: str) -> str:
    if intent == "policy":
        return (
            "我目前缺少足够依据来精确回答。"
            "请补充活动类型、票据类型、金额区间和发生时间，我再按制度条款给出结论。"
        )
    if intent == "finance":
        return (
            "为了继续处理，请补充任务目标（报销校验/自动填表/预算或决算）、"
            "涉及模板文件名，以及关键字段（金额、项目号、时间范围）。"
        )
    if intent == "lab_report":
        return "请补充实验目的、数据来源、分析方法和希望输出的报告结构，我再生成可执行建议。"
    if question.strip():
        return "我需要更多上下文。请补充关键条件（场景、约束、时间范围），我再给出准确结论。"
    return "请先描述你的问题场景和目标，我会先反问补齐信息后再回答。"


def _infer_domain_label(item: Dict[str, Any]) -> str:
    category = str(item.get("category", "")).strip()
    subcategory = str(item.get("subcategory", "")).strip()
    if category and subcategory:
        return f"{category}/{subcategory}"
    if category:
        return category
    source = str(item.get("source", "")).replace("\\", "/")
    if "/" in source:
        return source.split("/", 1)[0].strip() or "综合政策"
    return "综合政策"


def _build_action_tip(domain_label: str) -> str:
    mapping = {
        "政策文件": "先核对制度条款，再准备票据与审批材料。",
        "学生活动": "优先准备预算/决算模板与活动说明，再补齐附件。",
        "国内+思政实践": "核验交通与住宿标准，补齐行程和差旅说明。",
        "海外实践": "先确认国际差旅标准与合同流程，再准备外汇/转账材料。",
        "清华大学 财务报销标准": "按学校统一标准先做额度与票据合规自查。",
        "工作餐报销 餐单（仅校内结算单报销需要填写，电子票据直接系统内添加餐单）": "先确认是否属于校内结算单，再补齐餐单与审批单。",
    }
    return mapping.get(domain_label, "先确认适用场景，再按模板和制度逐项补齐材料。")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_markdown_text(text: str) -> str:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.split("\n")
    normalized: List[str] = []
    blank_run = 0
    for line in lines:
        collapsed = re.sub(r"[ \t]+", " ", line).strip()
        if not collapsed:
            blank_run += 1
            if blank_run <= 1:
                normalized.append("")
            continue
        blank_run = 0
        normalized.append(collapsed)
    return "\n".join(normalized).strip()


def _strip_reference_lines(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines()]
    if not lines:
        return ""
    filtered: List[str] = []
    for line in lines:
        if not line:
            continue
        if re.match(r"^(主要依据|参考|补充依据)\s*[：:]", line):
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def _extract_query_tokens(question: str) -> List[str]:
    normalized = _normalize_text(question)
    if not normalized:
        return []
    raw_tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", normalized)
    return [token.lower() for token in raw_tokens if len(token.strip()) >= 2]


def _citation_label(item: Dict[str, Any]) -> str:
    source = str(item.get("source", "")).strip()
    if source:
        return Path(source.replace("\\", "/")).name or source
    title = str(item.get("title", "")).strip()
    return title or "知识库片段"


def _split_sentences(content: str) -> List[str]:
    text = _normalize_text(content)
    if not text:
        return []
    text = re.sub(r"\[Slide\s*\d+\]", " ", text, flags=re.IGNORECASE)
    parts = re.split(r"[。\n；;!?！？]+", text)
    return [_normalize_text(part) for part in parts if _normalize_text(part)]


def _summarize_point(sentence: str, *, max_chars: int = 68) -> str:
    text = _normalize_text(sentence)
    if not text:
        return ""
    text = re.sub(r"[（(]\s*参考[:：].*?[)）]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"([\u4e00-\u9fff]{2,8})(?:\s+\1){1,}", r"\1", text)
    text = re.sub(r"([A-Za-z]{2,})(?:\s+\1){1,}", r"\1", text, flags=re.IGNORECASE)
    text = _normalize_text(text)
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip("，,；;。.!?！？ ") + "…"
    return text


def _evidence_title(item: Dict[str, Any]) -> str:
    title = str(item.get("title", "")).strip()
    if title:
        return title
    return _citation_label(item)


def _to_float_env(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default


def _normalize_chat_completions_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return "https://api.openai.com/v1/chat/completions"

    try:
        parsed = urlparse(text)
        path = (parsed.path or "").rstrip("/")
        if not path:
            next_path = "/v1/chat/completions"
        elif path.endswith("/chat/completions"):
            next_path = path
        else:
            next_path = f"{path}/chat/completions"
        return urlunparse(parsed._replace(path=next_path))
    except Exception:
        fallback = text.rstrip("/")
        if not fallback:
            return "https://api.openai.com/v1/chat/completions"
        if fallback.endswith("/chat/completions"):
            return fallback
        if fallback.endswith("/v1"):
            return f"{fallback}/chat/completions"
        return f"{fallback}/chat/completions"


def _resolve_temperature_for_model(model: str, temperature: float) -> float:
    normalized_model = str(model or "").strip().lower()
    # Kimi K2.5 currently only accepts temperature=1.
    if normalized_model in {"kimi-k2.5", "kimi-k2_5"}:
        return 1.0
    return float(temperature)


def _call_llm_chat(messages: List[Dict[str, str]], model: str, temperature: float, timeout: int = 20) -> str:
    api_key = (os.getenv("AGENT_LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("missing llm api key")
    raw_url = (
        os.getenv("AGENT_LLM_BASE_URL")
        or os.getenv("OPENAI_API_URL")
        or os.getenv("AGENT_LLM_API_URL")
        or "https://api.openai.com/v1"
    )
    url = _normalize_chat_completions_url(raw_url)
    resolved_temperature = _resolve_temperature_for_model(model, temperature)

    def _send_request(temp: float) -> str:
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": float(temp),
            },
            ensure_ascii=False,
        )
        req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    try:
        body = _send_request(resolved_temperature)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        detail_text = (detail or "").strip()
        if float(resolved_temperature) != 1.0 and "only 1 is allowed" in detail_text.lower():
            body = _send_request(1.0)
        else:
            reason = f"{exc.code} {exc.reason}"
            if detail_text:
                reason = f"{reason} - {detail_text[:280]}"
            raise RuntimeError(f"llm request failed: {reason}") from exc
    parsed_body = json.loads(body)
    return str(parsed_body["choices"][0]["message"]["content"])


def _generate_llm_answer(question: str, ranked: Sequence[Dict[str, Any]], *, intent: str, max_items: int = 4) -> Optional[str]:
    use_llm = str(os.getenv("AGENT_QA_USE_LLM_ANSWER", "true")).strip().lower()
    if use_llm in {"0", "false", "no", "off"}:
        return None
    if not ranked:
        return None
    api_key = (os.getenv("AGENT_LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return None

    evidence_rows: List[Dict[str, Any]] = []
    for idx, item in enumerate(ranked[: max(1, max_items)], start=1):
        excerpt = _normalize_text(str(item.get("content", "")))
        if len(excerpt) > 280:
            excerpt = excerpt[:280].rstrip() + "..."
        evidence_rows.append(
            {
                "id": idx,
                "title": str(item.get("title", "")).strip() or _citation_label(item),
                "source": _citation_label(item),
                "score": round(float(item.get("score", 0.0)), 3),
                "excerpt": excerpt,
            }
        )

    system_prompt = (
        "你是高校财务报销问答助手。"
        "请严格依据提供的检索证据回答，优先输出可执行建议。"
        "禁止逐字长段复制原文；可以提炼要点。"
        "若证据不足，请明确说明缺什么信息。"
        "不要输出“任务结果/检索模式/置信度”等系统字段。"
        "不要输出“主要依据/参考/补充依据/片段编号”等引用标签。"
    )
    user_prompt = (
        f"用户问题：{question}\n"
        f"问题意图：{intent}\n"
        f"证据（JSON）：{json.dumps(evidence_rows, ensure_ascii=False)}\n\n"
        "请输出中文答案，3-6行以内，先给结论，再给必要条件或步骤。"
    )
    model = str(os.getenv("AGENT_LLM_MODEL", "DeepSeekV3.2")).strip() or "DeepSeekV3.2"
    temperature = _to_float_env("AGENT_QA_LLM_TEMPERATURE", _to_float_env("AGENT_LLM_TEMPERATURE", 0.1))
    try:
        raw = _call_llm_chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=temperature,
        )
    except Exception:
        return None
    text = _normalize_markdown_text(raw)
    text = re.sub(r"^```(?:json|markdown|text)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = _strip_reference_lines(text)
    return text.strip() or None


def _extract_key_points(question: str, ranked: Sequence[Dict[str, Any]], max_points: int = 5) -> List[Tuple[str, str]]:
    query_tokens = _extract_query_tokens(question)
    generic_tokens = ["报销", "材料", "标准", "附件", "发票", "交通", "住宿", "保险", "租车", "实践"]
    selected: List[Tuple[float, str, str]] = []
    seen: set[str] = set()

    for item in ranked[:8]:
        source_name = _citation_label(item)
        sentences = _split_sentences(str(item.get("content", "")))
        for sentence in sentences:
            if len(sentence) < 10 or len(sentence) > 120:
                continue
            key = sentence.lower()
            if key in seen:
                continue
            token_hits = sum(1 for token in query_tokens if token and token in key)
            generic_hits = sum(1 for token in generic_tokens if token in key)
            if token_hits == 0 and generic_hits == 0:
                continue
            score = token_hits * 2 + generic_hits
            if re.search(r"报销|标准|需|需要|应|可|不得|凭票|附件", sentence):
                score += 1
            selected.append((float(score), sentence, source_name))
            seen.add(key)

    selected.sort(key=lambda row: row[0], reverse=True)
    return [(sentence, source_name) for _, sentence, source_name in selected[: max(1, max_points)]]


def build_workflow_hint(question: str) -> Optional[Dict[str, Any]]:
    text = question.strip()
    if not text:
        return None

    if any(key in text for key in ["报销", "自动填表", "填表", "审批", "财务"]):
        return {
            "name": "finance_workflow",
            "steps": [
                "信息采集（报销人、项目号、金额、票据）",
                "规则校验（额度、必填项、附件完整性）",
                "计算与格式化（汇总金额、模板字段映射）",
                "生成材料（表单、说明文档、邮件草稿）",
                "人工确认后提交",
            ],
            "tool_candidates": ["scan_inputs", "extract_text_from_files", "check_rules", "generate_excel_sheet"],
        }

    if any(key in text for key in ["实验报告", "实验", "报告辅助"]):
        return {
            "name": "lab_report_workflow",
            "steps": [
                "检索实验相关资料片段",
                "抽取实验背景与关键参数",
                "生成报告大纲与结论草稿",
                "按模板输出与人工复核",
            ],
            "tool_candidates": ["rag_retrieve", "generate_report"],
        }
    return None


def answer_generate(
    question: str,
    retrieved_items: List[Dict[str, Any]],
    *,
    min_score: float = 0.55,
    intent: str = "policy",
) -> ToolResult:
    if not retrieved_items:
        clarifying = _build_clarifying_question(intent, question)
        return ok(
            answer=f"未检索到直接依据：{question}。",
            citations=[],
            confidence=0.0,
            needs_clarification=True,
            clarifying_question=clarifying,
        )

    ranked = sorted(retrieved_items, key=lambda item: float(item.get("score", 0.0)), reverse=True)
    top = ranked[0]
    top_score = float(top.get("score", 0.0))
    if top_score < float(min_score):
        clarifying = _build_clarifying_question(intent, question)
        return ok(
            answer="已检索到相关内容，但证据置信度不足，暂不直接下结论。",
            citations=[],
            confidence=top_score,
            needs_clarification=True,
            clarifying_question=clarifying,
        )

    domain_label = _infer_domain_label(top)
    key_points = _extract_key_points(question, ranked, max_points=5)
    llm_answer = _generate_llm_answer(question, ranked, intent=intent, max_items=4)
    if llm_answer:
        answer = llm_answer
    elif key_points:
        lines = ["结论与建议："]
        for idx, (point, _) in enumerate(key_points, start=1):
            concise_point = _summarize_point(point)
            if not concise_point:
                continue
            lines.append(f"{idx}. {concise_point}")
        if len(lines) <= 3:
            lines.append("请补充更具体的活动类型和报销场景，我可以进一步细化到可执行清单。")
        answer = "\n".join(lines)
    else:
        top_category = str(top.get("category", "")).strip()
        action_tip = _build_action_tip(top_category or domain_label)
        scene = top_category or domain_label
        answer = f"适用场景：{scene}\n{action_tip}" if scene else action_tip
    citations = [
        {
            "source": top.get("source", ""),
            "title": top.get("title", ""),
            "score": float(top.get("score", 0)),
            "category": top.get("category", ""),
            "doc_type": top.get("doc_type", ""),
        }
        for top in ranked[:3]
    ]
    return ok(
        answer=answer,
        citations=citations,
        confidence=top_score,
        needs_clarification=False,
        clarifying_question="",
    )
