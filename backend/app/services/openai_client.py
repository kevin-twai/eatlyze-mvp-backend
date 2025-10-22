# backend/app/services/openai_client.py
from __future__ import annotations

import os
import json
import re
import asyncio
from typing import Any, Dict, Optional

import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
PRIMARY_MODEL = os.getenv("OPENAI_VISION_MODEL_PRIMARY", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("OPENAI_VISION_MODEL_FALLBACK", "gpt-4o")

_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

# 允許的再試狀態碼
_RETRY_STATUSES = {408, 409, 429, 500, 502, 503, 504}

PROMPT = (
    "You are a nutrition photo analyzer. Identify distinct food items you see, with Chinese names when possible. "
    "Return ONLY a JSON object with an 'items' array. Each item: "
    "{name: <中文或常見名>, canonical: <英文標準名>, weight_g: <估重 g 整數>, is_garnish: <true|false>}. "
    "Keep weights realistic. No markdown code fences."
)

def _strip_code_fences(s: str) -> str:
    if not s:
        return s
    s = s.strip()
    # ```json ... ``` 或 ``` ...
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s).strip()
        s = re.sub(r"\s*```$", "", s).strip()
    return s

def _force_items_dict(s: str) -> Dict[str, Any]:
    """
    嘗試把模型輸出解析成 dict，至少包含 {"items": [...]}
    """
    if not s:
        return {"items": []}
    text = _strip_code_fences(s)
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
            return data
        if isinstance(data, list):
            return {"items": data}
        # 不是 dict/list，回空
        return {"items": []}
    except Exception:
        # 嘗試抓出最像 JSON 的片段
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                data = json.loads(m.group(0))
                if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                    return data
            except Exception:
                pass
        return {"items": []}

async def _chat_json(image_b64: str, *, model: str, temp: float = 0.25, max_tokens: int = 600, retries: int = 3) -> Dict[str, Any]:
    """
    呼叫 Chat Completions 取得 JSON 結果（含重試與解析）
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing")

    payload = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this food photo."},
                    {
                        "type": "image_url",
                        "image_url": {
                            # 正確的資料 URL 格式
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        },
                    },
                ],
            },
        ],
    }

    backoff = 3
    last_err = None

    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(1, retries + 1):
            try:
                r = await client.post(f"{OPENAI_BASE}/chat/completions", headers=_HEADERS, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    content = data["choices"][0]["message"]["content"]
                    return _force_items_dict(content)
                # 非 200
                if r.status_code in _RETRY_STATUSES:
                    print(f"[openai] transient {r.status_code}, retry {attempt}/{retries} in {backoff}s…")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                # 其他直接報錯（但回傳錯誤內容方便除錯）
                try:
                    print(f"[openai] HTTP error ({model}): {r.status_code} {r.text[:300]}")
                except Exception:
                    print(f"[openai] HTTP error ({model}): {r.status_code}")
                r.raise_for_status()
            except Exception as e:
                last_err = e
                if attempt < retries:
                    print(f"[openai] exception {e}, retry {attempt}/{retries} in {backoff}s…")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    break

    raise RuntimeError(f"OpenAI API failed after retries (model={model})") from last_err

async def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """
    先用 primary，再 fallback。統一回傳 dict 形式，至少含 items 陣列。
    """
    try:
        return await _chat_json(image_b64, model=PRIMARY_MODEL, temp=0.25, max_tokens=550, retries=3)
    except Exception as e1:
        print(f"[vision] primary {PRIMARY_MODEL} failed: {e1}, fallback to {FALLBACK_MODEL}")
        try:
            return await _chat_json(image_b64, model=FALLBACK_MODEL, temp=0.3, max_tokens=600, retries=3)
        except Exception as e2:
            print(f"[vision] fallback {FALLBACK_MODEL} failed too: {e2}")
            # 最終失敗：回傳空 items，讓上層不會 502
            return {"items": [], "error": f"vision_failed: {str(e2)}"}
