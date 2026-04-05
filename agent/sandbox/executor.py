from __future__ import annotations

from typing import Dict, List

from .models import ExecutionRequest, ResourceLimits, SandboxPolicy
from .orchestrator import SandboxOrchestrator


def execute_untrusted_code(
    *,
    user_id: str,
    language: str,
    code: str,
    args: List[str] | None = None,
    env: Dict[str, str] | None = None,
    metadata: Dict[str, object] | None = None,
    limits: ResourceLimits | None = None,
    policy: SandboxPolicy | None = None,
) -> Dict[str, object]:
    orchestrator = SandboxOrchestrator(policy=policy, limits=limits)
    request = ExecutionRequest(
        user_id=user_id,
        language=language,
        code=code,
        args=args or [],
        env=env or {},
        metadata=metadata or {},
    )
    result = orchestrator.execute(request)
    return {
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "blocked_reason": result.blocked_reason,
        "code_hash": result.code_hash,
        "signature": result.signature,
        "audit_log_path": result.audit_log_path,
        "telemetry": {
            "cpu_usage_pct": result.telemetry.cpu_usage_pct,
            "memory_peak_mb": result.telemetry.memory_peak_mb,
            "network_tx_kb": result.telemetry.network_tx_kb,
            "network_rx_kb": result.telemetry.network_rx_kb,
            "filesystem_events": result.telemetry.filesystem_events,
            "syscall_sequence": result.telemetry.syscall_sequence,
            "abnormal_events": result.telemetry.abnormal_events,
        },
    }
