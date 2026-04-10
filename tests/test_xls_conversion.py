"""
测试 doc_tools 中的 xls 转换功能
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from agent.tools.doc_tools import convert_xls_to_xlsx, batch_convert_xls_to_xlsx

def test_convert_xls_to_xlsx():
    """测试单个 .xls 文件转换功能"""
    print("=== 测试单个 .xls 文件转换功能 ===")
    
    # 测试文件路径
    xls_file = "data/templates/学生活动_未央代发-调研模板.xls"
    
    # 检查文件是否存在
    if not Path(xls_file).exists():
        print(f"测试文件不存在: {xls_file}")
        return False
    
    # 转换文件
    result = convert_xls_to_xlsx(xls_file)
    
    if result.success:
        print(f"[成功] {result.data.get('message')}")
        print(f"输入文件: {result.data.get('input_file')}")
        print(f"输出文件: {result.data.get('output_file')}")
    else:
        print(f"[失败] {result.error}")
    
    return result.success

def test_batch_convert_xls_to_xlsx():
    """测试批量 .xls 文件转换功能"""
    print("\n=== 测试批量 .xls 文件转换功能 ===")
    
    result = batch_convert_xls_to_xlsx()
    
    if result.success:
        print(f"[成功] {result.data.get('message')}")
        print(f"转换文件数: {result.data.get('converted_count')}")
        print("转换的文件:")
        for file in result.data.get('converted_files', []):
            print(f"  - {file}")
    else:
        print(f"[失败] {result.error}")
    
    return result.success

if __name__ == "__main__":
    print("开始测试 doc_tools 中的 xls 转换功能...\n")
    
    success1 = test_convert_xls_to_xlsx()
    success2 = test_batch_convert_xls_to_xlsx()
    
    print("\n=== 测试完成 ===")
    print(f"测试 1 (单个文件转换): {'通过' if success1 else '失败'}")
    print(f"测试 2 (批量文件转换): {'通过' if success2 else '失败'}")
