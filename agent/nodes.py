from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .config import get_audit_config
from .schemas import ACTUAL_SCHEMA, BUDGET_SCHEMA
from .state import AgentState
from .utils import (
    append_discrepancy,
    build_budget_alias_map,
    dedupe_keep_order,
    fuzzy_align_category,
    safe_load_payload,
    to_float,
    validate_payload_schema,
)


def data_extraction_node(state: AgentState) -> AgentState:
    budget_payload = safe_load_payload(state["budget_source"])
    actual_payload = safe_load_payload(state["actual_source"])

    validate_payload_schema(budget_payload, BUDGET_SCHEMA, "预算数据")
    validate_payload_schema(actual_payload, ACTUAL_SCHEMA, "决算数据")

    budget_items = budget_payload.get("items", [])
    actual_items = actual_payload.get("items", [])

    extraction_warnings = list(state.get("extraction_warnings", []))

    normalized_budget: List[Dict[str, Any]] = []
    for row in budget_items:
        category = str(row.get("category", "")).strip()
        budget_amount = to_float(row.get("budget_amount", 0.0))
        aliases_raw = row.get("aliases", [])
        aliases = aliases_raw if isinstance(aliases_raw, list) else [aliases_raw]

        if not category:
            extraction_warnings.append("预算中存在空类目，已保留但后续可能触发对齐失败。")

        normalized_budget.append(
            {
                "category": category,
                "budget_amount": budget_amount,
                "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
            }
        )

    normalized_actual: List[Dict[str, Any]] = []
    for row in actual_items:
        attachments_raw = row.get("attachments", [])
        attachments = attachments_raw if isinstance(attachments_raw, list) else [attachments_raw]

        normalized_actual.append(
            {
                "invoice_no": str(row.get("invoice_no", "") or "").strip(),
                "expense_type": str(row.get("expense_type", "")).strip(),
                "amount": to_float(row.get("amount", 0.0)),
                "claimed_category": str(row.get("claimed_category", "")).strip(),
                "attachments": [str(item).strip() for item in attachments if str(item).strip()],
                "description": str(row.get("description", "") or "").strip(),
            }
        )

    budget_df = pd.DataFrame(normalized_budget)
    actual_df = pd.DataFrame(normalized_actual)

    if "budget_amount" in budget_df.columns:
        budget_df["budget_amount"] = pd.to_numeric(budget_df["budget_amount"], errors="coerce").fillna(0.0)
    if "amount" in actual_df.columns:
        actual_df["amount"] = pd.to_numeric(actual_df["amount"], errors="coerce").fillna(0.0)

    return {
        "budget_data": normalized_budget,
        "actual_data": normalized_actual,
        "budget_df": budget_df,
        "actual_df": actual_df,
        "discrepancies": state.get("discrepancies", []),
        "suggestions": state.get("suggestions", []),
        "extraction_warnings": extraction_warnings,
    }


def category_alignment_node(state: AgentState) -> AgentState:
    budget_df = state.get("budget_df", pd.DataFrame()).copy()
    actual_df = state.get("actual_df", pd.DataFrame()).copy()

    if "category" not in budget_df.columns:
        budget_df["category"] = ""
    if "expense_type" not in actual_df.columns:
        actual_df["expense_type"] = ""
    if "claimed_category" not in actual_df.columns:
        actual_df["claimed_category"] = ""

    budget_categories = budget_df["category"].tolist()
    alias_map = build_budget_alias_map(budget_df)

    matched_categories: List[Optional[str]] = []
    strategies: List[str] = []

    for _, row in actual_df.iterrows():
        matched, strategy = fuzzy_align_category(
            expense_type=row.get("expense_type", ""),
            claimed_category=row.get("claimed_category", ""),
            budget_categories=budget_categories,
            alias_map=alias_map,
        )
        matched_categories.append(matched)
        strategies.append(strategy)

    actual_df["matched_category"] = matched_categories
    actual_df["match_strategy"] = strategies

    return {
        "actual_df": actual_df,
        "actual_data": actual_df.to_dict(orient="records"),
    }


