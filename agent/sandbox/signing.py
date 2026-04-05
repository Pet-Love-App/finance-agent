from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Dict, Tuple


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def sign_code(code: str, metadata: Dict[str, Any]) -> Tuple[str, str]:
    payload = {
        "code_hash": hash_code(code),
        "metadata": metadata,
    }
    message = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    key = os.getenv("SANDBOX_SIGNING_KEY", "sandbox-dev-key").encode("utf-8")
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()
    return payload["code_hash"], signature


def verify_signature(code_hash: str, metadata: Dict[str, Any], signature: str) -> bool:
    payload = {
        "code_hash": code_hash,
        "metadata": metadata,
    }
    message = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    key = os.getenv("SANDBOX_SIGNING_KEY", "sandbox-dev-key").encode("utf-8")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
