"""财务报销 Agent 包。"""

def build_graph():
	from .graph_builder import build_graph as _build_graph

	return _build_graph()

__all__ = ["build_graph"]