def consistency_check_node(state: AgentState) -> AgentState:
    config = get_audit_config()
    budget_df = state.get("budget_df", pd.DataFrame()).copy()
    actual_df = state.get("actual_df", pd.DataFrame()).copy()

    discrepancies = list(state.get("discrepancies", []))
    suggestions = list(state.get("suggestions", []))

    if "matched_category" not in actual_df.columns:
        actual_df["matched_category"] = pd.NA
    if "match_strategy" not in actual_df.columns:
        actual_df["match_strategy"] = "unmatched"
    if "amount" not in actual_df.columns:
        actual_df["amount"] = 0.0
    if "category" not in budget_df.columns:
        budget_df["category"] = ""
    if "budget_amount" not in budget_df.columns:
        budget_df["budget_amount"] = 0.0

    unmatched_rows = actual_df[actual_df["matched_category"].isna()]
    for _, row in unmatched_rows.iterrows():
        append_discrepancy(
            discrepancies,
            issue_type="Category Compliance",
            risk=config.high_risk_label,
            message="该决算支出无法映射到任何预算父类。",
            details={
                "item": row.get("expense_type", ""),
                "amount": float(row.get("amount", 0.0)),
                "match_strategy": row.get("match_strategy", "unmatched"),
            },
        )
        suggestions.append(
            f"为支出项“{row.get('expense_type', '')}”补充预算父类映射，或在预算中新增对应类目。"
        )

    budget_sum_df = budget_df[["category", "budget_amount"]].copy()
    actual_sum_df = (
        actual_df.dropna(subset=["matched_category"])
        .groupby("matched_category", as_index=False)["amount"]
        .sum()
        .rename(columns={"matched_category": "category", "amount": "actual_amount"})
    )

    compare_df = budget_sum_df.merge(actual_sum_df, on="category", how="left").fillna({"actual_amount": 0.0})
    safe_budget = compare_df["budget_amount"].replace(0, pd.NA)
    compare_df["overspend_ratio"] = (
        (compare_df["actual_amount"] - compare_df["budget_amount"]) / safe_budget
    ).fillna(0.0)

    overspent_rows = compare_df[compare_df["overspend_ratio"] > config.category_overrun_threshold]
    for _, row in overspent_rows.iterrows():
        append_discrepancy(
            discrepancies,
            issue_type="Category Budget Overrun",
            risk=config.high_risk_label,
            message=f"单项类目超支超过 {config.category_overrun_threshold:.0%}。",
            details={
                "category": row["category"],
                "budget_amount": round(float(row["budget_amount"]), 2),
                "actual_amount": round(float(row["actual_amount"]), 2),
                "overspend_ratio": round(float(row["overspend_ratio"]), 4),
            },
        )
        suggestions.append(
            f"类目“{row['category']}”超支 {row['overspend_ratio']:.1%}，建议调整报销金额或申请预算追加。"
        )

    total_budget = float(compare_df["budget_amount"].sum())
    total_actual = float(actual_df["amount"].sum())
    if total_actual > total_budget:
        append_discrepancy(
            discrepancies,
            issue_type="Total Budget Overrun",
            risk=config.high_risk_label,
            message="决算总额超出预算总额。",
            details={
                "budget_total": round(total_budget, 2),
                "actual_total": round(total_actual, 2),
                "overspend_total": round(total_actual - total_budget, 2),
            },
        )
        suggestions.append("总额已超预算，建议删除非必要支出或走预算调整审批流程。")

    return {
        "discrepancies": discrepancies,
        "suggestions": dedupe_keep_order(suggestions),
    }


# 模拟内存数据库用于防重发票
_PROCESSED_INVOICES = set()

