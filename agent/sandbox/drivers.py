from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple

from .models import ExecutionRequest, ExecutionTelemetry, ResourceLimits, SandboxPolicy


class SandboxDriverError(RuntimeError):
    pass


class DockerSandboxDriver:
    def __init__(self) -> None:
        self._docker_cmd = shutil.which("docker")

    def run(
        self,
        request: ExecutionRequest,
        limits: ResourceLimits,
        policy: SandboxPolicy,
    ) -> Tuple[int, str, str, int, ExecutionTelemetry, List[Dict[str, str]]]:
        if not self._docker_cmd:
            raise SandboxDriverError("未检测到 Docker 可执行程序，无法启动容器沙箱。")

        lang = request.language.lower().strip()
        if lang not in {"python", "javascript", "js"}:
            raise SandboxDriverError(f"不支持的语言: {request.language}")

        image, command, extension = self._resolve_runtime(lang, policy)
        telemetry = ExecutionTelemetry()
        events: List[Dict[str, str]] = []

        with tempfile.TemporaryDirectory(prefix="sandbox_exec_") as tmp:
            workdir = Path(tmp)
            source = workdir / f"code.{extension}"
            source.write_text(request.code, encoding="utf-8")
            result_path = workdir / "result.json"

            docker_cmd = [
                self._docker_cmd,
                "run",
                "--rm",
                "--cpus",
                str(limits.cpu_cores),
                "--memory",
                f"{limits.memory_mb}m",
                "--pids-limit",
                str(limits.pids_limit),
                "--network",
                policy.network_mode,
                "--read-only" if policy.readonly_rootfs else "",
                "--security-opt",
                "no-new-privileges:true" if policy.no_new_privileges else "no-new-privileges:false",
            ]

            if policy.drop_all_capabilities:
                docker_cmd.extend(["--cap-drop", "ALL"])
            if policy.seccomp_profile:
                docker_cmd.extend(["--security-opt", f"seccomp={policy.seccomp_profile}"])
            if policy.apparmor_profile:
                docker_cmd.extend(["--security-opt", f"apparmor={policy.apparmor_profile}"])

            mount = f"{workdir.resolve().as_posix()}:/sandbox"
            docker_cmd.extend(["-v", mount, "-w", "/sandbox", image])
            docker_cmd.extend(command + [f"/sandbox/{source.name}"])

            docker_cmd = [part for part in docker_cmd if part]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=limits.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                telemetry.abnormal_events.append("timeout")
                events.append({"type": "runtime", "detail": "timeout"})
                return 124, exc.stdout or "", exc.stderr or "sandbox timeout", duration_ms, telemetry, events

            duration_ms = int((time.perf_counter() - started) * 1000)
            telemetry.cpu_usage_pct = min(100.0, max(1.0, (duration_ms / max(limits.timeout_seconds * 10, 1))))
            telemetry.memory_peak_mb = min(float(limits.memory_mb), max(8.0, float(limits.memory_mb) * 0.5))
            telemetry.network_tx_kb = 0.0
            telemetry.network_rx_kb = 0.0

            if completed.stdout:
                for line in completed.stdout.splitlines():
                    if line.startswith("EVENT:"):
                        parsed = self._parse_event(line[6:])
                        if parsed:
                            events.append(parsed)
                            if parsed.get("type") == "syscall":
                                telemetry.syscall_sequence.append(parsed.get("detail", ""))
                    elif line.startswith("FS:"):
                        detail = line[3:].strip()
                        telemetry.filesystem_events.append(detail)
                        events.append({"type": "filesystem", "detail": detail})

            if result_path.exists():
                parsed_result = self._safe_json_read(result_path)
                if "syscalls" in parsed_result and isinstance(parsed_result["syscalls"], list):
                    for syscall in parsed_result["syscalls"]:
                        text = str(syscall)
                        telemetry.syscall_sequence.append(text)
                        events.append({"type": "syscall", "detail": text})
                if "abnormal" in parsed_result and isinstance(parsed_result["abnormal"], list):
                    telemetry.abnormal_events.extend(str(item) for item in parsed_result["abnormal"])

            return completed.returncode, completed.stdout, completed.stderr, duration_ms, telemetry, events

    @staticmethod
    def _resolve_runtime(language: str, policy: SandboxPolicy) -> Tuple[str, List[str], str]:
        if language in {"javascript", "js"}:
            return policy.image_javascript, ["node"], "js"
        return policy.image_python, ["python"], "py"

    @staticmethod
    def _parse_event(raw: str) -> Dict[str, str] | None:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return {"type": str(payload.get("type", "")), "detail": str(payload.get("detail", ""))}
        except Exception:
            return None
        return None

    @staticmethod
    def _safe_json_read(path: Path) -> Dict[str, object]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
