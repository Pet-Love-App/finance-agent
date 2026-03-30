from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .nodes import (
    category_alignment_node,
    compliance_audit_node,
    consistency_check_node,
    data_extraction_node,
    llm_verification_node,
    report_generator_node,
)
from .state import AgentState


def build_graph() -> Any:
    graph = StateGraph(AgentState)

    graph.add_node("Data_Extraction", data_extraction_node)
    graph.add_node("Category_Alignment", category_alignment_node)
    graph.add_node("Consistency_Check", consistency_check_node)
    graph.add_node("Compliance_Audit", compliance_audit_node)
    graph.add_node("LLM_Verification", llm_verification_node)
    graph.add_node("Report_Generator", report_generator_node)

    graph.add_edge(START, "Data_Extraction")
    graph.add_edge("Data_Extraction", "Category_Alignment")
    graph.add_edge("Category_Alignment", "Consistency_Check")
    graph.add_edge("Consistency_Check", "Compliance_Audit")
    graph.add_edge("Compliance_Audit", "LLM_Verification")
    graph.add_edge("LLM_Verification", "Report_Generator")
    graph.add_edge("Report_Generator", END)

    return graph.compile()
