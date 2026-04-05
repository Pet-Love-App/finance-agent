from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Set

from .models import SandboxPolicy


@dataclass
class RiskDecision:
    blocked: bool
    reason: str = ""


class RuntimeRiskDetector:
    def __init__(self, policy: SandboxPolicy) -> None:
        self._policy = policy
        self._allowed_syscalls: Set[str] = set(policy.syscall_whitelist)

    def inspect(self, event: Dict[str, str]) -> RiskDecision:
        event_type = str(event.get("type", "")).strip()
        detail = str(event.get("detail", "")).strip()

        if event_type == "syscall" and self._allowed_syscalls and detail and detail not in self._allowed_syscalls:
            return RiskDecision(blocked=True, reason=f"系统调用不在白名单: {detail}")

        if event_type == "filesystem" and (".." in detail or detail.startswith("/etc") or detail.startswith("/proc")):
            return RiskDecision(blocked=True, reason=f"文件系统越权访问: {detail}")

        if event_type == "network" and detail:
            return RiskDecision(blocked=True, reason=f"检测到外联行为: {detail}")

        if event_type == "process" and detail:
            return RiskDecision(blocked=True, reason=f"检测到子进程创建: {detail}")

        if event_type == "api" and self._contains_sensitive_api(detail, self._policy.sensitive_apis):
            return RiskDecision(blocked=True, reason=f"检测到敏感 API 调用: {detail}")

        return RiskDecision(blocked=False)

    @staticmethod
    def _contains_sensitive_api(candidate: str, sensitive_apis: Iterable[str]) -> bool:
        lowered = candidate.lower()
        return any(token.lower() in lowered for token in sensitive_apis)
