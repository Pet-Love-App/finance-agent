from __future__ import annotations

from typing import Any, Dict

BUDGET_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "project": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "budget_amount": {"type": ["number", "string"]},
                    "aliases": {
                        "type": "array",
                        "items": {"type": ["string", "number"]},
                    },
                },
                "required": ["category", "budget_amount"],
            },
        },
    },
    "required": ["items"],
}


ACTUAL_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "project": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "invoice_no": {"type": ["string", "number", "null"]},
                    "expense_type": {"type": "string"},
                    "claimed_category": {"type": "string"},
                    "amount": {"type": ["number", "string"]},
                    "attachments": {
                        "type": "array",
                        "items": {"type": ["string", "number"]},
                    },
                    "description": {"type": ["string", "null"]},
                },
                "required": ["expense_type", "amount"],
            },
        },
    },
    "required": ["items"],
}


CATEGORY_SYNONYMS: Dict[str, str] = {
    "打车费": "差旅费",
    "交通费": "差旅费",
    "机票": "差旅费",
    "火车票": "差旅费",
    "住宿": "差旅费",
    "餐费": "餐饮费",
    "聚餐": "餐饮费",
    "会务": "会议费",
    "会议室": "会议费",
    "打印": "材料费",
    "文具": "材料费",
}
