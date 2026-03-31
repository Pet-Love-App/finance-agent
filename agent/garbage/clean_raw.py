# 我们首先对文件的命名进行规范化，去掉特殊字符，保留中文、英文、数字和下划线，并在文件名末尾添加日期戳。
# 其次，我们会删除一些明显的垃圾文件，比如临时文件、日志文件等，以及空文件和PDF中的空白页。
# 最后，我们将处理后的文件复制到新的目录中，保持原始文件不变。
import os
import re
import shutil
from datetime import datetime
from PyPDF2 import PdfReader

# ===================== 配置项（你只需要改这里） =====================
INPUT_DIR = "D:\\finance\\finance-agent\\docs\\raw"    # 原始杂乱文件目录
OUTPUT_DIR = "D:\\finance\\finance-agent\\docs\\clean_raw"          # 输出规范后的目录
TODAY = datetime.now().strftime("%Y%m%d")
# ===================================================================

# 要删除的垃圾文件后缀
NOISE_EXT = [".tmp", ".bak", ".log", ".ds_store", ".thumb", ".exe", ".zip", ".rar"]

# 空白页判断：字符数 < 20 视为空白
BLANK_TEXT_THRESHOLD = 20

def clean_filename(filename):
    """规范化文件名：只保留中文、英文、数字、下划线，删除特殊符号"""
    name, ext = os.path.splitext(filename)
    name = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)  # 替换非法字符为 _
    name = re.sub(r'_+', '_', name)                  # 多个下划线变一个
    name = name.strip("_")
    return f"{name}_{TODAY}{ext}".lower()

def is_pdf_blank(pdf_path):
    """判断PDF是否空白页"""
    try:
        reader = PdfReader(pdf_path)
        text = reader.pages[0].extract_text() or ""
        return len(text.strip()) < BLANK_TEXT_THRESHOLD
    except:
        return True

def is_file_empty(file_path):
    """判断文件是否为空"""
    return os.path.getsize(file_path) < 100  # 小于100字节视为空

def process_file(file_path, filename):
    """处理单个文件：去噪 + 重命名"""
    # 1. 跳过垃圾后缀
    ext = os.path.splitext(filename)[-1].lower()
    if ext in NOISE_EXT:
        return "跳过垃圾文件"

    # 2. 跳过空文件
    if is_file_empty(file_path):
        return "删除空文件"

    # 3. PDF 跳过空白页
    if ext == ".pdf" and is_pdf_blank(file_path):
        return "删除PDF空白页"

    # 4. 规范化命名
    new_name = clean_filename(filename)
    new_path = os.path.join(OUTPUT_DIR, new_name)

    # 5. 复制到输出目录（不修改原文件）
    shutil.copy2(file_path, new_path)
    return f"✅ 已规范：{new_name}"

def batch_clean_raw():
    """批量清理 raw 目录"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"📅 今日日期：{TODAY}")
    print(f"📂 原始目录：{INPUT_DIR}")
    print(f"📂 输出目录：{OUTPUT_DIR}\n")

    for filename in os.listdir(INPUT_DIR):
        file_path = os.path.join(INPUT_DIR, filename)
        if os.path.isfile(file_path):
            result = process_file(file_path, filename)
            print(f"{filename:40} → {result}")

    print("\n🎉 第二步自动化完成！raw 目录已干净、命名规范！")

if __name__ == "__main__":
    batch_clean_raw()