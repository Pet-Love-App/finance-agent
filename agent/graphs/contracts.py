from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from agent.graphs.names import ALL_GRAPH_NODES, INTENT_ROUTE_TARGETS
from agent.graphs.spec import build_conditional_route_snapshot


def describe_graph_contract() -> Dict[str, Any]:
    return {
        "nodes": sorted(ALL_GRAPH_NODES),
        "intent_route_targets": sorted(INTENT_ROUTE_TARGETS),
        "conditional_routes": build_conditional_route_snapshot(),
    }


def default_snapshot_path() -> Path:
    return Path(__file__).resolve().with_name("graph_contract_snapshot.json")


def write_graph_contract_snapshot(path: str | Path | None = None) -> Path:
    target = Path(path).resolve() if path is not None else default_snapshot_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(describe_graph_contract(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target

