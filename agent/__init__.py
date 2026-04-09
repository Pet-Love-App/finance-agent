# Ensure we set up certifi-based CA bundle (or fall back to disabling verification) as early as possible
import os
try:
    import certifi
    cert_path = certifi.where()
    os.environ.setdefault('SSL_CERT_FILE', cert_path)
    os.environ.setdefault('REQUESTS_CA_BUNDLE', cert_path)
    os.environ.setdefault('CURL_CA_BUNDLE', cert_path)
except Exception:
    try:
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass

"""财务报销 Agent 包。"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "EventBus":
        from .core.event_bus import EventBus

        return EventBus
    if name == "TaskDispatcher":
        from .core.dispatcher import TaskDispatcher

        return TaskDispatcher
    if name == "build_graph":
        from .graph_builder import build_graph

        return build_graph
    if name == "build_graph_v2":
        from .graph_builder import build_graph_v2

        return build_graph_v2
    raise AttributeError(f"module 'agent' has no attribute '{name}'")

__all__ = ["build_graph", "build_graph_v2", "TaskDispatcher", "EventBus"]
