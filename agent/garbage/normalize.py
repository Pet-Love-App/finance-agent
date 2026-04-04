import os
import re


RAW_DIR = r"D:\finance\finance-agent\docs\raw"
NORMALIZED_DIR = r"D:\finance\finance-agent\docs\clean_raw"

# 这里的元数据是非常粗糙的匹配方法，如果后续需要，可以对文件提供更好的命名，更好的时间信息
def make_meta(filename):
    """从文件名中提取元信息，返回一个字典"""
    meta = {
        "title": os.path.splitext(filename)[0],
        "source": filename,
        "encoding": "utf-8",  
        "date": None,
        "type": None
    }
    # 1. 提取日期戳
    date_match = re.search(r'(\d{8})', filename)
    if date_match:
        meta['date'] = date_match.group(1)
    else:
        meta['date'] = None

    # 2. 提取文件类型
    ext = os.path.splitext(filename)[-1].lower()
    if ext in ['.pdf', '.docx', '.xlsx', '.pptx']:
        meta['type'] = ext[1:]  # 去掉点
    else:
        meta['type'] = 'unknown'

    return meta

def save_meta(target_path):
    """将元信息保存为JSON文件"""
    import json
    meta_path = os.path.splitext(target_path)[0] + ".meta.json"
    meta = make_meta(os.path.basename(target_path))
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)

# 先给出ocr的接口，后续如果需要，可以替换成更好的ocr引擎
def ocr_image(image_path):

def process_text_file(filename):
    raise NotImplementedError

def normalize_files():
    ensure_dir(NORMALIZED_DIR)
    for filename in os.listdir(RAW_DIR):
        raw_path = os.path.join(RAW_DIR,filename)
        if not os.path.isfile(raw_path):
            continue

        type = os.path.splitext(filename)[-1].lower()

        match type:
            case '.md' | '.txt' | '.csv' :
                process_text_file(filename)# 这是无需过多处理的部分
            case '.pdf':
                process_pdf_file(filename) # pdf的处理包括但不限于如果不可复制，需要ocr，如果是扫描件需要ocr，如果是文本pdf需要提取文本
            case '.docx':
                process_docx_file(filename) # docx的处理需要转为md，图片文字也要ocr
            case '.xlsx'|'.xls':
                process_xlsx_file(filename) # xlsx的处理需要转为csv
            case '.pptx':
                process_pptx_file(filename) # pptx的处理需要转为md
            case '.png'|'.jpg'|'.jpeg'|'.bmp'|'.gif':
                process_image_file(filename) # 图片的处理需要转为jpg，并且生成缩略
            case _:
                continue
        