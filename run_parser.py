"""
D:/finance/finance-agent/run_parse.py

一键解析脚本。双击或在终端运行即可。

使用前请设置环境变量：
    set PARATERA_API_KEY=你的密钥      (Windows CMD)
    $env:PARATERA_API_KEY="你的密钥"   (PowerShell)
    export PARATERA_API_KEY=你的密钥    (Linux/Mac)
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

logger = logging.getLogger("run_parse")

# ======================================================================
# 路径配置
# ======================================================================
RAW_DIR = r"D:\finance\finance-agent\docs\raw"
PARSED_DIR = r"D:\finance\finance-agent\docs\parsed"
KB_NAME = "finance"


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


def check_directories():
    """检查输入输出目录"""
    if not os.path.isdir(RAW_DIR):
        logger.error(f"❌ 源文件目录不存在: {RAW_DIR}")
        logger.info("   请创建目录并放入待解析的文件")
        return False

    # 列出源文件
    supported = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".md", ".markdown", ".txt"}
    files = []
    for root, _, fnames in os.walk(RAW_DIR):
        for fn in fnames:
            if os.path.splitext(fn)[1].lower() in supported:
                files.append(os.path.join(root, fn))

    if not files:
        logger.warning(f"⚠️  源目录为空或没有受支持的文件: {RAW_DIR}")
        logger.info(f"   支持的格式: {', '.join(sorted(supported))}")
        return False

    logger.info(f"📂 源文件目录: {RAW_DIR}")
    logger.info(f"📂 输出目录:   {PARSED_DIR}")
    logger.info(f"📄 发现 {len(files)} 个待解析文件:")
    for f in sorted(files):
        size_kb = os.path.getsize(f) / 1024
        logger.info(f"   • {os.path.basename(f)} ({size_kb:.1f} KB)")

    # 确保输出目录存在
    os.makedirs(PARSED_DIR, exist_ok=True)
    return True


def print_results(result: dict):
    """打印解析结果汇总"""
    total = result.get("total", 0)
    success = result.get("success", 0)
    partial = result.get("partial", 0)
    error = result.get("error", 0)

    print()
    print("=" * 60)
    print("  📊 解析结果汇总")
    print("=" * 60)
    print(f"  知识库:   {result.get('kb_name', KB_NAME)}")
    print(f"  源目录:   {result.get('raw_dir', RAW_DIR)}")
    print(f"  输出目录: {result.get('parsed_dir', PARSED_DIR)}")
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


def main():
    print()
    print("=" * 60)
    print("  🔍 Finance Document Parser")
    print(f"  知识库: {KB_NAME}")
    print("=" * 60)
    print()

    # ---- Step 1: 检查目录 ----
    if not check_directories():
        return None

    # ---- Step 2: 检查 OCR ----
    print()
    check_ocr_api()

    # ---- Step 3: 执行解析 ----
    print()
    logger.info("🚀 开始解析...")
    print()

    from agent.parser.main import parse_directory

    result = parse_directory(
        raw_dir=RAW_DIR,
        parsed_dir=PARSED_DIR,
        kb_name=KB_NAME,
        owner="",
        source_summary="财务相关文档",
    )

    # ---- Step 4: 打印结果 ----
    print_results(result)

    # ---- Step 5: 保存结果到 JSON ----
    result_path = os.path.join(PARSED_DIR, "parse_result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info(f"📝 结果已保存: {result_path}")

    return result


if __name__ == "__main__":
    main()