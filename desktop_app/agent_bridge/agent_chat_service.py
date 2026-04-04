from __future__ import annotations

import errno
import json
import os
import re
import signal
import sys
import textwrap
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

CURRENT_FILE = Path(__file__).resolve()


def _resolve_project_root() -> Path:
    env_root = os.getenv("AGENT_PROJECT_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if candidate.exists():
            return candidate

    for parent in (CURRENT_FILE, *CURRENT_FILE.parents):
        agent_dir = parent / "agent" / "__init__.py"
        data_dir = parent / "data"
        if agent_dir.exists() and data_dir.exists():
            return parent

    if len(CURRENT_FILE.parents) >= 3:
        return CURRENT_FILE.parents[2]
    return CURRENT_FILE.parent


# 将仓库根目录加入 sys.path，便于导入已有 reimbursement_agent 包
PROJECT_ROOT = _resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SYSTEM_PROMPT = (
    "你是企业报销审计助手。"
    "请优先使用简洁、准确、可执行的中文回答；"
    "若用户询问报销审计规则，请结合常见合规点给出建议；"
    "若问题超出报销场景，也可进行通用问答。"
)

DEFAULT_KB_PATH = PROJECT_ROOT / "data" / "kb" / "reimbursement_kb.json"

WORKSPACE_SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
}


def _safe_workspace_root(payload: Dict[str, Any]) -> Optional[Path]:
    workspace_raw = str(payload.get("workspace_dir", "")).strip()
    if not workspace_raw:
        return None
    try:
        root = Path(workspace_raw).expanduser().resolve()
    except Exception:
        return None
    if not root.exists() or not root.is_dir():
        return None
    return root


def _safe_workspace_target(root: Path, relative_path: str) -> Path:
    rel = str(relative_path or "").strip().replace("\\", "/")
    if not rel:
        raise ValueError("路径不能为空")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("禁止访问目录外路径") from exc
    return target


def _workspace_tree_text(root: Path, *, max_files: int = 120) -> str:
    rows: List[str] = []
    count = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in WORKSPACE_SKIP_DIRS and not d.startswith(".")]
        rel_dir = Path(current).resolve().relative_to(root)
        rel_prefix = "" if str(rel_dir) == "." else str(rel_dir).replace("\\", "/") + "/"
        for name in sorted(files):
            if name.startswith("."):
                continue
            rows.append(rel_prefix + name)
            count += 1
            if count >= max_files:
                rows.append("... (更多文件已省略)")
                return "\n".join(rows)
    return "\n".join(rows) if rows else "(空目录)"


def _workspace_read(root: Path, relative_path: str) -> str:
    target = _safe_workspace_target(root, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"文件不存在: {relative_path}")
    return target.read_text(encoding="utf-8")


