# backend/app/services/openai_client.py
from __future__ import annotations
import os, json, asyncio, httpx, base64, logging

logger = logging.getLogger(__name__)

# ---- 模型設定 ----
PRIMARY_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # 預設用 mini
FALLBACK_MODEL = "gpt-4o"  # 若 mini 失敗，再試一次 4o
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

HEADERS = {"Authorization": f"Bearer {OPENAI_API_KEY}"}


async def _openai_chat_json(image_b64: str, model: str, temp=0.3, max_tokens=600):
    """送出 vision 請求並回傳 JSON 結果"""
    payload = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a nutrition vision assistant. "
                    "Analyze the food photo and return JSON with fields: "
                    '{"items":[{"name":"","weight_g":"","is_garnish":false}]}. '
                    "Do not include explanations or markdown."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this food image and list the dishes."},
                    {"type": "image_url", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                ],
            },
        ],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(3):
            try:
                r = await client.post(OPENAI_URL, headers=HEADERS, json=payload)
                if r.status_code == 429:
                    delay = 3 * (attempt + 1)
                    logger.warning(f"[openai] rate limited ({model}), retry {attempt+1}/3 in {delay}s…")
                    await asyncio.sleep(delay)
                    continue
                r.raise_for_status()
                return r.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"[openai] HTTP error ({model}): {e.response.status_code} {e.response.text[:120]}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.exception(f"[openai] request failed ({model}): {e}")
                await asyncio.sleep(2)

    raise RuntimeError(f"OpenAI API failed after retries (model={model})")


async def vision_analyze_base64(image_b64: str):
    """主要 Vision 分析邏輯 + 自動 fallback"""
    try:
        logger.info(f"[vision] Using primary model: {PRIMARY_MODEL}")
        res = await _openai_chat_json(image_b64, PRIMARY_MODEL)
    except Exception as e1:
        logger.warning(f"[vision] {PRIMARY_MODEL} failed: {e1}, fallback to {FALLBACK_MODEL}")
        try:
            res = await _openai_chat_json(image_b64, FALLBACK_MODEL)
        except Exception as e2:
            logger.error(f"[vision] Both models failed: {e2}")
            raise RuntimeError(f"Vision analysis failed for both models ({e1}, {e2})")

    # ---- 解析 JSON ----
    try:
        content = res["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        logger.exception("[vision] JSON parse failed")
        raise RuntimeError(f"Invalid JSON response: {e}")
