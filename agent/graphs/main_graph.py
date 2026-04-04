from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.graphs.intent import route_by_task, intent_node
from agent.graphs.state import AppState
from agent.graphs.subgraphs.budget import (
    budget_calculate_node,
    budget_generate_node,
    budget_start_node,
    load_final_data_node,
)
from agent.graphs.subgraphs.final_account import (
    aggregate_node,
    data_clean_node,
    final_generate_node,
    final_start_node,
    load_records_node,
)
from agent.graphs.subgraphs.qa import qa_start_node, question_understand_node, rule_retrieve_node
from agent.graphs.subgraphs.reimburse import (
    activity_parse_node,
    classify_file_node,
    extract_node,
    gen_doc_node,
    gen_mail_node,
    invoice_extract_node,
    reimburse_start_node,
    rule_check_node,
    save_record_node,
    scan_file_node,
)


def build_main_graph() -> Any:
    graph = StateGraph(AppState)

    graph.add_node("IntentNode", intent_node)

    graph.add_node("ReimburseStartNode", reimburse_start_node)
    graph.add_node("ScanFileNode", scan_file_node)
    graph.add_node("ClassifyFileNode", classify_file_node)
    graph.add_node("ExtractNode", extract_node)
    graph.add_node("InvoiceExtractNode", invoice_extract_node)
    graph.add_node("ActivityParseNode", activity_parse_node)
    graph.add_node("RuleCheckNode", rule_check_node)
    graph.add_node("GenDocNode", gen_doc_node)
    graph.add_node("GenMailNode", gen_mail_node)
    graph.add_node("SaveRecordNode", save_record_node)

    graph.add_node("QAStartNode", qa_start_node)
    graph.add_node("QuestionUnderstandNode", question_understand_node)
    graph.add_node("RuleRetrieveNode", rule_retrieve_node)

    graph.add_node("FinalStartNode", final_start_node)
    graph.add_node("LoadRecordNode", load_records_node)
    graph.add_node("DataCleanNode", data_clean_node)
    graph.add_node("DataAggregateNode", aggregate_node)
    graph.add_node("FinalGenerateNode", final_generate_node)

    graph.add_node("BudgetStartNode", budget_start_node)
    graph.add_node("LoadFinalDataNode", load_final_data_node)
    graph.add_node("BudgetCalculateNode", budget_calculate_node)
    graph.add_node("BudgetGenerateNode", budget_generate_node)

    graph.add_edge(START, "IntentNode")
    graph.add_conditional_edges(
        "IntentNode",
        route_by_task,
        {
            "ReimburseStartNode": "ReimburseStartNode",
            "QAStartNode": "QAStartNode",
            "FinalStartNode": "FinalStartNode",
            "BudgetStartNode": "BudgetStartNode",
        },
    )

    graph.add_edge("ReimburseStartNode", "ScanFileNode")
    graph.add_edge("ScanFileNode", "ClassifyFileNode")
    graph.add_edge("ClassifyFileNode", "ExtractNode")
    graph.add_edge("ExtractNode", "InvoiceExtractNode")
    graph.add_edge("InvoiceExtractNode", "ActivityParseNode")
    graph.add_edge("ActivityParseNode", "RuleCheckNode")
    graph.add_edge("RuleCheckNode", "GenDocNode")
    graph.add_edge("GenDocNode", "GenMailNode")
    graph.add_edge("GenMailNode", "SaveRecordNode")
    graph.add_edge("SaveRecordNode", END)

    graph.add_edge("QAStartNode", "QuestionUnderstandNode")
    graph.add_edge("QuestionUnderstandNode", "RuleRetrieveNode")
    graph.add_edge("RuleRetrieveNode", END)

    graph.add_edge("FinalStartNode", "LoadRecordNode")
    graph.add_edge("LoadRecordNode", "DataCleanNode")
    graph.add_edge("DataCleanNode", "DataAggregateNode")
    graph.add_edge("DataAggregateNode", "FinalGenerateNode")
    graph.add_edge("FinalGenerateNode", END)

    graph.add_edge("BudgetStartNode", "LoadFinalDataNode")
    graph.add_edge("LoadFinalDataNode", "BudgetCalculateNode")
    graph.add_edge("BudgetCalculateNode", "BudgetGenerateNode")
    graph.add_edge("BudgetGenerateNode", END)

    return graph.compile()