def _workspace_write(root: Path, relative_path: str, content: str) -> None:
    target = _safe_workspace_target(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _workspace_append(root: Path, relative_path: str, content: str) -> None:
    target = _safe_workspace_target(root, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(content)


def _workspace_replace(root: Path, relative_path: str, old: str, new: str) -> int:
    source = _workspace_read(root, relative_path)
    if old not in source:
        return 0
    updated = source.replace(old, new)
    _workspace_write(root, relative_path, updated)
    return source.count(old)


def _extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    candidates = re.findall(r"\{[\s\S]*\}", text)
    for block in reversed(candidates):
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _workspace_execute_actions(root: Path, actions: List[Dict[str, Any]]) -> List[str]:
    logs: List[str] = []
    for item in actions[:12]:
        action = str(item.get("action", "")).strip()
        rel = str(item.get("path", "")).strip()
        if action == "list_files":
            logs.append("[list_files] 已生成目录树")
            continue
        if action == "read_file":
            content = _workspace_read(root, rel)
            preview = content[:600]
            logs.append(f"[read_file] {rel}\n{preview}")
            continue
        if action == "write_file":
            content = str(item.get("content", ""))
            _workspace_write(root, rel, content)
            logs.append(f"[write_file] {rel} ({len(content)} chars)")
            continue
        if action == "append_file":
            content = str(item.get("content", ""))
            _workspace_append(root, rel, content)
            logs.append(f"[append_file] {rel} (+{len(content)} chars)")
            continue
        if action == "replace_text":
            old = str(item.get("old", ""))
            new = str(item.get("new", ""))
            replaced = _workspace_replace(root, rel, old, new)
            logs.append(f"[replace_text] {rel} replacements={replaced}")
            continue
        logs.append(f"[skip] 未知 action: {action}")
    return logs


def _parse_workspace_command(message: str) -> Optional[Dict[str, Any]]:
    text = message.strip()
    if text.startswith("/list"):
        return {"reply": "目录如下：", "actions": [{"action": "list_files"}]}

    if text.startswith("/read "):
        rel = text[6:].strip()
        return {"reply": f"读取文件: {rel}", "actions": [{"action": "read_file", "path": rel}]}

    if text.startswith("/write "):
        lines = text.splitlines()
        rel = lines[0][7:].strip()
        content = "\n".join(lines[1:])
        return {
            "reply": f"写入文件: {rel}",
            "actions": [{"action": "write_file", "path": rel, "content": content}],
        }

    if text.startswith("/append "):
        lines = text.splitlines()
        rel = lines[0][8:].strip()
        content = "\n".join(lines[1:])
        return {
            "reply": f"追加文件: {rel}",
            "actions": [{"action": "append_file", "path": rel, "content": content}],
        }

    if text.startswith("/replace "):
        lines = text.splitlines()
        rel = lines[0][9:].strip()
        body = "\n".join(lines[1:])
        marker_old = "---OLD---"
        marker_new = "---NEW---"
        if marker_old in body and marker_new in body:
            old_part = body.split(marker_old, 1)[1]
            old_text, new_text = old_part.split(marker_new, 1)
            return {
                "reply": f"替换文件: {rel}",
                "actions": [
                    {
                        "action": "replace_text",
                        "path": rel,
                        "old": old_text.strip("\n"),
                        "new": new_text.strip("\n"),
                    }
                ],
            }
    return None


def _run_workspace_agent(message: str, payload: Dict[str, Any], history: List[Dict[str, str]]) -> Dict[str, Any]:
    workspace_root = _safe_workspace_root(payload)
    if workspace_root is None:
        return {
            "ok": False,
            "error": "未绑定有效目录，请先拖拽文件夹到桌宠后再对话。",
        }

    directory_tree = _workspace_tree_text(workspace_root)

    command_plan = _parse_workspace_command(message)
    if command_plan is not None:
        logs = _workspace_execute_actions(workspace_root, command_plan.get("actions", []))
        if command_plan.get("actions") and command_plan["actions"][0].get("action") == "list_files":
            return {
                "ok": True,
                "reply": f"{command_plan['reply']}\n\n{directory_tree}",
                "mode": "workspace",
            }
        return {
            "ok": True,
            "reply": f"{command_plan['reply']}\n\n" + "\n\n".join(logs),
            "mode": "workspace",
        }

    if _is_llm_enabled():
        recent_history = history[-8:] if history else []
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}" for item in recent_history
        )
        planner_prompt = textwrap.dedent(
            f"""
            你是本地代码编辑代理，需要在指定目录内操作文件。
            目录根路径: {workspace_root}
            当前目录树（节选）:
            {directory_tree}

            对话历史（最近）:
            {history_text or '(无)'}

            用户请求:
            {message}

            请仅返回 JSON 对象，不要加解释文字。格式：
            {{
              "reply": "给用户的简短说明",
              "actions": [
                {{"action": "list_files"}},
                {{"action": "read_file", "path": "relative/path"}},
                {{"action": "write_file", "path": "relative/path", "content": "..."}},
                {{"action": "append_file", "path": "relative/path", "content": "..."}},
                {{"action": "replace_text", "path": "relative/path", "old": "...", "new": "..."}}
              ]
            }}

            规则：
            1) path 必须是相对路径。
            2) 若需要改文件，优先 replace_text；若文件不存在再 write_file。
            3) 若用户只是询问，则 actions 可为空。
            """
        ).strip()

        planner_raw = _llm_chat(message=planner_prompt, history=[], kb_context="")
        parsed = _extract_json_block(planner_raw)
        if parsed is None:
            return {
                "ok": True,
                "reply": planner_raw,
                "mode": "workspace",
            }

        actions = parsed.get("actions", [])
        safe_actions = [item for item in actions if isinstance(item, dict)] if isinstance(actions, list) else []
        logs = _workspace_execute_actions(workspace_root, safe_actions)

        if any(str(item.get("action", "")).strip() == "list_files" for item in safe_actions):
            logs.append(directory_tree)

        reply = str(parsed.get("reply", "已完成目录操作。"))
        if logs:
            reply += "\n\n" + "\n\n".join(logs)
        return {
            "ok": True,
            "reply": reply,
            "mode": "workspace",
        }

    return {
        "ok": True,
        "mode": "workspace",
        "reply": (
            "当前未启用 LLM 规划。可用命令：\n"
            "/list\n"
            "/read 相对路径\n"
            "/write 相对路径 + 换行后文件内容\n"
            "/append 相对路径 + 换行后追加内容\n"
            "/replace 相对路径 + 换行后使用 ---OLD--- 与 ---NEW--- 标记"
        ),
    }


