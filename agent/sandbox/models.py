from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ResourceLimits:
    cpu_cores: float = 1.0
    memory_mb: int = 512
    disk_mb: int = 256
    network_kbps: int = 256
    pids_limit: int = 64
    timeout_seconds: int = 8


@dataclass(frozen=True)
class SandboxPolicy:
    technology: str = "docker"
    image_python: str = "python:3.11-alpine"
    image_javascript: str = "node:20-alpine"
    network_mode: str = "none"
    seccomp_profile: Optional[str] = None
    apparmor_profile: Optional[str] = None
    drop_all_capabilities: bool = True
    no_new_privileges: bool = True
    readonly_rootfs: bool = True
    syscall_whitelist: List[str] = field(default_factory=list)
    sensitive_apis: List[str] = field(
        default_factory=lambda: ["os.system", "subprocess", "socket", "ctypes", "winreg", "eval", "exec"]
    )


@dataclass(frozen=True)
class ExecutionRequest:
    user_id: str
    language: str
    code: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityFinding:
    rule_id: str
    severity: str
    message: str
    offset: int


@dataclass
class ScanResult:
    passed: bool
    findings: List[SecurityFinding] = field(default_factory=list)


@dataclass
class ExecutionTelemetry:
    cpu_usage_pct: float = 0.0
    memory_peak_mb: float = 0.0
    network_tx_kb: float = 0.0
    network_rx_kb: float = 0.0
    filesystem_events: List[str] = field(default_factory=list)
    syscall_sequence: List[str] = field(default_factory=list)
    abnormal_events: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    status: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    code_hash: str
    signature: str
    blocked_reason: str = ""
    audit_log_path: str = ""
    telemetry: ExecutionTelemetry = field(default_factory=ExecutionTelemetry)
