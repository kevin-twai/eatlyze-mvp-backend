# backend/app/services/openai_client.py
from __future__ import annotations

import os
import re
import json
import asyncio
import httpx
from typing import List, Dict, Any

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

SYSTEM_PROMPT = (
    "你是營養辨識助手。請分析輸入的食物照片，"
    "輸出**純 JSON 陣列**，每個元素包含："
    "{\"name\": <原始名稱或辨識名>, "
    "\"canonical\": <可用於查表的標準名(英文或中文皆可)>, "
    "\"weight_g\": <重量(公克，數字)>, "
    "\"is_garnish\": <是否僅裝飾用 布林> }。"
    "不要輸出多餘文字。"
)

def _payload_for_b64(image_b64: str) -> Dict[str, Any]:
    # 使用 data URL，避免外部連結失效
    data_url = f"data:image/jpeg;base64,{image_b64}"
    return {
        "model": MODEL,
        "temperature": 0.2,
        "max_tokens": 700,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "input_text", "text": "請辨識這張餐點照片，並估重（g）。只回 JSON 陣列。"},
                {"type": "input_image", "image_url": {"url": data_url}},
            ]},
        ],
    }

_JSON_BLOCK = re.compile(r"\[[\s\S]*\]")

def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    """
    嘗試從模型回覆中抽出 JSON 陣列；若本身就是陣列字串亦可解析。
    """
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass

    m = _JSON_BLOCK.search(text or "")
    if m:
        return json.loads(m.group(0))

    raise ValueError("model_output_not_json_array")

async def vision_analyze_base64(image_b64: str, retries: int = 2) -> List[Dict[str, Any]]:
    """
    呼叫 OpenAI Chat Completions（Vision），將輸出解析為 list[dict]。
    對 5xx/507 進行退避重試；仍失敗拋 RuntimeError("openai_http_<status>")。
    """
    payload = _payload_for_b64(image_b64)

    async with httpx.AsyncClient(timeout=45) as client:
        for attempt in range(retries + 1):
            try:
                r = await client.post(OPENAI_URL, headers=HEADERS, json=payload)
                r.raise_for_status()
                data = r.json()
                # Chat Completions: 取 message.content（多段時串起來）
                message = data["choices"][0]["message"]
                content = message.get("content") or ""
                if isinstance(content, list):
                    # 少數驅動會把片段分段回來
                    content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                items = _extract_json_array(content)
                return items
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code >= 500 and attempt < retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                raise RuntimeError(f"openai_http_{code}") from e
            except Exception as e:
                # 其它錯誤（例如暫時性網路錯）也嘗試重試一次
                if attempt < retries:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                raise RuntimeError(f"openai_unknown:{e}") from e
