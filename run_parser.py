# """
# D:/finance/finance-agent/run_parse.py

# 一键解析脚本。双击或在终端运行即可。

# 使用前请设置环境变量：
#     set PARATERA_API_KEY=你的密钥      (Windows CMD)
#     $env:PARATERA_API_KEY="你的密钥"   (PowerShell)
#     export PARATERA_API_KEY=你的密钥    (Linux/Mac)
# """
# import logging
# import sys
# import os
# import json

# # 确保项目根目录在 path 中
# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# # 自动加载 .env（如果安装了 python-dotenv）
# try:
#     from dotenv import load_dotenv
#     load_dotenv()
# except ImportError:
#     pass

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
#     handlers=[
#         logging.StreamHandler(),
#         logging.FileHandler(
#             os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse.log"),
#             encoding="utf-8",
#         ),
#     ],
# )

# logger = logging.getLogger("run_parse")

# # ======================================================================
# # 路径配置
# # ======================================================================
# # RAW_DIR = r"D:\finance\finance-agent\docs\raw"
# # PARSED_DIR = r"D:\finance\finance-agent\docs\parsed"
# # KB_NAME = "finance"

# DEFAULT_RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "raw")
# DEFAULT_PARSED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "parsed")
# DEFAULT_KB_NAME = "finance"
# def check_ocr_api():
#     """检查 OCR API 连通性"""
#     api_key = os.environ.get("PARATERA_API_KEY", "")
#     if not api_key:
#         logger.warning(
#             "⚠️  PARATERA_API_KEY 未设置。\n"
#             "   扫描件 PDF 的 OCR 功能将不可用。\n"
#             "   设置方法:\n"
#             "     Windows CMD:    set PARATERA_API_KEY=你的密钥\n"
#             "     PowerShell:     $env:PARATERA_API_KEY=\"你的密钥\"\n"
#             "     或在 .env 文件中: PARATERA_API_KEY=你的密钥"
#         )
#         return False

#     logger.info("✅ PARATERA_API_KEY 已配置")
#     try:
#         from agent.parser.utils.ocr_utils import check_api_connectivity
#         check = check_api_connectivity()
#         if check["ok"]:
#             logger.info(f"✅ OCR API 连通正常: {check['message']}")
#             return True
#         else:
#             logger.warning(f"⚠️  OCR API 异常: {check['message']}")
#             return False
#     except Exception as exc:
#         logger.warning(f"⚠️  OCR 模块加载失败: {exc}")
#         return False


# def check_directories(RAW_DIR, PARSED_DIR):
#     """检查输入输出目录"""
#     if not os.path.isdir(RAW_DIR):
#         logger.error(f"❌ 源文件目录不存在: {RAW_DIR}")
#         logger.info("   请创建目录并放入待解析的文件")
#         return False

#     # 列出源文件
#     supported = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".md", ".markdown", ".txt"}
#     files = []
#     for root, _, fnames in os.walk(RAW_DIR):
#         for fn in fnames:
#             if os.path.splitext(fn)[1].lower() in supported:
#                 files.append(os.path.join(root, fn))

#     if not files:
#         logger.warning(f"⚠️  源目录为空或没有受支持的文件: {RAW_DIR}")
#         logger.info(f"   支持的格式: {', '.join(sorted(supported))}")
#         return False

#     logger.info(f"📂 源文件目录: {RAW_DIR}")
#     logger.info(f"📂 输出目录:   {PARSED_DIR}")
#     logger.info(f"📄 发现 {len(files)} 个待解析文件:")
#     for f in sorted(files):
#         size_kb = os.path.getsize(f) / 1024
#         logger.info(f"   • {os.path.basename(f)} ({size_kb:.1f} KB)")

#     # 确保输出目录存在
#     os.makedirs(PARSED_DIR, exist_ok=True)
#     return True


# def print_results(result: dict, KB_NAME=DEFAULT_KB_NAME, RAW_DIR=DEFAULT_RAW_DIR, PARSED_DIR=DEFAULT_PARSED_DIR):
#     """打印解析结果汇总"""
#     total = result.get("total", 0)
#     success = result.get("success", 0)
#     partial = result.get("partial", 0)
#     error = result.get("error", 0)

#     print()
#     print("=" * 60)
#     print("  📊 解析结果汇总")
#     print("=" * 60)
#     print(f"  知识库:   {result.get('kb_name', KB_NAME)}")
#     print(f"  源目录:   {result.get('raw_dir', RAW_DIR)}")
#     print(f"  输出目录: {result.get('parsed_dir', PARSED_DIR)}")
#     print("-" * 60)
#     print(f"  总计:   {total} 个文件")
#     print(f"  ✅ 成功: {success}")
#     print(f"  ⚠️  部分: {partial} (有警告但可用)")
#     print(f"  ❌ 失败: {error}")
#     print("-" * 60)

