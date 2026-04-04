from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    fallback_used: bool = False


def ok(**kwargs: Any) -> ToolResult:
    return ToolResult(success=True, data=kwargs)


def fail(message: str, *, fallback_used: bool = False, **kwargs: Any) -> ToolResult:
    return ToolResult(success=False, error=message, data=kwargs, fallback_used=fallback_used)
