from __future__ import annotations

from agent.graphs.state import AppState
from agent.sandbox import execute_untrusted_code
from agent.sandbox.models import ResourceLimits, SandboxPolicy


def sandbox_start_node(state: AppState) -> AppState:
    return {"task_progress": state.get("task_progress", []) + [{"step": "sandbox_start", "tool_name": "start"}]}


def sandbox_execute_node(state: AppState) -> AppState:
    payload = state.get("payload", {})
    limits = ResourceLimits(
        cpu_cores=float(payload.get("cpu_cores", 1.0)),
        memory_mb=int(payload.get("memory_mb", 512)),
        disk_mb=int(payload.get("disk_mb", 256)),
        network_kbps=int(payload.get("network_kbps", 256)),
        timeout_seconds=int(payload.get("timeout_seconds", 8)),
    )
    policy = SandboxPolicy(
        technology=str(payload.get("technology", "docker")),
        network_mode=str(payload.get("network_mode", "none")),
        seccomp_profile=payload.get("seccomp_profile"),
        apparmor_profile=payload.get("apparmor_profile"),
        syscall_whitelist=list(payload.get("syscall_whitelist", [])),
    )
    result = execute_untrusted_code(
        user_id=str(payload.get("user_id", "anonymous")),
        language=str(payload.get("language", "python")),
        code=str(payload.get("code", "")),
        args=list(payload.get("args", [])),
        env=dict(payload.get("env", {})),
        metadata=dict(payload.get("metadata", {})),
        limits=limits,
        policy=policy,
    )
    return {
        "result": {"type": "sandbox_exec", **result},
        "outputs": {**state.get("outputs", {}), "sandbox": result},
        "task_progress": state.get("task_progress", []) + [{"step": "sandbox_execute", "tool_name": "execute_untrusted_code"}],
    }