#     # 每个文件的详情
#     for r in result.get("results", []):
#         status = r.get("status", "error")
#         emoji = {"success": "✅", "partial": "⚠️", "error": "❌"}.get(status, "❓")
#         fname = os.path.basename(r.get("file_path", "unknown"))
#         title = r.get("title", "")
#         print(f"  {emoji} {fname}")
#         if title and title != os.path.splitext(fname)[0]:
#             print(f"      标题: {title}")
#         if r.get("tables"):
#             print(f"      📊 {len(r['tables'])} 个表格")
#         if r.get("warnings_count", 0) > 0:
#             print(f"      ⚠️  {r['warnings_count']} 个警告")
#         if r.get("errors_count", 0) > 0:
#             print(f"      ❌ {r['errors_count']} 个错误")
#         if r.get("error"):
#             print(f"      💥 {r['error']}")

#     print("-" * 60)
#     manifest = result.get("manifest_path", "")
#     if manifest:
#         print(f"  📋 清单文件: {manifest}")
#     print("=" * 60)

# def input_path(prompt, default):
#     """控制台输入路径，直接回车使用默认值"""
#     user_input = input(f"{prompt}（默认：{default}）：").strip()
#     return user_input if user_input else default
# def main():
    
#     RAW_DIR = input_path("请输入 待解析文件目录", DEFAULT_RAW_DIR)
#     PARSED_DIR = input_path("请输入 解析输出目录", DEFAULT_PARSED_DIR)
#     KB_NAME = input_path("请输入 知识库名称", DEFAULT_KB_NAME)
#     os.makedirs(PARSED_DIR, exist_ok=True)
#     print()
#     print("=" * 60)
#     print("  🔍 Finance Document Parser")
#     print(f"  知识库: {KB_NAME}")
#     print("=" * 60)
#     print()
#     # ---- Step 1: 检查目录 ----
#     if not check_directories(RAW_DIR, PARSED_DIR):
#         return None

#     # ---- Step 2: 检查 OCR ----
#     print()
#     check_ocr_api()

#     # ---- Step 3: 执行解析 ----
#     print()
#     logger.info("🚀 开始解析...")
#     print()
    
#     from agent.parser.main import parse_directory

#     result = parse_directory(
#         raw_dir=RAW_DIR,
#         parsed_dir=PARSED_DIR,
#         kb_name=KB_NAME,
#         owner="",
#         source_summary="财务相关文档",
#     )

#     # ---- Step 4: 打印结果 ----
#     print_results(result, KB_NAME=KB_NAME, RAW_DIR=RAW_DIR, PARSED_DIR=PARSED_DIR)

#     # ---- Step 5: 保存结果到 JSON ----
#     result_path = os.path.join(PARSED_DIR, "parse_result.json")
#     with open(result_path, "w", encoding="utf-8") as f:
#         json.dump(result, f, ensure_ascii=False, indent=2)
#     logger.info(f"📝 结果已保存: {result_path}")

#     return result


# if __name__ == "__main__":
#     main()

"""
统一解析脚本：支持单个文件、单目录、多目录三种模式
使用方式：
    python run_unified_parser.py
    然后根据提示输入 0/1/2 选择模式：
    0 - 单个文件解析
    1 - 单目录解析（原 run_parser.py 逻辑）
    2 - 多目录批量解析（原 run_multi_parser.py 逻辑）
"""
import logging
import sys
import os
import json

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 自动加载 .env（如果安装了 python-dotenv）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ======================== 日志配置 ========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("unified_parse")

# ======================== 路径配置 ========================
DEFAULT_RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "raw")
DEFAULT_PARSED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "parsed")
DEFAULT_KB_NAME = "finance"

# 支持的文件格式
SUPPORTED_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".md", ".markdown", ".txt"}

