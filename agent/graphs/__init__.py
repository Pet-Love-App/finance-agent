__all__ = ["build_main_graph", "describe_main_graph_contract", "describe_graph_contract"]


def __getattr__(name: str):
    if name == "build_main_graph":
        from agent.graphs.main_graph import build_main_graph

        return build_main_graph
    if name == "describe_main_graph_contract":
        from agent.graphs.main_graph import describe_main_graph_contract

        return describe_main_graph_contract
    if name == "describe_graph_contract":
        from agent.graphs.contracts import describe_graph_contract

        return describe_graph_contract
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
