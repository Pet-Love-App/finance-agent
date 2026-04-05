from __future__ import annotations

import re
from typing import List, Pattern, Tuple

from .models import ScanResult, SecurityFinding


class StaticSecurityScanner:
    def __init__(self) -> None:
        self._rules: List[Tuple[str, str, Pattern[str], str]] = [
            ("PY-EVAL", "high", re.compile(r"\beval\s*\("), "检测到 eval，可能导致任意代码执行。"),
            ("PY-EXEC", "high", re.compile(r"\bexec\s*\("), "检测到 exec，可能导致任意代码执行。"),
            ("PY-SUBPROCESS", "high", re.compile(r"\bsubprocess\."), "检测到 subprocess，可能逃逸到系统命令。"),
            ("PY-SOCKET", "medium", re.compile(r"\bsocket\."), "检测到 socket，可能发起外联。"),
            ("PY-OPEN-ABS", "medium", re.compile(r"open\s*\(\s*['\"]/"), "检测到绝对路径文件访问。"),
            ("JS-CHILD", "high", re.compile(r"child_process"), "检测到 child_process，可能创建子进程。"),
            ("JS-EVAL", "high", re.compile(r"\beval\s*\("), "检测到 eval，可能执行不可信脚本。"),
            ("GEN-NET", "medium", re.compile(r"https?://"), "检测到网络 URL，需检查是否允许外联。"),
        ]

    def scan(self, code: str) -> ScanResult:
        findings: List[SecurityFinding] = []
        for rule_id, severity, pattern, message in self._rules:
            for matched in pattern.finditer(code):
                findings.append(
                    SecurityFinding(
                        rule_id=rule_id,
                        severity=severity,
                        message=message,
                        offset=matched.start(),
                    )
                )
        has_high = any(item.severity == "high" for item in findings)
        return ScanResult(passed=not has_high, findings=findings)