def compliance_audit_node(state: AgentState) -> AgentState:
    config = get_audit_config()
    actual_df = state["actual_df"].copy()
    budget_df = state.get("budget_df", pd.DataFrame())
    discrepancies = list(state.get("discrepancies", []))
    suggestions = list(state.get("suggestions", []))

    special_types = set(config.special_expense_keywords)
    
    # 获取动态的全局字典和当前项目的预算类别
    budget_categories = budget_df["category"].tolist() if "category" in budget_df.columns else []
    alias_map = build_budget_alias_map(budget_df)

    for _, row in actual_df.iterrows():
        expense_type = str(row.get("expense_type", "")).strip()
        matched_category = str(row.get("matched_category", "")).strip()
        invoice_no = str(row.get("invoice_no", "")).strip()

        # 1. 发票防重校验
        if invoice_no:
            if invoice_no in _PROCESSED_INVOICES:
                append_discrepancy(
                    discrepancies,
                    issue_type="Duplicate Invoice",
                    risk=config.high_risk_label,
                    message="检测到潜在重复报销",
                    details={
                        "item": expense_type,
                        "invoice_no": invoice_no,
                        "amount": float(row.get("amount", 0.0)),
                    },
                )
                suggestions.append(f"发票号 {invoice_no} 已被使用过，请核实是否重复报销。")
            else:
                _PROCESSED_INVOICES.add(invoice_no)

        # 2. 类目合法性交叉校验（动态防“张冠李戴”）
        # 仅根据发票实际支出(expense_type)进行独立客观地推断它本该属于哪个预算类别
        expected_category, _ = fuzzy_align_category(
            expense_type=expense_type,
            claimed_category="",  # 忽略用户主观申报类别，只看事实花费
            budget_categories=budget_categories,
            alias_map=alias_map
        )
        
        # 如果推算出的客观大类和最终匹配到的大类不一致，说明用户瞎填了
        if expected_category and matched_category and matched_category != "nan":
            if expected_category != matched_category:
                append_discrepancy(
                    discrepancies,
                    issue_type="Category Mismatch",
                    risk=config.high_risk_label,
                    message=f"类目合规校验失败：实际支出属于[{expected_category}]，但被申报合并至[{matched_category}]核算。",
                    details={
                        "item": expense_type,
                        "expected_category": expected_category,
                        "actual_category": matched_category,
                    },
                )
                suggestions.append(f"支出项“{expense_type}”客观上应归入“{expected_category}”，请勿在“{matched_category}”中违规报销。")

        # 3. 特殊类型附件校验
        is_special = any(key in expense_type for key in special_types)
        if not is_special:
            continue

        attachments = row.get("attachments", [])
        attachments_text = " ".join(str(item) for item in attachments)
        has_required_proof = ("签到" in attachments_text) or ("通知" in attachments_text)

        if not has_required_proof:
            append_discrepancy(
                discrepancies,
                issue_type="Material Compliance",
                risk=config.high_risk_label,
                message="餐饮/会议类支出缺少签到表或通知文件。",
                details={
                    "item": expense_type,
                    "amount": float(row.get("amount", 0.0)),
                    "attachments": attachments,
                },
            )
            suggestions.append(f"支出“{expense_type}”需补齐签到表或活动通知文件。")

    return {
        "discrepancies": discrepancies,
        "suggestions": dedupe_keep_order(suggestions),
    }


def llm_verification_node(state: AgentState) -> AgentState:
    """Optional LLM-assisted verification: ask model to re-evaluate borderline mappings."""
    print("[LLM NODE] llm_verification_node running...")
    import os as _os
    print("[LLM NODE] AGENT_LLM_DEBUG=", _os.getenv("AGENT_LLM_DEBUG"))
    print("[LLM NODE] AGENT_LLM_API_KEY present=", bool(_os.getenv("AGENT_LLM_API_KEY")))
    print("[LLM NODE] AGENT_ENABLE_LLM_CHECKS=", _os.getenv("AGENT_ENABLE_LLM_CHECKS"))
    from .config import get_audit_config
    from .utils import llm_align_category_for_items, build_budget_alias_map

    config = get_audit_config()
    if not getattr(config, "enable_llm_checks", False):
        return {"discrepancies": state.get("discrepancies", []), "suggestions": state.get("suggestions", [])}

    api_key = _os.getenv("OPENAI_API_KEY") or _os.getenv("AGENT_LLM_API_KEY")
    if not api_key:
        return {"discrepancies": state.get("discrepancies", []), "suggestions": state.get("suggestions", [])}

    budget_df = state.get("budget_df", pd.DataFrame()).copy()
    actual_df = state.get("actual_df", pd.DataFrame()).copy()

    budget_categories = budget_df["category"].tolist() if "category" in budget_df.columns else []
    alias_map = build_budget_alias_map(budget_df)

    # Strategy change per request:
    # - 如果模糊匹配已经发现问题（expected is None 或 expected != matched），不要调用大模型（节省成本），直接保留原有问题提示。
    # - 仅对模糊匹配看起来没有问题（expected == matched）的条目，调用 LLM 做额外核查以避免漏判。
    candidates_to_ask = []
    for idx, row in actual_df.iterrows():
        expense_type = str(row.get("expense_type", "")).strip()
        matched_category = str(row.get("matched_category", "")).strip()

        expected, _ = fuzzy_align_category(
            expense_type=expense_type,
            claimed_category="",
            budget_categories=budget_categories,
            alias_map=alias_map,
        )

        # ask LLM when fuzzy check did NOT already flag a mismatch
        # i.e., include items where expected is None (unmatched) OR expected == matched_category
        if not (expected and matched_category and expected != matched_category):
            item = row.to_dict()
            item["_index"] = int(idx)
            candidates_to_ask.append(item)

    if not candidates_to_ask:
        return {"discrepancies": state.get("discrepancies", []), "suggestions": state.get("suggestions", [])}

    # limit batch size to control cost
    batch = candidates_to_ask[:50]
    print("[LLM NODE] Candidates to ask:", [(b.get("_index"), b.get("expense_type")) for b in batch])
    try:
        suggestions_from_llm = llm_align_category_for_items(
            items=batch,
            budget_categories=budget_categories,
            model=config.llm_model,
            temperature=config.llm_temperature,
            api_key=api_key,
        )
        print("[LLM NODE] LLM returned", len(suggestions_from_llm), "suggestions")
    except Exception as exc:
        print("[LLM NODE] LLM call failed:", exc)
        return {"discrepancies": state.get("discrepancies", []), "suggestions": state.get("suggestions", [])}

    discrepancies = list(state.get("discrepancies", []))
    suggestions = list(state.get("suggestions", []))

    for rec in suggestions_from_llm:
        try:
            idx = int(rec.get("index", -1))
            suggested = rec.get("suggested_category")
            reason = rec.get("reason", "")
        except Exception:
            continue

        if not suggested:
            continue

        # compare against current matched category
        row = actual_df.iloc[idx] if 0 <= idx < len(actual_df) else None
        matched = str(row.get("matched_category", "")) if row is not None else ""
        if suggested != matched:
            # Do not expose internal index in the output details; keep it for internal mapping only
            append_discrepancy(
                discrepancies,
                issue_type="LLM Category Suggestion",
                risk=config.high_risk_label,
                message=f"LLM suggests category '{suggested}' for 支出项 '{row.get('expense_type','')}'",
                details={"suggested_category": suggested, "reason": reason},
            )
            suggestions.append(f"LLM 建议将支出项“{row.get('expense_type','')}”归入“{suggested}”：{reason}")

    return {"discrepancies": discrepancies, "suggestions": dedupe_keep_order(suggestions)}


