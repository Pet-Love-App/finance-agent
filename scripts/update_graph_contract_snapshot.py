from __future__ import annotations

from pathlib import Path

from agent.graphs.contracts import write_graph_contract_snapshot


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    snapshot_path = repo_root / "agent" / "graphs" / "graph_contract_snapshot.json"
    written = write_graph_contract_snapshot(snapshot_path)
    print(f"Graph contract snapshot updated: {written}")


if __name__ == "__main__":
    main()