# ======================== 通用工具函数 ========================
def check_ocr_api():
    """检查 OCR API 连通性"""
    api_key = os.environ.get("PARATERA_API_KEY", "")
    if not api_key:
        logger.warning(
            "⚠️  PARATERA_API_KEY 未设置。\n"
            "   扫描件 PDF 的 OCR 功能将不可用。\n"
            "   设置方法:\n"
            "     Windows CMD:    set PARATERA_API_KEY=你的密钥\n"
            "     PowerShell:     $env:PARATERA_API_KEY=\"你的密钥\"\n"
            "     或在 .env 文件中: PARATERA_API_KEY=你的密钥"
        )
        return False

    logger.info("✅ PARATERA_API_KEY 已配置")
    try:
        from agent.parser.utils.ocr_utils import check_api_connectivity
        check = check_api_connectivity()
        if check["ok"]:
            logger.info(f"✅ OCR API 连通正常: {check['message']}")
            return True
        else:
            logger.warning(f"⚠️  OCR API 异常: {check['message']}")
            return False
    except Exception as exc:
        logger.warning(f"⚠️  OCR 模块加载失败: {exc}")
        return False


def input_path(prompt, default):
    """控制台输入路径，直接回车使用默认值"""
    user_input = input(f"{prompt}（默认：{default}）：").strip()
    return user_input if user_input else default


def check_single_file(file_path):
    """检查单个文件是否有效"""
    if not os.path.isfile(file_path):
        logger.error(f"❌ 文件不存在: {file_path}")
        return False
    
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in SUPPORTED_EXT:
        logger.error(f"❌ 不支持的文件格式: {file_ext}")
        logger.info(f"   支持的格式: {', '.join(sorted(SUPPORTED_EXT))}")
        return False
    
    file_size_kb = os.path.getsize(file_path) / 1024
    logger.info(f"📄 待解析文件: {file_path}")
    logger.info(f"   大小: {file_size_kb:.1f} KB")
    logger.info(f"   格式: {file_ext}")
    return True


def check_directory(raw_dir, parsed_dir):
    """检查单目录模式的输入输出目录"""
    if not os.path.isdir(raw_dir):
        logger.error(f"❌ 源文件目录不存在: {raw_dir}")
        logger.info("   请创建目录并放入待解析的文件")
        return False

    # 列出源文件
    files = []
    for root, _, fnames in os.walk(raw_dir):
        for fn in fnames:
            if os.path.splitext(fn)[1].lower() in SUPPORTED_EXT:
                files.append(os.path.join(root, fn))

    if not files:
        logger.warning(f"⚠️  源目录为空或没有受支持的文件: {raw_dir}")
        logger.info(f"   支持的格式: {', '.join(sorted(SUPPORTED_EXT))}")
        return False

    logger.info(f"📂 源文件目录: {raw_dir}")
    logger.info(f"📂 输出目录:   {parsed_dir}")
    logger.info(f"📄 发现 {len(files)} 个待解析文件:")
    for f in sorted(files):
        size_kb = os.path.getsize(f) / 1024
        logger.info(f"   • {os.path.basename(f)} ({size_kb:.1f} KB)")

    # 确保输出目录存在
    os.makedirs(parsed_dir, exist_ok=True)
    return True