def _extract_task_request(message: str, payload: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
    task_type = str(payload.get("task_type", "")).strip().lower()
    task_payload = payload.get("task_payload", payload)
    if isinstance(task_payload, dict) and task_type:
        return task_type, task_payload

    if message.startswith("/task "):
        parts = message.split(maxsplit=2)
        task_type = parts[1].strip().lower() if len(parts) > 1 else ""
        if task_type:
            return task_type, payload

    return None, payload


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


def _run_v2_task(task_type: str, task_payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from agent import EventBus, TaskDispatcher  # noqa: WPS433
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "任务调度模式依赖缺失，请确认已安装项目依赖并同步到当前 Python 环境。"
        ) from exc

    event_bus = EventBus()
    progress_events: List[Dict[str, Any]] = []
    event_bus.subscribe("task_progress", lambda evt: progress_events.append(evt))
    dispatcher = TaskDispatcher(event_bus)
    result = dispatcher.dispatch(task_type, task_payload)
    return {
        "reply": f"任务已完成：{task_type}",
        "mode": "task",
        "task_type": task_type,
        "task_result": result,
        "task_progress": progress_events,
    }


def _help_text() -> str:
    return (
        "你可以这样和我对话：\n"
        "1) 输入“运行sample审计”触发内置示例审计；\n"
        "2) 输入“如何修复高风险问题”等规则咨询；\n"
        "3) 传入 payload.budget_source / payload.actual_source 做真实数据审计；\n"
        "4) 传入 payload.task_type（qa/reimburse/final_account/budget）触发新图任务。"
        "\n5) 传入 payload.workspace_mode=true + payload.workspace_dir 使用目录编辑工具模式。"
    )


def _is_llm_enabled() -> bool:
    base_url = _get_llm_base_url()
    api_key = os.getenv("AGENT_LLM_API_KEY", "").strip()
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    return bool(api_key) or is_local


def _get_kb_context(message: str) -> str:
    kb_path = Path(os.getenv("AGENT_KB_PATH", str(DEFAULT_KB_PATH))).resolve()
    top_k = _safe_int_env("AGENT_KB_TOP_K", 4, min_value=1)
    max_chars = _safe_int_env("AGENT_KB_MAX_CHARS", 1800, min_value=600)

    if not kb_path.exists():
        return ""

    try:
        from agent.kb.retriever import format_retrieved_context, retrieve_chunks  # noqa: WPS433
    except ModuleNotFoundError:
        return ""

    try:
        chunks = retrieve_chunks(message, kb_path=kb_path, top_k=top_k)
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
    history = payload.get("history", []) if isinstance(payload, dict) else []
    safe_history = history if isinstance(history, list) else []

    if bool(payload.get("workspace_mode", False)):
        yield {"type": "status", "status": "正在处理目录编辑任务..."}
        workspace_result = _run_workspace_agent(message, payload, safe_history)
        if not workspace_result.get("ok", True):
            yield {"type": "error", "error": str(workspace_result.get("error", "目录任务失败"))}
            return
        reply = str(workspace_result.get("reply", "已处理"))
        for chunk in _iter_text_chunks(reply):
            yield {"type": "delta", "delta": chunk}
        yield {"type": "done", "response": {"ok": True, **workspace_result}}
        return

    task_type, task_payload = _extract_task_request(message, payload)
    if task_type:
        yield {"type": "status", "status": f"正在执行任务: {task_type}"}
        task_resp = _run_v2_task(task_type, task_payload)
        for step in task_resp.get("task_progress", []):
            step_name = str(step.get("step", ""))
            tool_name = str(step.get("tool_name", ""))
            yield {"type": "status", "status": f"步骤: {step_name} | Tool: {tool_name}"}
        reply = str(task_resp.get("reply", "任务完成"))
        for chunk in _iter_text_chunks(reply):
            yield {"type": "delta", "delta": chunk}
        yield {"type": "done", "response": {"ok": True, **task_resp}}
        return

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
        yield {"type": "status", "status": "正在调用 RAG 知识库检索..."}
        kb_context = _get_kb_context(message)
        yield {"type": "status", "status": "正在生成回答..."}
        streamed_reply = ""
        try:
            for chunk in _llm_chat_stream(message=message, history=safe_history, kb_context=kb_context):
                streamed_reply += chunk
                yield {"type": "delta", "delta": chunk}
        except Exception:
            streamed_reply = _llm_chat(message=message, history=safe_history, kb_context=kb_context)
            for chunk in _iter_text_chunks(streamed_reply):
                yield {"type": "delta", "delta": chunk}

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
    history = payload.get("history", []) if isinstance(payload, dict) else []
    safe_history = history if isinstance(history, list) else []

    if bool(payload.get("workspace_mode", False)):
        return _run_workspace_agent(message, payload, safe_history)

    task_type, task_payload = _extract_task_request(message, payload)
    if task_type:
        return {"ok": True, **_run_v2_task(task_type, task_payload)}

    rule_result = _rule_reply(message, payload)
    if rule_result is not None:
        return {"ok": True, **rule_result}

    if _is_llm_enabled():
        kb_context = _get_kb_context(message)
        llm_reply = _llm_chat(message=message, history=safe_history, kb_context=kb_context)
        return {"ok": True, "reply": llm_reply, "mode": "llm"}

    return {"ok": True, "reply": _help_text()}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            continue


def _safe_write_line(line: str) -> bool:
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
        return True
    except BrokenPipeError:
        return False
    except OSError as exc:
        if exc.errno in {errno.EPIPE, errno.ECONNRESET}:
            return False
        raise


def _emit_json(payload: Dict[str, Any]) -> bool:
    return _safe_write_line(json.dumps(payload, ensure_ascii=False))


def _handle_request_payload(request: Dict[str, Any]) -> bool:
    if request.get("command") == "shutdown":
        _emit_json({"type": "status", "status": "shutdown"})
        return False

    if bool(request.get("stream", False)):
        for event in handle_request_stream(request):
            if not _emit_json(event):
                return False
        return True

    response = handle_request(request)
    return _emit_json(response)


def _handle_raw_request(raw: str) -> bool:
    if not raw:
        return True
    try:
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise ValueError("request payload must be a JSON object")
        return _handle_request_payload(request)
    except Exception as exc:  # pragma: no cover
        if "request" in locals() and isinstance(request, dict) and bool(request.get("stream", False)):
            return _emit_json({"type": "error", "error": str(exc)})
        return _emit_json({"ok": False, "error": str(exc)})


def main() -> None:
    _configure_stdio()

    shutdown_requested = {"value": False}

    def _request_shutdown(signum: int, frame: Any) -> None:
        shutdown_requested["value"] = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _request_shutdown)
        except Exception:
            continue

    for raw_line in sys.stdin:
        if shutdown_requested["value"]:
            break
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        if not _handle_raw_request(raw_line):
            break


if __name__ == "__main__":
    main()
