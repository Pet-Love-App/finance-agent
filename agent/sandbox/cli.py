from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .executor import execute_untrusted_code
from .models import ResourceLimits, SandboxPolicy
from .scanner import StaticSecurityScanner
from .signing import hash_code, sign_code, verify_signature


def _cmd_scan(code_path: Path) -> int:
    code = code_path.read_text(encoding="utf-8")
    scan = StaticSecurityScanner().scan(code)
    payload = {
        "passed": scan.passed,
        "findings": [
            {"rule_id": item.rule_id, "severity": item.severity, "message": item.message, "offset": item.offset}
            for item in scan.findings
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if scan.passed else 2


def _cmd_sign(code_path: Path, metadata_text: str) -> int:
    code = code_path.read_text(encoding="utf-8")
    metadata: Dict[str, Any] = json.loads(metadata_text or "{}")
    code_hash, signature = sign_code(code, metadata)
    payload = {
        "code_hash": code_hash,
        "signature": signature,
        "verified": verify_signature(code_hash, metadata, signature),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_hash(code_path: Path) -> int:
    code = code_path.read_text(encoding="utf-8")
    print(hash_code(code))
    return 0


def _cmd_exec(args: argparse.Namespace) -> int:
    code = Path(args.code_file).read_text(encoding="utf-8")
    limits = ResourceLimits(
        cpu_cores=args.cpu,
        memory_mb=args.memory,
        disk_mb=args.disk,
        network_kbps=args.network,
        timeout_seconds=args.timeout,
    )
    policy = SandboxPolicy(
        technology="docker",
        network_mode=args.network_mode,
        seccomp_profile=args.seccomp_profile,
        apparmor_profile=args.apparmor_profile,
        syscall_whitelist=args.syscall_whitelist,
    )
    result = execute_untrusted_code(
        user_id=args.user_id,
        language=args.language,
        code=code,
        metadata={"pipeline": "cli"},
        limits=limits,
        policy=policy,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 3


def main() -> int:
    parser = argparse.ArgumentParser(description="Sandbox 安全执行 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_scan = subparsers.add_parser("scan", help="静态扫描")
    parser_scan.add_argument("--code-file", required=True)

    parser_sign = subparsers.add_parser("sign", help="代码签名")
    parser_sign.add_argument("--code-file", required=True)
    parser_sign.add_argument("--metadata", default="{}")

    parser_hash = subparsers.add_parser("hash", help="代码哈希")
    parser_hash.add_argument("--code-file", required=True)

    parser_exec = subparsers.add_parser("exec", help="沙箱执行")
    parser_exec.add_argument("--user-id", required=True)
    parser_exec.add_argument("--language", choices=["python", "javascript", "js"], required=True)
    parser_exec.add_argument("--code-file", required=True)
    parser_exec.add_argument("--cpu", type=float, default=1.0)
    parser_exec.add_argument("--memory", type=int, default=512)
    parser_exec.add_argument("--disk", type=int, default=256)
    parser_exec.add_argument("--network", type=int, default=256)
    parser_exec.add_argument("--timeout", type=int, default=8)
    parser_exec.add_argument("--network-mode", default="none")
    parser_exec.add_argument("--seccomp-profile", default=None)
    parser_exec.add_argument("--apparmor-profile", default=None)
    parser_exec.add_argument("--syscall-whitelist", nargs="*", default=[])

    args = parser.parse_args()
    if args.command == "scan":
        return _cmd_scan(Path(args.code_file))
    if args.command == "sign":
        return _cmd_sign(Path(args.code_file), args.metadata)
    if args.command == "hash":
        return _cmd_hash(Path(args.code_file))
    if args.command == "exec":
        return _cmd_exec(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
