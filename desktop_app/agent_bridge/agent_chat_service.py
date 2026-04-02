from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from uuid import uuid4

# 将仓库根目录加入 sys.path，便于导入已有 reimbursement_agent 包
CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[2]  # .../agent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SYSTEM_PROMPT = (
    "你是企业报销审计助手。"
    "请优先使用简洁、准确、可执行的中文回答；"
    "若用户询问报销审计规则，请结合常见合规点给出建议；"
    "若问题超出报销场景，也可进行通用问答。"
)

DEFAULT_KB_PATH = PROJECT_ROOT / "data" / "kb" / "reimbursement_kb.json"


def _get_llm_base_url() -> str:
    raw = (
        os.getenv("AGENT_LLM_BASE_URL", "").strip()
        or os.getenv("AGENT_LLM_API_URL", "").strip()
        or "https://api.openai.com/v1"
    )
    normalized = raw.rstrip("/")
    parsed = urlparse(normalized)

    path = (parsed.path or "").rstrip("/")
    if not path:
        normalized = f"{normalized}/v1"

    return normalized


def _safe_int_env(name: str, default: int, *, min_value: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(value, min_value)


def _normalize_history(history: List[Dict[str, str]], message: str) -> List[Dict[str, str]]:
    history_messages: List[Dict[str, str]] = []
    for item in history[-20:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        history_messages.append({"role": role, "content": content})

    normalized: List[Dict[str, str]] = []
    for item in history_messages:
        if not normalized:
            if item["role"] != "user":
                continue
            normalized.append(item)
            continue

        if normalized[-1]["role"] == item["role"]:
            normalized[-1]["content"] += "\n\n" + item["content"]
        else:
            normalized.append(item)

    if not normalized:
        return [{"role": "user", "content": message}]

    if normalized[-1]["role"] != "user":
        normalized.append({"role": "user", "content": message})
    elif normalized[-1]["content"] != message:
        normalized[-1]["content"] += "\n\n" + message
    return normalized


def _build_llm_messages(message: str, history: List[Dict[str, str]], kb_context: str) -> Tuple[List[Dict[str, str]], bool]:
    base_url = _get_llm_base_url()
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}

    normalized = _normalize_history(history, message)

    messages: List[Dict[str, str]] = []
    if is_local:
        if normalized:
            context_block = f"\n\n可参考的知识库片段（优先基于这些资料回答）：\n{kb_context}" if kb_context else ""
            normalized[0]["content"] = f"{SYSTEM_PROMPT}{context_block}\n\n用户问题：{normalized[0]['content']}"
        messages.extend(normalized)
    else:
        system_prompt = SYSTEM_PROMPT
        if kb_context:
            system_prompt += f"\n\n可参考的知识库片段：\n{kb_context}"
        messages.append({"role": "system", "content": system_prompt})
        messages.extend(normalized)

    return messages, is_local


def _rule_reply(message: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    budget_source = payload.get("budget_source")
    actual_source = payload.get("actual_source")

    if budget_source is not None and actual_source is not None:
        return _run_audit(budget_source, actual_source)

    if re.search(r"sample|示例|demo", message, flags=re.IGNORECASE):
        from agent.sample_data import get_sample_payloads  # noqa: WPS433

        budget_json, actual_json = get_sample_payloads()
        return _run_audit(budget_json, actual_json)

    if "高风险" in message or "风险" in message:
        return {
            "reply": "高风险触发规则：类目无法映射、单项超支>10%、总额超预算、餐饮/会议缺签到或通知附件。",
        }

    if "材料" in message or "附件" in message:
        return {
            "reply": "餐饮/会议类支出需具备签到表或通知文件提示，建议在上传时同时附发票和明细。",
        }

    return None


def _brief_report(report_json: Dict[str, Any]) -> str:
    summary = report_json.get("summary", {})
    total = summary.get("total_issues", 0)
    high = summary.get("high_risk_issues", 0)
    status = summary.get("overall_status", "UNKNOWN")
    return f"审计完成：状态={status}，问题总数={total}，高风险={high}。"


def _run_audit(budget_source: Any, actual_source: Any) -> Dict[str, Any]:
    try:
        from agent.graph_builder import build_graph  # noqa: WPS433
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "审计模式依赖缺失，请在当前 Python 环境安装 requirements.txt（含 pandas/langgraph/jsonschema）。"
        ) from exc

    app = build_graph()
    state: Dict[str, Any] = {
        "budget_source": budget_source,
        "actual_source": actual_source,
        "discrepancies": [],
        "suggestions": [],
    }
    result = app.invoke(state)
    report = result.get("report", {})
    report_json = report.get("report_json", {})
    report_markdown = report.get("report_markdown", "")
    return {
        "reply": _brief_report(report_json),
        "report_json": report_json,
        "report_markdown": report_markdown,
    }


def _help_text() -> str:
    return (
        "你可以这样和我对话：\n"
        "1) 输入“运行sample审计”触发内置示例审计；\n"
        "2) 输入“如何修复高风险问题”等规则咨询；\n"
        "3) 传入 payload.budget_source / payload.actual_source 做真实数据审计。"
    )


def _is_llm_enabled() -> bool:
    base_url = _get_llm_base_url()
    api_key = os.getenv("AGENT_LLM_API_KEY", "").strip()
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    return bool(api_key) or is_local


def _is_rag_trace_enabled() -> bool:
    try:
        from agent.config import get_rag_trace_config  # noqa: WPS433

        return bool(get_rag_trace_config().enabled)
    except Exception:
        return os.getenv("AGENT_RAG_TRACE_ENABLED", "1").strip().lower() in {"1", "true", "yes"}


def _get_rag_trace_dir() -> Path:
    try:
        from agent.config import get_rag_trace_config  # noqa: WPS433

        raw = get_rag_trace_config().trace_dir
    except Exception:
        raw = os.getenv("AGENT_RAG_TRACE_DIR", "").strip() or "data/eval/traces"

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    return path


def _trace_request_id(payload: Dict[str, Any]) -> str:
    raw = str(payload.get("request_id", "")).strip()
    return raw or uuid4().hex


def _write_rag_trace(
    *,
    request_id: str,
    status: str,
    message: str,
    contexts: List[Any],
    answer: str,
    latency_ms: int,
    mode: str,
    error: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    if not _is_rag_trace_enabled():
        return

    try:
        from agent.eval import RAGTraceStore, build_trace_record  # noqa: WPS433

        record = build_trace_record(
            request_id=request_id,
            status=status,
            question=message,
            contexts=contexts,
            answer=answer,
            latency_ms=latency_ms,
            mode=mode,
            error=error,
            meta=meta,
        )
        store = RAGTraceStore(base_dir=_get_rag_trace_dir())
        store.append(record)
    except Exception:
        return


def _get_kb_chunks(message: str) -> List[Any]:
    kb_path = Path(os.getenv("AGENT_KB_PATH", str(DEFAULT_KB_PATH))).resolve()
    top_k = _safe_int_env("AGENT_KB_TOP_K", 4, min_value=1)

    if not kb_path.exists():
        return []

    try:
        from agent.kb.retriever import retrieve_chunks  # noqa: WPS433
    except ModuleNotFoundError:
        return []

    try:
        return list(retrieve_chunks(message, kb_path=kb_path, top_k=top_k))
    except Exception:
        return []


def _format_kb_context(chunks: List[Any]) -> str:
    kb_path = Path(os.getenv("AGENT_KB_PATH", str(DEFAULT_KB_PATH))).resolve()
    max_chars = _safe_int_env("AGENT_KB_MAX_CHARS", 1800, min_value=600)

    if not kb_path.exists():
        return ""

    try:
        from agent.kb.retriever import format_retrieved_context  # noqa: WPS433
    except ModuleNotFoundError:
        return ""

    if not chunks:
        return ""

    try:
        return format_retrieved_context(chunks, max_chars=max_chars)
    except Exception:
        return ""


def _llm_chat(message: str, history: List[Dict[str, str]], kb_context: str = "") -> str:
    base_url = _get_llm_base_url()
    api_key = os.getenv("AGENT_LLM_API_KEY", "").strip()
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}

    if not api_key and not is_local:
        raise ValueError("未配置 AGENT_LLM_API_KEY。非本地 LLM 服务需要有效 API Key。")

    model = os.getenv("AGENT_LLM_MODEL", "gpt-4o-mini").strip()
    timeout_seconds = _safe_int_env("AGENT_LLM_TIMEOUT", 60, min_value=10)
    messages, _ = _build_llm_messages(message=message, history=history, kb_context=kb_context)

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        raise RuntimeError(f"LLM 接口请求失败: HTTP {exc.code} - {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 接口网络错误: {exc}") from exc

    choices = payload.get("choices", [])
    if not choices:
        raise RuntimeError("LLM 返回为空，未获取到回答。")

    content = choices[0].get("message", {}).get("content", "")
    text = str(content).strip()
    if not text:
        raise RuntimeError("LLM 返回内容为空。")
    return text


def _llm_chat_stream(message: str, history: List[Dict[str, str]], kb_context: str = "") -> Iterator[str]:
    base_url = _get_llm_base_url()
    api_key = os.getenv("AGENT_LLM_API_KEY", "").strip()
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}

    if not api_key and not is_local:
        raise ValueError("未配置 AGENT_LLM_API_KEY。非本地 LLM 服务需要有效 API Key。")

    model = os.getenv("AGENT_LLM_MODEL", "gpt-4o-mini").strip()
    timeout_seconds = _safe_int_env("AGENT_LLM_TIMEOUT", 60, min_value=10)
    messages, _ = _build_llm_messages(message=message, history=history, kb_context=kb_context)

    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": True,
    }

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break

                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = payload.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {}).get("content", "")
                text = str(delta)
                if text:
                    yield text
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
        raise RuntimeError(f"LLM 接口请求失败: HTTP {exc.code} - {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM 接口网络错误: {exc}") from exc


