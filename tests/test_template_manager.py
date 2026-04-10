"""
测试模板管理器的新功能
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.templates.manager import TemplateManager
from agent.templates.generator import TemplateGenerator


def test_search_templates():
    """
    测试基于模板元数据模糊匹配模板
    """
    print("=== 测试模板搜索功能 ===")
    
    # 初始化模板管理器
    manager = TemplateManager()
    
    # 测试搜索 "学生活动" 相关模板
    print("搜索 '学生活动' 相关模板:")
    student_activity_templates = manager.search_templates("学生活动")
    print(f"找到 {len(student_activity_templates)} 个模板")
    for template in student_activity_templates:
        print(f"  - {template['name']} (类型: {template['type']})")
    
    # 测试搜索 "excel" 相关模板
    print("\n搜索 'excel' 相关模板:")
    excel_templates = manager.search_templates("excel")
    print(f"找到 {len(excel_templates)} 个模板")
    for template in excel_templates:
        print(f"  - {template['name']} (类型: {template['type']})")
    
    return student_activity_templates, excel_templates


def test_get_template_by_metadata():
    """
    测试基于元数据匹配模板
    """
    print("\n=== 测试基于元数据匹配模板 ===")
    
    # 初始化模板管理器
    manager = TemplateManager()
    
    # 测试匹配 Word 文档模板
    word_metadata = {
        "content_type": "word",
        "file_type": ".docx"
    }
    word_template = manager.get_template_by_metadata(word_metadata)
    if word_template:
        print(f"找到 Word 模板: {word_template['name']}")
    else:
        print("未找到 Word 模板")
    
    # 测试匹配 Excel 文档模板
    excel_metadata = {
        "content_type": "excel",
        "file_type": ".xlsx"
    }
    excel_template = manager.get_template_by_metadata(excel_metadata)
    if excel_template:
        print(f"找到 Excel 模板: {excel_template['name']}")
    else:
        print("未找到 Excel 模板")
    
    return word_template, excel_template


def test_read_template():
    """
    测试基于确定模板读取
    """
    print("\n=== 测试基于确定模板读取 ===")
    
    # 初始化模板管理器
    manager = TemplateManager()
    
    # 测试读取 Word 模板
    word_template_name = "学生活动经费使用情况.docx"
    word_doc = manager.read_template(word_template_name)
    if word_doc:
        print(f"成功读取 Word 模板: {word_template_name}")
        print(f"  内容类型: {word_doc.content_type}")
        print(f"  章节数: {len(word_doc.sections)}")
        print(f"  表格数: {len(word_doc.tables)}")
    else:
        print(f"未能读取 Word 模板: {word_template_name}")
    
    # 测试读取 Excel 模板
    excel_template_name = "国内+思政实践_附件1. 未央书院 xx支队 思政实践 国内实践差旅报销模板-发老师电子版（必填25.12更新）.xlsx"
    excel_doc = manager.read_template(excel_template_name)
    if excel_doc:
        print(f"成功读取 Excel 模板: {excel_template_name}")
        print(f"  内容类型: {excel_doc.content_type}")
        print(f"  章节数: {len(excel_doc.sections)}")
        print(f"  表格数: {len(excel_doc.tables)}")
    else:
        print(f"未能读取 Excel 模板: {excel_template_name}")
    
    return word_doc, excel_doc


def test_generate_with_output_dir():
    """
    测试指定输出文件夹
    """
    print("\n=== 测试指定输出文件夹 ===")
    
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
    
    # 测试指定输出目录
    output_dir = "tests/output"
    
    print(f"测试模板: {template_name}")
    print(f"输出目录: {output_dir}")
    
    # 生成文档
    result = generator.generate_from_template(
        template_name=template_name,
        data=test_data,
        output_dir=output_dir
    )
    
    if result.get("success"):
        print(f"成功: {result['output_path']}")
    else:
        print(f"失败: {result.get('error', 'Unknown error')}")
    
    return result


if __name__ == "__main__":
    print("开始测试模板管理器新功能...\n")
    
    # 运行测试
    result1 = test_search_templates()
    result2 = test_get_template_by_metadata()
    result3 = test_read_template()
    result4 = test_generate_with_output_dir()
    
    print("\n=== 测试完成 ===")
    print(f"测试 1 (模板搜索): 成功找到 {len(result1[0])} 个学生活动模板, {len(result1[1])} 个 Excel 模板")
    print(f"测试 2 (元数据匹配): {'通过' if (result2[0] or result2[1]) else '失败'}")
    print(f"测试 3 (模板读取): {'通过' if (result3[0] or result3[1]) else '失败'}")
    print(f"测试 4 (指定输出目录): {'通过' if result4.get('success') else '失败'}")
