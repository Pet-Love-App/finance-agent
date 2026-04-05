from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.sandbox.audit import AuditLogger
from agent.sandbox.executor import execute_untrusted_code
from agent.sandbox.models import ExecutionRequest, ExecutionTelemetry, ResourceLimits, SandboxPolicy
from agent.sandbox.orchestrator import SandboxOrchestrator
from agent.sandbox.risk import RuntimeRiskDetector
from agent.sandbox.signing import sign_code, verify_signature


class TestSigning(unittest.TestCase):
    def test_sign_and_verify(self) -> None:
        code_hash, signature = sign_code("print('ok')", {"user_id": "u1"})
        self.assertTrue(verify_signature(code_hash, {"user_id": "u1"}, signature))
        self.assertFalse(verify_signature(code_hash, {"user_id": "u2"}, signature))


class TestRiskDetector(unittest.TestCase):
    def test_block_network_event(self) -> None:
        detector = RuntimeRiskDetector(SandboxPolicy())
        decision = detector.inspect({"type": "network", "detail": "https://evil.example"})
        self.assertTrue(decision.blocked)


class TestAuditLogger(unittest.TestCase):
    def test_append_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = str(Path(tmp) / "audit.jsonl")
            logger = AuditLogger(log_path=log_path)
            output_path = logger.append({"user_id": "u1", "code_hash": "abc"})
            self.assertTrue(Path(output_path).exists())
            content = Path(output_path).read_text(encoding="utf-8").strip()
            row = json.loads(content)
            self.assertEqual(row["user_id"], "u1")


class TestOrchestrator(unittest.TestCase):
    def test_scan_failure_denied(self) -> None:
        orchestrator = SandboxOrchestrator()
        req = ExecutionRequest(user_id="u1", language="python", code="eval('1+1')", metadata={})
        result = orchestrator.execute(req)
        self.assertEqual(result.status, "denied")
        self.assertIn("静态扫描未通过", result.stderr)

    def test_execute_success_with_mock_driver(self) -> None:
        orchestrator = SandboxOrchestrator(limits=ResourceLimits(timeout_seconds=2))
        req = ExecutionRequest(user_id="u1", language="python", code="print('ok')", metadata={})
        fake_events = [{"type": "syscall", "detail": "read"}]
        with patch.object(
            orchestrator.driver,
            "run",
            return_value=(0, "ok", "", 80, ExecutionTelemetry(syscall_sequence=["read"]), fake_events),
        ):
            result = orchestrator.execute(req)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.exit_code, 0)


class TestExecutor(unittest.TestCase):
    def test_execute_untrusted_code_denied(self) -> None:
        result = execute_untrusted_code(user_id="u1", language="python", code="eval('1+1')")
        self.assertEqual(result["status"], "denied")


if __name__ == "__main__":
    unittest.main()