def _iter_text_chunks(text: str, chunk_size: int = 36) -> Iterator[str]:
    content = text or ""
    if not content:
        return
    for index in range(0, len(content), max(chunk_size, 8)):
        yield content[index : index + max(chunk_size, 8)]


def handle_request_stream(request: Dict[str, Any]) -> Iterator[Dict[str, Any]]: 
    message = str(request.get("message", "")).strip()
    raw_payload = request.get("payload", {}) or {}
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    request_id = _trace_request_id(payload)
    history = payload.get("history", []) if isinstance(payload, dict) else []
    safe_history = history if isinstance(history, list) else []

    yield {"type": "status", "status": "正在分析意图..."}
    rule_result = _rule_reply(message, payload)
    if rule_result is not None:
        yield {"type": "status", "status": "正在处理审计规则..."}
        reply = str(rule_result.get("reply", ""))
        report_markdown = str(rule_result.get("report_markdown", "") or "")     
        for chunk in _iter_text_chunks(reply):
            yield {"type": "delta", "delta": chunk}
        if report_markdown:
            yield {"type": "delta", "delta": f"\n\n{report_markdown}"}
        yield {"type": "done", "response": {"ok": True, **rule_result}}
        return

    if _is_llm_enabled():
        started = time.perf_counter()
        yield {"type": "status", "status": "正在调用 RAG 知识库检索..."}
        kb_chunks = _get_kb_chunks(message)
        kb_context = _format_kb_context(kb_chunks)
        yield {"type": "status", "status": "正在生成回答..."}
        streamed_reply = ""
        try:
            for chunk in _llm_chat_stream(message=message, history=safe_history, kb_context=kb_context):
                streamed_reply += chunk
                yield {"type": "delta", "delta": chunk}
        except Exception:
            try:
                streamed_reply = _llm_chat(message=message, history=safe_history, kb_context=kb_context)
                for chunk in _iter_text_chunks(streamed_reply):
                    yield {"type": "delta", "delta": chunk}
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                _write_rag_trace(
                    request_id=request_id,
                    status="error",
                    message=message,
                    contexts=kb_chunks,
                    answer=streamed_reply,
                    latency_ms=latency_ms,
                    mode="llm_stream",
                    error=str(exc),
                    meta={"stream": True, "fallback": "llm_chat"},
                )
                raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        _write_rag_trace(
            request_id=request_id,
            status="ok",
            message=message,
            contexts=kb_chunks,
            answer=streamed_reply,
            latency_ms=latency_ms,
            mode="llm_stream",
            meta={"stream": True},
        )
        yield {"type": "done", "response": {"ok": True, "reply": streamed_reply, "mode": "llm"}}                                                                        
        return

    reply = _help_text()
    for chunk in _iter_text_chunks(reply):
        yield {"type": "delta", "delta": chunk}
    yield {"type": "done", "response": {"ok": True, "reply": reply}}


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    message = str(request.get("message", "")).strip()
    raw_payload = request.get("payload", {}) or {}
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    request_id = _trace_request_id(payload)
    history = payload.get("history", []) if isinstance(payload, dict) else []
    safe_history = history if isinstance(history, list) else []

    rule_result = _rule_reply(message, payload)
    if rule_result is not None:
        return {"ok": True, **rule_result}

    if _is_llm_enabled():
        started = time.perf_counter()
        kb_chunks = _get_kb_chunks(message)
        kb_context = _format_kb_context(kb_chunks)
        try:
            llm_reply = _llm_chat(message=message, history=safe_history, kb_context=kb_context)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            _write_rag_trace(
                request_id=request_id,
                status="error",
                message=message,
                contexts=kb_chunks,
                answer="",
                latency_ms=latency_ms,
                mode="llm_sync",
                error=str(exc),
                meta={"stream": False},
            )
            raise

        latency_ms = int((time.perf_counter() - started) * 1000)
        _write_rag_trace(
            request_id=request_id,
            status="ok",
            message=message,
            contexts=kb_chunks,
            answer=llm_reply,
            latency_ms=latency_ms,
            mode="llm_sync",
            meta={"stream": False},
        )
        return {"ok": True, "reply": llm_reply, "mode": "llm"}

    return {"ok": True, "reply": _help_text()}


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"ok": False, "error": "empty input"}, ensure_ascii=False))
        return

    try:
        request = json.loads(raw)
        if bool(request.get("stream", False)):
            for event in handle_request_stream(request):
                print(json.dumps(event, ensure_ascii=False), flush=True)
            return
        response = handle_request(request)
        print(json.dumps(response, ensure_ascii=False))
    except Exception as exc:  # pragma: no cover
        if "request" in locals() and bool(request.get("stream", False)):
            print(json.dumps({"type": "error", "error": str(exc)}, ensure_ascii=False), flush=True)
            return
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