def report_generator_node(state: AgentState) -> AgentState:
    config = get_audit_config()
    discrepancies = state.get("discrepancies", [])
    suggestions = dedupe_keep_order(state.get("suggestions", []))
    extraction_warnings = state.get("extraction_warnings", [])
    actual_df = state.get("actual_df", pd.DataFrame())

    high_risk_count = sum(1 for item in discrepancies if item.get("risk") == config.high_risk_label)
    unmatched_count = sum(
        1
        for item in discrepancies
        if item.get("type") == "Category Compliance" and item.get("risk") == config.high_risk_label
    )

    report_json: Dict[str, Any] = {
        "summary": {
            "total_issues": len(discrepancies),
            "high_risk_issues": high_risk_count,
            "unmatched_items": unmatched_count,
            "overall_status": "REJECTED" if high_risk_count > 0 else "PASSED",
        },
        "warnings": extraction_warnings,
        "discrepancies": discrepancies,
        "suggestions": suggestions,
    }

    if not actual_df.empty and {"expense_type", "matched_category", "match_strategy"}.issubset(set(actual_df.columns)):
        report_json["alignment_preview"] = actual_df[
            ["expense_type", "claimed_category", "matched_category", "match_strategy", "amount"]
        ].to_dict(orient="records")

    lines = [
        "# 财务报销核验报告",
        "",
        f"- 问题总数: {len(discrepancies)}",
        f"- 高风险问题: {high_risk_count}",
        f"- 审核结论: {'不通过' if high_risk_count > 0 else '通过'}",
        "",
        "## 问题明细",
    ]

    if extraction_warnings:
        lines.extend(["", "## 提取告警"])
        for warning in extraction_warnings:
            lines.append(f"- {warning}")

    if discrepancies:
        for index, item in enumerate(discrepancies, start=1):
            lines.append(
                f"{index}. [{item.get('risk', 'Unknown')}] {item.get('type', 'Unknown')} - {item.get('message', '')}"
            )
    else:
        lines.append("- 无异常。")

    lines.append("")
    lines.append("## 修改建议")
    if suggestions:
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")
    else:
        lines.append("- 无需修改。")

    report_markdown = "\n".join(lines)

    return {
        "report": {
            "report_json": report_json,
            "report_markdown": report_markdown,
        }
    }
