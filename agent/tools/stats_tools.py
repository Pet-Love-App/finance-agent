from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from agent.tools.base import ToolResult, ok


def data_clean(records: List[Dict[str, Any]]) -> ToolResult:
    cleaned: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    for item in records:
        amount = float(item.get("invoice", {}).get("amount", item.get("amount", 0)) or 0)
        if amount <= 0:
            invalid.append(item)
            continue
        cleaned.append(item)
    return ok(cleaned=cleaned, invalid=invalid)


def aggregate_records(records: List[Dict[str, Any]]) -> ToolResult:
    if not records:
        return ok(aggregate={"total_amount": 0.0, "count": 0, "by_month": {}})

    rows: List[Dict[str, Any]] = []
    for item in records:
        created_at = str(item.get("created_at", ""))
        month = created_at[:7] if len(created_at) >= 7 else "unknown"
        amount = float(item.get("invoice", {}).get("amount", item.get("amount", 0)) or 0)
        rows.append({"month": month, "amount": amount})

    df = pd.DataFrame(rows)
    by_month = df.groupby("month", as_index=False)["amount"].sum().to_dict(orient="records")
    total = float(df["amount"].sum())
    return ok(aggregate={"total_amount": total, "count": len(records), "by_month": by_month})


def generate_final_account(aggregate: Dict[str, Any], output_dir: str | None = None) -> ToolResult:
    out_dir = Path(output_dir or "docs/parsed/final_outputs").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"final_account_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    pd.DataFrame(aggregate.get("by_month", [])).to_excel(target, index=False)
    return ok(final_account_path=str(target))


def load_final_data(payload: Dict[str, Any]) -> ToolResult:
    aggregate = payload.get("aggregate", {})
    return ok(final_data=aggregate)


def budget_calculate(final_data: Dict[str, Any], strategy: Dict[str, Any] | None = None) -> ToolResult:
    strategy = strategy or {}
    growth_rate = float(strategy.get("growth_rate", 0.05))
    base_total = float(final_data.get("total_amount", 0.0))
    budget_total = base_total * (1 + growth_rate)
    return ok(budget={"base_total": base_total, "growth_rate": growth_rate, "budget_total": round(budget_total, 2)})


def generate_budget(budget: Dict[str, Any], output_dir: str | None = None) -> ToolResult:
    out_dir = Path(output_dir or "docs/parsed/budget_outputs").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"budget_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    pd.DataFrame([budget]).to_excel(target, index=False)
    return ok(budget_path=str(target))


def generate_report(aggregate: Dict[str, Any], budget: Dict[str, Any], output_dir: str | None = None) -> ToolResult:
    out_dir = Path(output_dir or "docs/parsed/report_outputs").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    content = (
        "# 年度分析报告\n\n"
        f"- 决算总额: {aggregate.get('total_amount', 0)}\n"
        f"- 记录数: {aggregate.get('count', 0)}\n"
        f"- 预算总额: {budget.get('budget_total', 0)}\n"
    )
    target.write_text(content, encoding="utf-8")
    return ok(report_path=str(target))
