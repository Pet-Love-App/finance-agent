import sys
from pathlib import Path

# 确保能导入 ocr_utils
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent.parser.utils.ocr_utils import run_ocr, check_api_connectivity

# ----------------------
# 第一步：测试 API 连通性
# ----------------------
print("🔍 检查 OCR API 连通性...")
res = check_api_connectivity()
print(f"连通性结果: {res}")

if not res["ok"]:
    print("❌ API 连通失败，退出测试")
    sys.exit(1)

# ----------------------
# 第二步：用一张小图片测试真实 OCR
# ----------------------
print("\n📷 测试 OCR 识别（使用测试图片）...")

# 随便找一张本地小图片（你自己替换路径）
test_image_path = "test.png"

try:
    with open(test_image_path, "rb") as f:
        img_bytes = f.read()

    text = run_ocr(img_bytes)
    print("\n✅ OCR 返回结果:")
    print(text)

except Exception as e:
    print(f"❌ OCR 测试失败: {e}")