# backend/app/services/openai_client.py
from __future__ import annotations

import os, json, httpx, logging

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = "https://api.openai.com/v1"
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")  # 安全預設

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}" if OPENAI_API_KEY else "",
    "Content-Type": "application/json",
}

PROMPT = (
    "你是一個只能輸出 JSON 的助手。"
    "輸入是一張餐點照片，請辨識主要食材，回傳陣列 items，每個元素："
    "{ name: 食材原文或中文, canonical: 英文或統一名, weight_g: number, is_garnish: boolean }。"
    "weight_g 為推估重量（整數或小數），沒有的也請估。is_garnish 為配菜/裝飾請標 true。"
    "禁止回任何多餘文字，僅回：{ \"items\": [...] }。"
)

def _data_url_from_b64(img_b64: str) -> str:
    # 預設當成 jpeg；如果你想更準，可從檔頭 sniff mime
    return f"data:image/jpeg;base64,{img_b64}"

async def vision_analyze_base64(img_b64: str) -> dict:
    """
    呼叫 OpenAI Chat Completions（Vision）。回傳 dict，例如 { "items": [...] }。
    在任何非 2xx 會將 response text 打 log，並拋 RuntimeError。
    """
    assert OPENAI_API_KEY, "OPENAI_API_KEY missing"

    payload = {
        "model": VISION_MODEL,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": _data_url_from_b64(img_b64)}},
                ],
            }
        ],
    }

    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            r = await client.post(
                f"{OPENAI_API_BASE}/chat/completions",
                headers=HEADERS,
                json=payload,
            )
        except httpx.HTTPError as e:
            logger.exception("HTTP error calling OpenAI")
            raise RuntimeError("OpenAI HTTP error") from e

    if r.status_code // 100 != 2:
        # 400 這邊會把 body 打出來
        logger.error("OpenAI bad response %s: %s", r.status_code, r.text)
        raise RuntimeError(f"OpenAI returned {r.status_code}")

    try:
        data = r.json()
        content = (
            data["choices"][0]["message"]["content"]
            if data.get("choices")
            else ""
        )
    except Exception:
        logger.exception("Unexpected OpenAI schema: %s", r.text[:500])
        raise RuntimeError("OpenAI response parse error")

    # OpenAI 會回「字串 JSON」，要再 parse 一次
    try:
        parsed = json.loads(content)
    except Exception:
        logger.error("OpenAI content is not valid JSON: %s", content[:500])
        raise RuntimeError("OpenAI content not JSON")

    if not isinstance(parsed, dict) or "items" not in parsed:
        logger.error("OpenAI JSON missing items: %s", parsed)
        raise RuntimeError("OpenAI JSON missing 'items'")

    return parsed
