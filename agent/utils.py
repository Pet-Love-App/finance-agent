from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .schemas import CATEGORY_SYNONYMS
import os
from typing import Iterable
import urllib.request
import urllib.error

try:
    # prefer dotenv if available to load .env into environment
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

if load_dotenv is not None:
    # Load default .env if present
    load_dotenv()
    # If user placed .env under desktop_app/.env, try loading it as a fallback
    # agent/utils.py -> parent is finance-agent directory
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    desktop_env = os.path.join(base_dir, "desktop_app", ".env")
    if os.path.exists(desktop_env):
        load_dotenv(desktop_env)
try:
    from jsonschema import ValidationError, validate
except Exception:  # pragma: no cover
    ValidationError = ValueError
    validate = None


def safe_load_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"输入不是合法 JSON: {exc}") from exc
    raise TypeError("仅支持 dict 或 JSON 字符串作为输入")


def validate_payload_schema(payload: Dict[str, Any], schema: Dict[str, Any], label: str) -> None:
    if validate is not None:
        try:
            validate(instance=payload, schema=schema)
        except ValidationError as exc:
            path = ".".join(str(item) for item in getattr(exc, "absolute_path", [])) or "<root>"
            raise ValueError(f"{label} 字段校验失败: {path} - {exc.message}") from exc
        return
    if not isinstance(payload, dict):
        raise ValueError(f"{label} 必须是对象")
    if "items" not in payload or not isinstance(payload["items"], list):
        raise ValueError(f"{label} 缺少 items 数组")


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def append_discrepancy(
    state_items: List[Dict[str, Any]],
    *,
    issue_type: str,
    risk: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"type": issue_type, "risk": risk, "message": message}
    if details:
        payload["details"] = details
        payload.update(details)
    state_items.append(payload)


def dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_budget_alias_map(budget_df: pd.DataFrame) -> Dict[str, str]:
    alias_map: Dict[str, str] = {}
    for _, row in budget_df.iterrows():
        category = row["category"]
        alias_map[normalize_text(category)] = category

        aliases = row.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                alias_map[normalize_text(str(alias))] = category

    for alias, category in CATEGORY_SYNONYMS.items():
        alias_map[normalize_text(alias)] = category

    return alias_map


def fuzzy_align_category(
    expense_type: str,
    claimed_category: str,
    budget_categories: List[str],
    alias_map: Dict[str, str],
) -> Tuple[Optional[str], str]:
    from difflib import get_close_matches

    claimed_norm = normalize_text(claimed_category)
    expense_norm = normalize_text(expense_type)

    if claimed_norm in alias_map:
        return alias_map[claimed_norm], "exact_claimed"
    if expense_norm in alias_map:
        return alias_map[expense_norm], "exact_expense"

    for key, mapped_category in alias_map.items():
        if key and key in claimed_norm:
            return mapped_category, "contain_claimed"
    for key, mapped_category in alias_map.items():
        if key and key in expense_norm:
            return mapped_category, "contain_expense"

    budget_norm_to_raw = {normalize_text(category): category for category in budget_categories}
    budget_norm_keys = list(budget_norm_to_raw.keys())

    claim_hits = get_close_matches(claimed_norm, budget_norm_keys, n=1, cutoff=0.55)
    if claim_hits:
        return budget_norm_to_raw[claim_hits[0]], "fuzzy_claimed"

    expense_hits = get_close_matches(expense_norm, budget_norm_keys, n=1, cutoff=0.55)
    if expense_hits:
        return budget_norm_to_raw[expense_hits[0]], "fuzzy_expense"

    return None, "unmatched"


def _call_openai_chat(messages: List[Dict[str, str]], model: str, temperature: float, api_key: Optional[str] = None, timeout: int = 15) -> str:
    # allow overriding endpoint via env var (e.g., self-hosted or vendor URL)
    url = os.getenv("OPENAI_API_URL") or os.getenv("AGENT_LLM_API_URL") or "https://api.openai.com/v1/chat/completions"
    # if user provided only base host (no path), append standard chat completions path
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if not parsed.path or parsed.path == "/":
            parsed = parsed._replace(path="/v1/chat/completions")
            url = urlunparse(parsed)
    except Exception:
        pass
    payload = json.dumps({"model": model, "messages": messages, "temperature": float(temperature)}, ensure_ascii=False)
    req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AGENT_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM API key not set in environment (.env accepted). Set OPENAI_API_KEY or AGENT_LLM_API_KEY.")
    req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM request failed: {exc.code} {exc.reason}") from exc
    try:
        parsed = json.loads(body)
        # Chat Completions response shape: choices[0].message.content
        return parsed["choices"][0]["message"]["content"]
    except Exception:
        # fallback to raw body
        return body


def llm_align_category_for_items(
    items: Iterable[Dict[str, Any]],
    budget_categories: List[str],
    model: str,
    temperature: float = 0.0,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Ask an LLM to re-evaluate expected categories for a list of items.

    Each input item should contain at least: index (optional), expense_type, claimed_category, matched_category, amount.
    Returns a list of dicts with keys: index, suggested_category (or null), reason.
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AGENT_LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM API key not set for LLM checks. Set OPENAI_API_KEY or AGENT_LLM_API_KEY.")

    budget_text = ", ".join(budget_categories) if budget_categories else "(no budget categories)"

    items_list = []
    for i, it in enumerate(items):
        items_list.append(
            {
                "index": int(it.get("_index", i)),
                "expense_type": it.get("expense_type", ""),
                "claimed_category": it.get("claimed_category", ""),
                "matched_category": it.get("matched_category", ""),
                "amount": float(it.get("amount", 0.0) or 0.0),
            }
        )

    system = (
        "You are a concise financial auditor assistant. Given an expense description and the project's budget categories, "
        "suggest the most appropriate budget category if the provided mapping seems incorrect. Output only valid JSON: "
        "a list of objects with keys: index (int), suggested_category (string or null), reason (string). Keep answers short."
    )

    user = {
        "text": f"Budget categories: {budget_text}\n\nItems: {json.dumps(items_list, ensure_ascii=False)}\n\nReturn JSON only."
    }

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user["text"]}]

    raw = _call_openai_chat(messages=messages, model=model, temperature=temperature, api_key=api_key)
    # Optional debug logging controlled by env var
    if os.getenv("AGENT_LLM_DEBUG", "").lower() in ("1", "true", "yes"):
        try:
            print("[LLM DEBUG] Messages:", messages)
            print("[LLM DEBUG] Raw response:", raw)
        except Exception:
            pass

    try:
        return json.loads(raw)
    except Exception:
        # If parsing failed, return empty list signaling no LLM suggestions
        return []
