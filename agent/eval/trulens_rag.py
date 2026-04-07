from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Sequence

from agent.kb.retriever import search_policy


def _normalize(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _token_set(text: str) -> set[str]:
    return {token for token in _normalize(text).split(" ") if token}


def _safe_overlap_ratio(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    if not left_tokens:
        return 0.0
    right_tokens = _token_set(right)
    overlap = left_tokens.intersection(right_tokens)
    return float(len(overlap) / len(left_tokens))


def _context_relevance_score(question: str, answer_payload: Dict[str, Any]) -> float:
    contexts = answer_payload.get("contexts", [])
    context_text = "\n".join(str(item) for item in contexts)
    return _safe_overlap_ratio(question, context_text)


def _answer_groundedness_score(question: str, answer_payload: Dict[str, Any]) -> float:
    _ = question
    contexts = answer_payload.get("contexts", [])
    context_text = "\n".join(str(item) for item in contexts)
    return _safe_overlap_ratio(str(answer_payload.get("answer", "")), context_text)


def _expected_keyword_hit_score(expected_keywords: Sequence[str], answer_payload: Dict[str, Any]) -> float:
    expected = [str(item).strip() for item in expected_keywords if str(item).strip()]
    if not expected:
        return 0.0
    answer_text = str(answer_payload.get("answer", ""))
    contexts_text = "\n".join(str(item) for item in answer_payload.get("contexts", []))
    full_text = f"{answer_text}\n{contexts_text}".lower()
    hit = 0
    for keyword in expected:
        if keyword.lower() in full_text:
            hit += 1
    return float(hit / len(expected))


def _build_feedbacks():
    from trulens_eval import Feedback

    feedbacks: List[Any] = []
    warnings: List[str] = []

    f_context = Feedback(
        _context_relevance_score,
        name="context_relevance",
    ).on_input_output()
    f_grounded = Feedback(
        _answer_groundedness_score,
        name="answer_groundedness",
    ).on_input_output()
    feedbacks.extend([f_context, f_grounded])

    use_llm_judge = os.getenv("AGENT_TRULENS_USE_LLM_JUDGE", "").strip().lower() in ("1", "true", "yes", "on")
    if not use_llm_judge:
        return feedbacks, warnings

    try:
        from trulens_eval.feedback.provider.openai import OpenAI

        judge_model = os.getenv("AGENT_TRULENS_JUDGE_MODEL", os.getenv("AGENT_LLM_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"
        api_key = os.getenv("AGENT_LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")).strip()
        base_url = os.getenv("AGENT_LLM_API_URL", os.getenv("AGENT_LLM_BASE_URL", "")).strip()
        if not api_key:
            warnings.append("已启用 LLM Judge，但未检测到 AGENT_LLM_API_KEY，回退到启发式评分。")
            return feedbacks, warnings

        provider_kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            provider_kwargs["base_url"] = base_url

        try:
            provider = OpenAI(model_engine=judge_model, **provider_kwargs)
        except TypeError:
            provider = OpenAI(model=judge_model, **provider_kwargs)

        # 1. Context Relevance (LLM)
        llm_context_fn = getattr(provider, "relevance_with_cot_reasons", None)
        if callable(llm_context_fn):
            feedbacks.append(Feedback(llm_context_fn, name="llm_context_relevance").on_input_output())

        # 2. Answer Relevance (LLM)
        llm_answer_fn = getattr(provider, "qs_relevance_with_cot_reasons", None)
        if callable(llm_answer_fn):
            feedbacks.append(Feedback(llm_answer_fn, name="llm_answer_relevance").on_input_output())

        # 3. Conciseness (LLM)
        llm_conciseness_fn = getattr(provider, "conciseness_with_cot_reasons", None)
        if callable(llm_conciseness_fn):
            feedbacks.append(Feedback(llm_conciseness_fn, name="llm_conciseness").on_input_output())

        if not any(f.name.startswith("llm_") for f in feedbacks):
            warnings.append("当前 TruLens 版本未暴露预期的 OpenAI Feedback 方法，已跳过 LLM Judge。")
    except Exception as exc:
        warnings.append(f"加载 LLM Judge 失败，已回退启发式评分: {exc}")

    return feedbacks, warnings


def build_eval_questions_from_kb(
    kb_path: str | Path,
    *,
    max_samples: int = 30,
) -> List[Dict[str, Any]]:
    payload = json.loads(Path(kb_path).read_text(encoding="utf-8"))
    chunks = payload.get("chunks", [])
    if not isinstance(chunks, list):
        return []

    samples: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        title = str(chunk.get("title", "")).strip()
        if not title:
            continue
        question = f"{title} 的核心报销要求是什么？"
        if question in seen:
            continue
        seen.add(question)
        samples.append(
            {
                "id": f"kb_auto_{idx+1}",
                "question": question,
                "expected_keywords": [],
            }
        )
        if len(samples) >= max(1, max_samples):
            break
    return samples


def load_eval_questions(dataset_path: str | Path) -> List[Dict[str, Any]]:
    raw = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        rows = raw.get("samples", [])
    else:
        rows = raw
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        question = str(row.get("question", "")).strip()
        if not question:
            continue
        normalized.append(
            {
                "id": str(row.get("id", f"sample_{idx+1}")),
                "question": question,
                "expected_keywords": row.get("expected_keywords", []) if isinstance(row.get("expected_keywords", []), list) else [],
            }
        )
    return normalized


def _build_rag_app(kb_path: Path, top_k: int):
    def _app(question: str) -> Dict[str, Any]:
        chunks = search_policy(question, top_k=top_k, kb_path=kb_path)
        contexts = [item.content for item in chunks]
        citations = [{"source": item.source, "title": item.title, "score": float(item.score)} for item in chunks]
        answer = contexts[0] if contexts else "未检索到相关内容"
        return {
            "answer": answer,
            "contexts": contexts,
            "citations": citations,
        }

    return _app


def run_trulens_rag_eval(
    *,
    kb_path: str | Path,
    questions: Sequence[Dict[str, Any]],
    top_k: int = 4,
    app_id: str = "agent_rag_eval",
    output_dir: str | Path = "data/eval",
) -> Dict[str, Any]:
    try:
        from trulens_eval import TruBasicApp
    except Exception as exc:
        raise RuntimeError(
            "未检测到 TruLens 依赖。请先安装: pip install trulens-eval"
        ) from exc

    resolved_kb = Path(kb_path).resolve()
    if not resolved_kb.exists():
        raise FileNotFoundError(f"知识库不存在: {resolved_kb}")
    if top_k < 1:
        raise ValueError("top_k 必须大于等于 1")
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    rag_app = _build_rag_app(resolved_kb, top_k=top_k)
    feedbacks, feedback_warnings = _build_feedbacks()
    tru_app = TruBasicApp(
        rag_app,
        app_id=app_id,
        feedbacks=feedbacks,
    )

    records: List[Dict[str, Any]] = []
    pass_threshold = float(os.getenv("AGENT_TRULENS_PASS_THRESHOLD", "0.7"))
    for item in questions:
        question = str(item.get("question", "")).strip()
        if not question:
            continue
        with tru_app as recorder:
            output = rag_app(question)
        record_id = getattr(recorder, "record_id", None)
        context_score = _context_relevance_score(question, output)
        grounded_score = _answer_groundedness_score(question, output)
        expected_keywords = item.get("expected_keywords", [])
        if not isinstance(expected_keywords, list):
            expected_keywords = []
        expected_hit_score = _expected_keyword_hit_score(expected_keywords, output)

        scores = {
            "context_relevance": context_score,
            "answer_groundedness": grounded_score,
            "expected_keyword_hit": expected_hit_score,
        }
        # A simple pass/fail logic based on average heuristic scores
        avg_score = mean(scores.values())
        is_pass = avg_score >= pass_threshold

        records.append(
            {
                "sample_id": item.get("id", ""),
                "question": question,
                "record_id": str(record_id or ""),
                "answer": output.get("answer", ""),
                "contexts": output.get("contexts", []),
                "citations": output.get("citations", []),
                "expected_keywords": expected_keywords,
                "scores": scores,
                "is_pass": is_pass,
            }
        )

    if not records:
        raise RuntimeError("评估问题为空或全部无效，未产生任何评估记录")

    pass_count = sum(1 for r in records if r["is_pass"])
    summary = {
        "app_id": app_id,
        "kb_path": str(resolved_kb),
        "top_k": top_k,
        "run_id": run_id,
        "sample_count": len(records),
        "pass_count": pass_count,
        "pass_rate": float(pass_count / len(records)),
        "avg_context_relevance": mean([row["scores"]["context_relevance"] for row in records]) if records else 0.0,
        "avg_answer_groundedness": mean([row["scores"]["answer_groundedness"] for row in records]) if records else 0.0,
        "avg_expected_keyword_hit": mean([row["scores"]["expected_keyword_hit"] for row in records]) if records else 0.0,
        "feedback_names": [str(getattr(item, "name", "unknown")) for item in feedbacks],
        "feedback_warnings": feedback_warnings,
        "timestamp": datetime.now().isoformat(),
    }

    report = {"summary": summary, "records": records}
    report_path = out_dir / f"trulens_rag_eval_{run_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "report_path": str(report_path),
        "summary": summary,
    }
