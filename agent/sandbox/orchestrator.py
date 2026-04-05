from __future__ import annotations

from typing import Dict, List

from .audit import AuditLogger
from .drivers import DockerSandboxDriver, SandboxDriverError
from .models import ExecutionRequest, ExecutionResult, ExecutionTelemetry, ResourceLimits, SandboxPolicy
from .policy import CircuitBreaker
from .risk import RuntimeRiskDetector
from .scanner import StaticSecurityScanner
from .signing import hash_code, sign_code, verify_signature


class SandboxOrchestrator:
    def __init__(
        self,
        policy: SandboxPolicy | None = None,
        limits: ResourceLimits | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.policy = policy or SandboxPolicy()
        self.limits = limits or ResourceLimits()
        self.breaker = breaker or CircuitBreaker()
        self.scanner = StaticSecurityScanner()
        self.risk_detector = RuntimeRiskDetector(self.policy)
        self.driver = DockerSandboxDriver()
        self.audit = AuditLogger()

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        code_hash = hash_code(request.code)
        if not self.breaker.allow():
            return self._deny_result(
                request=request,
                code_hash=code_hash,
                reason="沙箱熔断器已开启，请稍后重试。",
            )

        scan = self.scanner.scan(request.code)
        if not scan.passed:
            findings = ", ".join(f"{item.rule_id}:{item.severity}" for item in scan.findings[:5])
            self.breaker.record_failure()
            return self._deny_result(
                request=request,
                code_hash=code_hash,
                reason=f"静态扫描未通过: {findings}",
            )

        code_hash, signature = sign_code(request.code, request.metadata)
        if not verify_signature(code_hash, request.metadata, signature):
            self.breaker.record_failure()
            return self._deny_result(
                request=request,
                code_hash=code_hash,
                reason="代码签名校验失败。",
            )

        try:
            exit_code, stdout, stderr, duration_ms, telemetry, events = self.driver.run(
                request=request,
                limits=self.limits,
                policy=self.policy,
            )
        except SandboxDriverError as exc:
            self.breaker.record_failure()
            return self._deny_result(request, code_hash, str(exc), signature=signature)

        blocked_reason = self._inspect_runtime_events(events, telemetry)
        status = "blocked" if blocked_reason else ("success" if exit_code == 0 else "failed")
        if status == "success":
            self.breaker.record_success()
        else:
            self.breaker.record_failure()

        result = ExecutionResult(
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            code_hash=code_hash,
            signature=signature,
            blocked_reason=blocked_reason,
            telemetry=telemetry,
        )
        result.audit_log_path = self._write_audit_log(request=request, result=result, events=events)
        return result

    def _inspect_runtime_events(self, events: List[Dict[str, str]], telemetry: ExecutionTelemetry) -> str:
        for event in events:
            decision = self.risk_detector.inspect(event)
            if decision.blocked:
                telemetry.abnormal_events.append(decision.reason)
                return decision.reason
        return ""

    def _write_audit_log(
        self,
        request: ExecutionRequest,
        result: ExecutionResult,
        events: List[Dict[str, str]],
    ) -> str:
        return self.audit.append(
            {
                "user_id": request.user_id,
                "language": request.language,
                "code_hash": result.code_hash,
                "signature": result.signature,
                "status": result.status,
                "exit_code": result.exit_code,
                "execution_duration_ms": result.duration_ms,
                "syscall_sequence": result.telemetry.syscall_sequence,
                "abnormal_events": result.telemetry.abnormal_events,
                "runtime_events": events[:100],
                "metadata": request.metadata,
            }
        )

    def _deny_result(
        self,
        request: ExecutionRequest,
        code_hash: str,
        reason: str,
        signature: str = "",
    ) -> ExecutionResult:
        denied = ExecutionResult(
            status="denied",
            exit_code=126,
            stdout="",
            stderr=reason,
            duration_ms=0,
            code_hash=code_hash,
            signature=signature,
            blocked_reason=reason,
        )
        denied.audit_log_path = self._write_audit_log(request, denied, events=[])
        return denied
