__all__ = ["build_main_graph"]


def __getattr__(name: str):
    if name == "build_main_graph":
        from agent.graphs.main_graph import build_main_graph

        return build_main_graph
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
