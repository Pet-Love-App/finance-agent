import os
import sys
# 确保模块搜索路径包含当前目录
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.graph_builder import build_graph
import json

def run_test():
    budget_json = {
        "project": "测试项目A",
        "items": [
            {"category": "差旅费", "budget_amount": 5000, "aliases": ["交通"]},
            {"category": "办公费", "budget_amount": 2000, "aliases": ["文具"]},
        ],
    }

    actual_json = {
        "project": "测试项目A",
        "items": [
            {
                # 测试条件1: 张冠李戴（打车费应属差旅费，但在申报中随意列为了办公费）
                "invoice_no": "INV-001",
                "expense_type": "打车费",
                "claimed_category": "办公费", 
                "amount": 150,
                "attachments": ["发票"],
                "description": "外出打车"
            },
            {
                # 测试条件2: 发票号重复 (和上方的发票号一样都是 INV-001)
                "invoice_no": "INV-001", 
                "expense_type": "交通费",
                "claimed_category": "差旅费",
                "amount": 100,
                "attachments": ["发票"],
                "description": "这是第二次用同一张发票"
            },
            {
                "invoice_no": "INV-002", 
                "expense_type": "交通费",
                "claimed_category": "差旅费",
                "amount": 100,
                "attachments": ["发票"],
                "description": "正常"
            },
            {
                "invoice_no": "INV-003", 
                "expense_type": "滴滴",
                "claimed_category": "办公费",
                "amount": 100,
                "attachments": ["发票"],
                "description": "打车费但申报为办公费"
            }
        ]
    }

    app = build_graph()
    initial_state = {
        "budget_source": budget_json,
        "actual_source": actual_json,
        "discrepancies": [],
        "suggestions": [],
    }

    print("启动财务图流程核验节点...")
    final_state = app.invoke(initial_state)

    print("\n================== 拦截到的异常明细 ==================")
    discrepancies = final_state["report"]["report_json"]["discrepancies"]
    print(json.dumps(discrepancies, ensure_ascii=False, indent=2))
    
if __name__ == "__main__":
    run_test()
