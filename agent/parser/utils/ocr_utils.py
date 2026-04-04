"""
agent/parser/utils/ocr_utils.py

OCR 工具 —— 通过 ds API (Paratera 平台) 实现。
API 文档: https://ai.paratera.com/document/llm/quickStart/useApi

调用方式：OpenAI 兼容的 Chat Completions 接口，发送 base64 图片。
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置（从环境变量读取，不要硬编码密钥）
# ---------------------------------------------------------------------------
PARATERA_API_KEY = "sk-YNXuBle27-wX1oeQZmlRCg"
PARATERA_API_BASE = os.environ.get(
    "PARATERA_API_BASE", "https://llmapi.paratera.com"
)
PARATERA_OCR_MODEL = os.environ.get(
    "PARATERA_OCR_MODEL", "DeepSeek-OCR"
)

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒
REQUEST_TIMEOUT = 60  # 秒


# ---------------------------------------------------------------------------
# 核心 OCR 函数
# ---------------------------------------------------------------------------
def run_ocr(image_bytes: bytes, detail: str = "high") -> str:
    """
    对图片字节执行 OCR，返回识别文本。

    使用 ds (Paratera 平台 OpenAI 兼容接口)。
    图片以 base64 编码发送。

    Args:
        image_bytes: 图片的原始字节
        detail: 识别精度 "high" / "low"

    Returns:
        识别出的文本内容
    """
    api_key = PARATERA_API_KEY
    if not api_key:
        logger.error(
            "PARATERA_API_KEY not set. "
            "Please set environment variable: export PARATERA_API_KEY=your_key"
        )
        return "[OCR ERROR: PARATERA_API_KEY not configured]"

    # 编码图片为 base64
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    # 检测图片类型
    mime_type = _detect_mime_type(image_bytes)

    # 构造 OpenAI 兼容的请求体
    url = f"{PARATERA_API_BASE}/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": PARATERA_OCR_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个高精度 OCR 工具。请仔细识别图片中的所有文字内容，"
                    "包括表格、标题、正文、页眉页脚等。"
                    "请保持原文的结构和格式（如换行、缩进、表格行列关系）。"
                    "只输出识别到的文字，不要添加任何解释或评论。"
                    "如果图片中有表格，请用 Markdown 表格格式输出。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                            "detail": detail,
                        },
                    },
                    {
                        "type": "text",
                        "text": "请识别此图片中的所有文字内容，保持原始排版结构。",
                    },
                ],
            },
        ],
        "max_tokens": 4096,
        "temperature": 0.0,  # OCR 需要确定性输出
    }

    # 带重试的请求
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                f"OCR API request (attempt {attempt}/{MAX_RETRIES}), "
                f"image size: {len(image_bytes)} bytes"
            )
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if resp.status_code == 200:
                result = resp.json()
                text = _extract_text_from_response(result)
                logger.info(f"OCR success: {len(text)} chars extracted")
                return text

            elif resp.status_code == 429:
                # 限流，等待后重试
                wait = RETRY_DELAY * attempt
                logger.warning(f"Rate limited (429), waiting {wait}s...")
                time.sleep(wait)
                continue

            elif resp.status_code in (500, 502, 503):
                # 服务端错误，重试
                wait = RETRY_DELAY * attempt
                logger.warning(
                    f"Server error ({resp.status_code}), waiting {wait}s..."
                )
                time.sleep(wait)
                continue

            else:
                error_msg = f"OCR API error: HTTP {resp.status_code}"
                try:
                    error_detail = resp.json()
                    error_msg += f" - {json.dumps(error_detail, ensure_ascii=False)}"
                except Exception:
                    error_msg += f" - {resp.text[:500]}"
                logger.error(error_msg)
                return f"[OCR ERROR: {error_msg}]"

        except requests.exceptions.Timeout:
            logger.warning(f"OCR API timeout (attempt {attempt})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return "[OCR ERROR: API request timed out after all retries]"

        except requests.exceptions.ConnectionError as exc:
            logger.warning(f"OCR API connection error (attempt {attempt}): {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return f"[OCR ERROR: Connection failed - {exc}]"

        except Exception as exc:
            logger.error(f"OCR unexpected error: {exc}")
            return f"[OCR ERROR: {exc}]"

    return "[OCR ERROR: All retries exhausted]"



def run_ocr_on_file(image_path: str, detail: str = "high") -> str:
    """对图片文件执行 OCR"""
    return run_ocr(Path(image_path).read_bytes(), detail=detail)


def run_ocr_batch(
    image_list: list[bytes],
    delay_between: float = 0.5,
) -> list[str]:
    """
    批量 OCR，每次调用之间加延迟以避免限流。
    """
    results = []
    for i, img_bytes in enumerate(image_list):
        logger.info(f"OCR batch: {i+1}/{len(image_list)}")
        text = run_ocr(img_bytes)
        results.append(text)
        if i < len(image_list) - 1:
            time.sleep(delay_between)
    return results


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _extract_text_from_response(response: dict) -> str:
    """从 OpenAI 兼容的响应中提取文本"""
    try:
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")
            return content.strip()
    except (IndexError, KeyError, TypeError) as exc:
        logger.warning(f"Failed to extract text from response: {exc}")
    return ""


def _detect_mime_type(image_bytes: bytes) -> str:
    """根据文件头检测图片 MIME 类型"""
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif image_bytes[:4] == b'GIF8':
        return "image/gif"
    elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    elif image_bytes[:4] in (b'II\x2a\x00', b'MM\x00\x2a'):
        return "image/tiff"
    elif image_bytes[:4] == b'%PDF':
        return "application/pdf"
    else:
        return "image/png"  # 默认


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------
def check_api_connectivity() -> dict:
    """
    检查 API 连通性（不发送图片，仅测试认证）。
    返回 {"ok": bool, "message": str}
    """
    api_key = PARATERA_API_KEY
    if not api_key:
        return {
            "ok": False,
            "message": "PARATERA_API_KEY not set",
        }

    url = f"{PARATERA_API_BASE}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return {"ok": True, "message": "API connection OK"}
        else:
            return {
                "ok": False,
                "message": f"HTTP {resp.status_code}: {resp.text[:200]}",
            }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}