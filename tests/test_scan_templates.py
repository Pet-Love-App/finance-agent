"""
测试 doc_tools 中的 scan_templates 功能
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.tools.doc_tools import scan_templates

def test_scan_templates():
    """测试模板扫描功能"""
    print("=== 测试模板扫描功能 ===")
    
    result = scan_templates()
    
    if result.success:
        print(f"[成功] {result.data.get('message')}")
        print(f"模板数量: {result.data.get('template_count')}")
        print(f"配置文件: {result.data.get('config_file')}")
    else:
        print(f"[失败] {result.error}")
    
    return result.success

if __name__ == "__main__":
    print("开始测试 doc_tools 中的 scan_templates 功能...\n")
    
    success = test_scan_templates()
    
    print("\n=== 测试完成 ===")
    if success:
        print("测试 (模板扫描): 通过")
    else:
        print("测试 (模板扫描): 失败")
