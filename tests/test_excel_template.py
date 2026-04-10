"""
测试 Excel 模板生成功能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.templates.generator import TemplateGenerator


def test_excel_template_with_loop():
    """
    测试 Excel 模板生成 - 带有循环标记的模板
    """
    print("=== 测试 Excel 模板生成 (带有循环标记) ===")
    
    # 初始化生成器
    generator = TemplateGenerator()
    
    # 测试数据 - 多条数据
    test_data = {
        "payment_data_list": [
            {
                "dept_code": "001",
                "proj_code": "P20260410",
                "student_name": "张三",
                "id_type": "身份证",
                "id_number": "110101199001011234",
                "payment_purpose": "调研经费",
                "payment_amount": 1000.00,
                "tax_exempt": "是"
            },
            {
                "dept_code": "002",
                "proj_code": "P20260411",
                "student_name": "李四",
                "id_type": "身份证",
                "id_number": "110101199001011235",
                "payment_purpose": "调研经费",
                "payment_amount": 2000.00,
                "tax_exempt": "是"
            },
            {
                "dept_code": "003",
                "proj_code": "P20260412",
                "student_name": "王五",
                "id_type": "身份证",
                "id_number": "110101199001011236",
                "payment_purpose": "调研经费",
                "payment_amount": 1500.00,
                "tax_exempt": "否"
            }
        ]
    }
    
    print(f"测试数据: {test_data}")
    
    # 测试模板
    template_name = "学生活动_未央代发-调研模板.xlsx"
    
    print(f"测试模板: {template_name}")
    
    # 生成文档到指定目录
    output_dir = "tests/output"
    
    # 生成文档
    result = generator.generate_from_template(
        template_name=template_name,
        data=test_data,
        output_dir=output_dir
    )
    
    if result.get("success"):
        print(f"[成功] 成功: {result['output_path']}")
        print(f"   工作表: {result.get('sheet_name', 'Sheet1')}")
        print(f"   生成文件数: {len(test_data['payment_data_list'])}")
    else:
        print(f"[失败] 失败: {result.get('error', 'Unknown error')}")
    
    return result


def test_excel_template_with_multiple_rows():
    """
    测试 Excel 模板生成 - 多条数据
    """
    print("=== 测试 Excel 模板生成 (多条数据) ===")
    
    # 初始化生成器
    generator = TemplateGenerator()
    
    # 测试数据
    test_data = {
        "name": "张三",
        "contact": "13800138000",
        "activity_time": "2026-04-01",
        "activity_location": "清华大学",
        "participants": "10人",
        "activity_content": "学生活动",
        "expense_detail": "餐饮费: 500元"
    }
    
    # 测试模板 (使用 .xlsx 格式)
    template_name = "国内+思政实践_附件1. 未央书院 xx支队 思政实践 国内实践差旅报销模板-发老师电子版（必填25.12更新）.xlsx"
    
    print(f"测试模板: {template_name}")
    
    # 生成文档到指定目录
    output_dir = "tests/output"
    
    # 生成文档
    result = generator.generate_from_template(
        template_name=template_name,
        data=test_data,
        output_dir=output_dir
    )
    
    if result.get("success"):
        print(f"[成功] 成功: {result['output_path']}")
        print(f"   工作表: {result.get('sheet_name', 'Sheet1')}")
    else:
        print(f"[失败] 失败: {result.get('error', 'Unknown error')}")
    
    return result


def test_excel_template_with_single_data():
    """
    测试 Excel 模板生成 - 单条数据
    """
    print("\n=== 测试 Excel 模板生成 (单条数据) ===")
    
    # 初始化生成器
    generator = TemplateGenerator()
    
    # 测试数据
    test_data = {
        "name": "张三",
        "contact": "13800138000",
        "activity_time": "2026-04-01",
        "location": "清华大学",
        "participants": "10人",
        "description": "学生活动",
        "expense_detail": "餐饮费: 500元"
    }
    
    # 测试模板
    template_name = "学生活动经费使用情况.docx"
    
    print(f"测试模板: {template_name}")
    
    # 生成文档到指定目录
    output_dir = "tests/output"
    
    # 生成文档
    result = generator.generate_from_template(
        template_name=template_name,
        data=test_data,
        output_dir=output_dir
    )
    
    if result.get("success"):
        print(f"[成功] 成功: {result['output_path']}")
    else:
        print(f"[失败] 失败: {result.get('error', 'Unknown error')}")
    
    return result


def test_excel_template_not_found():
    """
    测试 Excel 模板不存在的情况
    """
    print("\n=== 测试 Excel 模板不存在 ===")
    
    # 初始化生成器
    generator = TemplateGenerator()
    
    # 测试数据
    test_data = {
        "payment_data_list": []
    }
    
    # 不存在的模板
    template_name = "不存在的模板.xlsx"
    
    print(f"测试模板: {template_name}")
    
    # 生成文档到指定目录
    output_dir = "tests/output"
    
    # 生成文档
    result = generator.generate_from_template(
        template_name=template_name,
        data=test_data,
        output_dir=output_dir
    )
    
    if not result.get("success"):
        print(f"[成功] 预期失败: {result.get('error', 'Unknown error')}")
    else:
        print(f"[失败] 意外成功: {result.get('output_path')}")
    
    return result


if __name__ == "__main__":
    print("开始测试 Excel 模板生成功能...\n")
    
    # 运行测试
    result1 = test_excel_template_with_loop()
    result2 = test_excel_template_with_multiple_rows()
    result3 = test_excel_template_with_single_data()
    result4 = test_excel_template_not_found()
    
    print("\n=== 测试完成 ===")
    print(f"测试 1 (带有循环标记): {'通过' if result1.get('success') else '失败'}")
    print(f"测试 2 (多条数据): {'通过' if result2.get('success') else '失败'}")
    print(f"测试 3 (单条数据): {'通过' if result3.get('success') else '失败'}")
    print(f"测试 4 (模板不存在): {'通过' if not result4.get('success') else '失败'}")
