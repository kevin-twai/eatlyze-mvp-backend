# backend/app/services/openai_client.py
from __future__ import annotations

import os, json, httpx, logging, re
from typing import Any, Dict

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_BASE = "https://api.openai.com/v1"
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}" if OPENAI_API_KEY else "",
    "Content-Type": "application/json",
}

PROMPT = (
    "你是一個只能輸出 JSON 的助手。"
    "輸入是一張餐點照片，請辨識主要食材，回傳："
    "{ \"items\": [ { \"name\": <字串>, \"canonical\": <字串>, \"weight_g\": <數字>, \"is_garnish\": <布林> }, ... ] }。"
    "weight_g 為推估重量（整數或小數），沒有的也請估。is_garnish 為配菜/裝飾請標 true。"
    "只輸出 JSON，本身不得包含說明文字或 ``` 程式碼區塊。"
)

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.DOTALL)
_JSON_BLOCK = re.compile(r"(\{[\s\S]*\}|$begin:math:display$[\\s\\S]*$end:math:display$)")

def _strip_code_fence(s: str) -> str:
    # 去除前後 ``` 或 ```json
    return _CODE_FENCE.sub("", s or "")

def _parse_model_json(content: str) -> Dict[str, Any]:
    """
    盡力把模型回覆解成 JSON：
    1) 先去掉 ```/```json；直接 json.loads
    2) 失敗則用正則抓第一個 {...} 或 [...]
    """
    s = _strip_code_fence(content)
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"items": obj}
    except Exception:
        pass

    m = _JSON_BLOCK.search(s)
    if m:
        frag = m.group(1)
        obj = json.loads(frag)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"items": obj}

    raise ValueError("model_output_not_json")

def _data_url_from_b64(img_b64: str) -> str:
    return f"data:image/jpeg;base64,{img_b64}"

async def vision_analyze_base64(img_b64: str) -> Dict[str, Any]:
    """
    呼叫 OpenAI Vision，回傳 dict（必含 'items'）。
    遇到非 2xx 會把 response text 打 log 並拋 RuntimeError。
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
        logger.error("OpenAI bad response %s: %s", r.status_code, r.text)
        raise RuntimeError(f"OpenAI returned {r.status_code}")

    try:
        data = r.json()
        # Chat Completions：message.content 是純文字（偶爾會含 ```json 區塊）
        content = data["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("Unexpected OpenAI schema: %s", r.text[:500])
        raise RuntimeError("OpenAI response parse error")

    try:
        parsed = _parse_model_json(content)
    except Exception:
        logger.error("OpenAI content is not valid JSON: %s", content[:500])
        raise RuntimeError("OpenAI content not JSON")

    if not isinstance(parsed, dict) or "items" not in parsed:
        logger.error("OpenAI JSON missing items: %s", parsed)
        raise RuntimeError("OpenAI JSON missing 'items'")

    # 最後保險：確保 items 是 list
    items = parsed.get("items")
    if not isinstance(items, list):
        logger.error("OpenAI 'items' is not a list: %r", type(items))
        raise RuntimeError("OpenAI 'items' not list")

    return parsed
