from __future__ import annotations

from typing import Any, Dict, Iterable


def get_graph_policy(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    policy = payload.get("graph_policy", {})
    return policy if isinstance(policy, dict) else {}


def get_policy_value(
    payload: Dict[str, Any] | None,
    key: str,
    default: Any,
    *,
    legacy_keys: Iterable[str] = (),
) -> Any:
    if isinstance(payload, dict):
        policy = get_graph_policy(payload)
        if key in policy:
            return policy[key]
        for legacy_key in legacy_keys:
            if legacy_key in payload:
                return payload[legacy_key]
    return default


def get_bool_policy(
    payload: Dict[str, Any] | None,
    key: str,
    default: bool,
    *,
    legacy_keys: Iterable[str] = (),
) -> bool:
    value = get_policy_value(payload, key, default, legacy_keys=legacy_keys)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def get_int_policy(
    payload: Dict[str, Any] | None,
    key: str,
    default: int,
    *,
    min_value: int = 1,
    legacy_keys: Iterable[str] = (),
) -> int:
    value = get_policy_value(payload, key, default, legacy_keys=legacy_keys)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, parsed)
