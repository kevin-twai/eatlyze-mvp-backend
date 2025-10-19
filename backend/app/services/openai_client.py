# backend/app/services/openai_client.py
from __future__ import annotations
import os, json, asyncio, httpx, logging

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

# ── 模型：先用 mini，失敗再 fallback 到 4o ───────────────────────────────
PRIMARY_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = "gpt-4o"

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}


def _vision_messages_from_b64(image_b64: str):
    """
    建立帶圖片的 messages（符合 Chat Completions 規範）
    注意：image 要用 type: input_image，且 image_url 需為物件：{"url": "..."}
    """
    data_url = f"data:image/jpeg;base64,{image_b64}"

    return [
        {
            "role": "system",
            "content": (
                "You are a nutrition vision assistant. Analyze the food photo and return pure JSON. "
                "JSON schema: {\"items\":[{\"name\":\"string\",\"canonical\":\"string(optional)\","
                "\"weight_g\":number,\"is_garnish\":boolean}]}. "
                "No extra text, no markdown, just a JSON object."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Detect the edible items (food/ingredients) in the image. "
                        "Estimate weight_g for each item (rough guess is fine). "
                        "Mark small decorations as is_garnish=true."
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": { "url": data_url },
                },
            ],
        },
    ]


async def _openai_chat_json(image_b64: str, *, model: str, temp: float, max_tokens: int):
    """
    呼叫 Chat Completions 取得 JSON（帶重試與 429 退避）
    """
    payload = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tokens,
        # 讓模型輸出真正的 JSON（無 markdown）
        "response_format": { "type": "json_object" },
        "messages": _vision_messages_from_b64(image_b64),
    }

    async with httpx.AsyncClient(timeout=60) as client:
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
                body = e.response.text
                logger.error(f"[openai] HTTP error ({model}): {e.response.status_code} {body[:200]}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.exception(f"[openai] request failed ({model}): {e}")
                await asyncio.sleep(2)

    raise RuntimeError(f"OpenAI API failed after retries (model={model})")


async def vision_analyze_base64(image_b64: str) -> dict:
    """
    主要入口：先用 PRIMARY_MODEL，失敗再 fallback 到 FALLBACK_MODEL
    回傳 dict（已解析的 JSON）
    """
    try:
        logger.info(f"[vision] Using primary model: {PRIMARY_MODEL}")
        res = await _openai_chat_json(image_b64, model=PRIMARY_MODEL, temp=0.25, max_tokens=600)
    except Exception as e1:
        logger.warning(f"[vision] {PRIMARY_MODEL} failed: {e1}, fallback to {FALLBACK_MODEL}")
        try:
            res = await _openai_chat_json(image_b64, model=FALLBACK_MODEL, temp=0.3, max_tokens=600)
        except Exception as e2:
            logger.error(f"[vision] Both models failed: {e2}")
            raise RuntimeError(f"Vision analysis failed for both models ({e1}, {e2})")

    # 解析 JSON
    try:
        content = res["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return parsed
    except Exception as e:
        logger.exception("[vision] JSON parse failed")
        raise RuntimeError(f"Invalid JSON response: {e}")
