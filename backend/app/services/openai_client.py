# backend/app/services/openai_client.py
from __future__ import annotations

import os
import json
import logging
import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()  # 小、快、夠用

# 超時與重試設定
_DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0, read=20.0, write=20.0)
_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY is empty – vision will fail without it.")


def _strip_code_fences(s: str) -> str:
    """移除```…```或```json…```包裹，避免 JSONDecodeError"""
    if not isinstance(s, str):
        return s
    s = s.strip()
    if s.startswith("```"):
        # 去掉開頭 ``` 或 ```json
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        # 去掉結尾 ```
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _build_messages(img_b64: str):
    prompt = (
        "你是營養辨識助手。請只輸出 JSON 物件（不要多餘文字）。"
        "從餐點照片中列出主要食材與推測重量(克)。"
        "欄位：name(中文)、canonical(英文或中文常見寫法)、weight_g(數字)、is_garnish(是否配菜/裝飾，布林)。"
        "僅列出你有把握的項目，重量為整數或一位小數。"
    )
    return [
        {
            "role": "system",
            "content": "You are a precise vision analyst that returns ONLY valid JSON objects.",
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}",
                        "detail": "low",  # 更快
                    },
                },
            ],
        },
    ]


async def vision_analyze_base64(img_b64: str) -> dict:
    """
    呼叫 OpenAI Vision 並回傳 Python 物件：
    {"items": [{"name": "...", "canonical": "...", "weight_g": 123, "is_garnish": false}, ...]}
    任何錯誤都 raise RuntimeError，讓路由轉成 JSON 錯誤。
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")

    url = f"{OPENAI_BASE_URL}/chat/completions"
    payload = {
        "model": OPENAI_MODEL,
        "messages": _build_messages(img_b64),
        "temperature": 0.2,
        "max_tokens": 400,  # 控制成本 & 速度
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            r = await client.post(url, headers=_HEADERS, json=payload)
            r.raise_for_status()
    except httpx.HTTPStatusError as e:
        # 伺服器/用戶錯誤（含 400/401/429/5xx）
        logger.error("OpenAI HTTP %s: %s", e.response.status_code, e.response.text)
        raise RuntimeError(f"OpenAI HTTP {e.response.status_code}") from e
    except Exception as e:
        logger.exception("OpenAI request failed")
        raise RuntimeError("OpenAI request failed") from e

    data = r.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("Unexpected OpenAI response: %s", json.dumps(data)[:500])
        raise RuntimeError("OpenAI response shape unexpected") from e

    # 移除可能的 code fences
    content = _strip_code_fences(content)

    # 解析 JSON
    try:
        parsed = json.loads(content)
    except Exception:
        logger.error("OpenAI content is not valid JSON: %r", content[:500])
        raise RuntimeError("OpenAI content not JSON")

    # 正規化輸出：確保有 items 並為 list
    items = parsed.get("items", parsed if isinstance(parsed, list) else None)
    if not isinstance(items, list):
        # 統一回傳結構
        parsed = {"items": []}
    else:
        parsed = {"items": items}
    return parsed
