# backend/app/services/openai_client.py
from __future__ import annotations
import os
import json
import re
import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

PROMPT = """
你是一位食物辨識專家。請從圖片中辨識所有「可食用的食材與配料」，
忽略盤子、餐具、標籤文字、背景物件（例如木桌、菜單、LOGO、日文紙條）。

只回傳 JSON（不要任何說明），格式如下：
{
  "items": [
    { "name": "食材名（可中文）" }
  ]
}

規則：
- 盡量用常見中文名稱（例如：牛肉、雞肉、南瓜、胡蘿蔔、茄子、青椒、玉米筍、蓮藕、馬鈴薯、咖哩醬、雞蛋...）
- 如果不確定，仍可輸出你最有把握的名稱；若真的沒有，items 回傳 []。
"""

def _strip_code_fences(s: str) -> str:
    """移除```json ... ``` 或 ``` ... ``` 包裹"""
    s = re.sub(r"^```(?:json)?\s*", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s.strip())
    return s.strip()

def _extract_json(s: str) -> str:
    """從回覆文字中擷取第一個看似 JSON 的 {...} 片段"""
    s = _strip_code_fences(s)
    # 先嘗試整段
    try:
        json.loads(s)
        return s
    except Exception:
        pass
    # 再用最外層大括號抓第一段 JSON
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        return m.group(0)
    return s  # 最後一搏，回原字串交給 json.loads 試試

async def vision_analyze_base64(img_b64: str) -> dict:
    """
    呼叫 OpenAI Vision，回傳 dict：
      {"items": [{"name": "雞肉"}, ...]}
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a meticulous food recognition expert. Reply in JSON only."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}",
                        },
                    },
                ],
            },
        ],
        # 控制成本/延遲
        "temperature": 0.2,
        "max_tokens": 400,
        "response_format": {"type": "text"},  # 我們會自己 parse 成 JSON
    }

    url = f"{OPENAI_BASE_URL}/chat/completions"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=HEADERS, json=payload)
        r.raise_for_status()
        data = r.json()

    content = data["choices"][0]["message"]["content"]
    text = _extract_json(content)
    try:
        obj = json.loads(text)
        # 正常化
        items = obj.get("items", [])
        if not isinstance(items, list):
            items = []
        # 只保留 name 欄位
        slim = [{"name": str(x.get("name", "")).strip()} for x in items if x and x.get("name")]
        return {"items": slim}
    except Exception:
        # 回傳空集合，讓後續邏輯執行
        return {"items": []}