# ======================== 各模式专用函数 ========================
def run_single_file_mode():
    """运行单个文件解析模式（模式 0）"""
    print("\n" + "=" * 60)
    print("  🔍 单个文件解析模式")
    print("=" * 60)
    
    # 1. 获取文件路径和输出目录
    default_file = ""
    while True:
        file_path = input_path("请输入 待解析文件路径", default_file)
        if check_single_file(file_path):
            break
        default_file = file_path  # 保留上次输入，方便修正
    
    parsed_dir = input_path("请输入 解析输出目录", DEFAULT_PARSED_DIR)
    kb_name = input_path("请输入 知识库名称", DEFAULT_KB_NAME)
    
    # 确保输出目录存在
    os.makedirs(parsed_dir, exist_ok=True)
    
    # 2. 检查 OCR API
    print()
    check_ocr_api()
    
    # 3. 执行解析（单个文件）
    print()
    logger.info("🚀 开始解析单个文件...")
    print()
    
    try:
        from agent.parser.main import parse_file  # 假设存在单个文件解析函数
        # 如果 parse_file 不存在，改用 parse_directory 适配
        # 先创建临时目录，复制文件过去，再解析
        result = parse_file(
            file_path=file_path,
            parsed_dir=parsed_dir,
            kb_name=kb_name,
            owner="",
            source_summary="单个文件解析"
        )
        
        # 4. 打印单个文件解析结果
        print_single_file_result(result, file_path, parsed_dir)
        
        # 5. 保存结果
        result_path = os.path.join(parsed_dir, f"{os.path.splitext(os.path.basename(file_path))[0]}_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"📝 结果已保存: {result_path}")
        
    except ImportError:
        # 备用方案：如果没有 parse_file 函数，用目录解析适配
        logger.warning("⚠️  未找到单个文件解析函数，使用目录解析适配")
        temp_raw_dir = os.path.join(os.path.dirname(__file__), "temp_single_file")
        os.makedirs(temp_raw_dir, exist_ok=True)
        
        # 复制文件到临时目录
        import shutil
        temp_file_path = os.path.join(temp_raw_dir, os.path.basename(file_path))
        shutil.copy2(file_path, temp_file_path)
        
        # 调用目录解析
        from agent.parser.main import parse_directory
        result = parse_directory(
            raw_dir=temp_raw_dir,
            parsed_dir=parsed_dir,
            kb_name=kb_name,
            owner="",
            source_summary="单个文件解析（适配模式）"
        )
        
        # 打印结果
        print_results(result, kb_name, temp_raw_dir, parsed_dir)
        
        # 删除临时目录
        shutil.rmtree(temp_raw_dir)
        
        # 保存结果
        result_path = os.path.join(parsed_dir, f"{os.path.splitext(os.path.basename(file_path))[0]}_result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"📝 结果已保存: {result_path}")
        
    except Exception as e:
        logger.error(f"❌ 解析失败: {str(e)}")
        return None
    
    return result


def run_single_directory_mode():
    """运行单目录解析模式（模式 1，原 run_parser.py 逻辑）"""
    print("\n" + "=" * 60)
    print("  🔍 单目录解析模式")
    print(f"  知识库: {DEFAULT_KB_NAME}")
    print("=" * 60)
    
    # 1. 获取用户输入路径
    raw_dir = input_path("请输入 待解析文件目录", DEFAULT_RAW_DIR)
    parsed_dir = input_path("请输入 解析输出目录", DEFAULT_PARSED_DIR)
    kb_name = input_path("请输入 知识库名称", DEFAULT_KB_NAME)
    
    os.makedirs(parsed_dir, exist_ok=True)
    
    # 2. 检查目录有效性
    if not check_directory(raw_dir, parsed_dir):
        return None
    
    # 3. 检查 OCR API
    print()
    check_ocr_api()
    
    # 4. 执行解析
    print()
    logger.info("🚀 开始解析目录...")
    print()
    
    from agent.parser.main import parse_directory
    result = parse_directory(
        raw_dir=raw_dir,
        parsed_dir=parsed_dir,
        kb_name=kb_name,
        owner="",
        source_summary="财务相关文档",
    )
    
    # 5. 打印结果
    print_results(result, kb_name, raw_dir, parsed_dir)
    
    # 6. 保存结果到 JSON
    result_path = os.path.join(parsed_dir, "parse_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"📝 结果已保存: {result_path}")
    
    return result


def run_multi_directory_mode():
    """运行多目录批量解析模式（模式 2，原 run_multi_parser.py 逻辑）"""
    print("\n" + "=" * 60)
    print("  🔍 多目录批量解析模式")
    print("=" * 60)
    
    # 1. 获取用户输入根路径
    raw_root = input_path("请输入 根待解析目录", DEFAULT_RAW_DIR)
    parsed_root = input_path("请输入 根输出目录", DEFAULT_PARSED_DIR)
    print()
    
    # 2. 检查根目录是否存在
    if not os.path.isdir(raw_root):
        logger.error(f"❌ 目录不存在：{raw_root}")
        return None
    
    # 3. 自动获取 raw 下所有子文件夹（每个子文件夹=一个知识库）
    kb_folders = []
    for name in os.listdir(raw_root):
        full_path = os.path.join(raw_root, name)
        if os.path.isdir(full_path):
            kb_folders.append(name)
    
    if not kb_folders:
        logger.error(f"❌ 在 {raw_root} 下未找到任何子文件夹（知识库）")
        return None
    
    logger.info(f"📂 发现 {len(kb_folders)} 个知识库：")
    for folder in kb_folders:
        logger.info(f"   • {folder}")
    print()
    
    # 4. 检查 OCR API
    check_ocr_api()
    print()
    
    # 5. 批量遍历每个文件夹（每个知识库）
    all_results = {}
    from agent.parser.main import parse_directory
    
    for kb_name in kb_folders:
        raw_sub = os.path.join(raw_root, kb_name)
        parsed_sub = os.path.join(parsed_root, kb_name)
        os.makedirs(parsed_sub, exist_ok=True)
    
        logger.info(f"🚀 开始解析 知识库：[{kb_name}]")
        logger.info(f"   输入：{raw_sub}")
        logger.info(f"   输出：{parsed_sub}")
    
        result = parse_directory(
            raw_dir=raw_sub,
            parsed_dir=parsed_sub,
            kb_name=kb_name,
            owner="",
            source_summary=f"知识库：{kb_name}"
        )
    
        # 打印单个知识库结果
        print_results(result, kb_name, raw_sub, parsed_sub)
        all_results[kb_name] = result
    
        # 保存单知识库结果
        result_file = os.path.join(parsed_sub, "parse_result.json")
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    
    # 6. 保存总结果
    total_result_file = os.path.join(parsed_root, "all_kb_results.json")
    with open(total_result_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    
    logger.info("✅ 所有知识库解析完成！")
    logger.info(f"📝 总结果：{total_result_file}")
    
    return all_results

# ======================== 结果打印函数 ========================
def print_single_file_result(result: dict, file_path, parsed_dir):
    """打印单个文件解析结果"""
    print()
    print("=" * 60)
    print("  📊 单个文件解析结果")
    print("=" * 60)
    print(f"  文件路径: {file_path}")
    print(f"  输出目录: {parsed_dir}")
    print("-" * 60)
    
    status = result.get("status", "error")
    emoji = {"success": "✅", "partial": "⚠️", "error": "❌"}.get(status, "❓")
    print(f"  解析状态: {emoji} {status.upper()}")
    
    if status != "error":
        title = result.get("title", "")
        if title:
            print(f"  文件标题: {title}")
        tables = result.get("tables", [])
        if tables:
            print(f"  提取表格: {len(tables)} 个")
        warnings = result.get("warnings_count", 0)
        if warnings > 0:
            print(f"  警告数量: ⚠️ {warnings}")
    
    if result.get("error"):
        print(f"  错误信息: ❌ {result['error']}")
    
    manifest = result.get("manifest_path", "")
    if manifest:
        print(f"  清单文件: 📋 {manifest}")
    print("=" * 60)


def print_results(result: dict, kb_name, raw_dir, parsed_dir):
    """打印目录解析结果汇总（兼容单目录/多目录）"""
    total = result.get("total", 0)
    success = result.get("success", 0)
    partial = result.get("partial", 0)
    error = result.get("error", 0)

    print()
    print("=" * 60)
    if "知识库" in kb_name:
        print(f"  📊 知识库：【{kb_name}】解析完成")
    else:
        print("  📊 解析结果汇总")
    print("=" * 60)
    print(f"  知识库:   {kb_name}")
    print(f"  源目录:   {raw_dir}")
    print(f"  输出目录: {parsed_dir}")
    print("-" * 60)
    print(f"  总计:   {total} 个文件")
    print(f"  ✅ 成功: {success}")
    print(f"  ⚠️  部分: {partial} (有警告但可用)")
    print(f"  ❌ 失败: {error}")
    print("-" * 60)

    # 每个文件的详情
    for r in result.get("results", []):
        status = r.get("status", "error")
        emoji = {"success": "✅", "partial": "⚠️", "error": "❌"}.get(status, "❓")
        fname = os.path.basename(r.get("file_path", "unknown"))
        title = r.get("title", "")
        print(f"  {emoji} {fname}")
        if title and title != os.path.splitext(fname)[0]:
            print(f"      标题: {title}")
        if r.get("tables"):
            print(f"      📊 {len(r['tables'])} 个表格")
        if r.get("warnings_count", 0) > 0:
            print(f"      ⚠️  {r['warnings_count']} 个警告")
        if r.get("errors_count", 0) > 0:
            print(f"      ❌ {r['errors_count']} 个错误")
        if r.get("error"):
            print(f"      💥 {r['error']}")

    print("-" * 60)
    manifest = result.get("manifest_path", "")
    if manifest:
        print(f"  📋 清单文件: {manifest}")
    print("=" * 60)

# ======================== 主函数 ========================
def main():
    print("=" * 60)
    print("  🎯 统一文档解析工具")
    print("=" * 60)
    print("  请选择运行模式：")
    print("  0 - 单个文件解析")
    print("  1 - 单目录解析（原 run_parser.py）")
    print("  2 - 多目录批量解析（原 run_multi_parser.py）")
    print("=" * 60)
    
    # 获取用户模式选择
    while True:
        mode_input = input("请输入模式编号（0/1/2）：").strip()
        if mode_input in ["0", "1", "2"]:
            mode = int(mode_input)
            break
        logger.warning("❌ 无效输入！请输入 0、1 或 2")
    
    # 执行对应模式
    if mode == 0:
        run_single_file_mode()
    elif mode == 1:
        run_single_directory_mode()
    elif mode == 2:
        run_multi_directory_mode()

    print()
    logger.info("🎉 解析流程执行完成！")

if __name__ == "__main__":
    main()