# backend/app/services/openai_client.py
from __future__ import annotations

import os, httpx, json, asyncio

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
PRIMARY_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK", "gpt-4o")

PROMPT = """
You are a food vision assistant. Return a strict JSON with an array `items`.
Each `item` has: name (en), canonical (en), weight_g (float), is_garnish (bool).

Rules:
- Prefer concrete ingredient names over broad categories (e.g., "shredded tofu" not just "tofu").
- Synonyms you may use:
  * shredded tofu = tofu strips = tofu threads
  * cucumber = small cucumber
  * bell pepper = sweet pepper
- Only set is_garnish=true when the portion is tiny (sprinkle-level).
  If a vegetable portion is visible in spoonfuls (>= ~5 g), set is_garnish=false.
- Guess reasonable weights in grams.

Return JSON only.
"""

async def _openai_chat_json(image_b64: str, model: str, temp=0.2, max_tokens=600):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "Analyze this meal and list items."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]}
        ],
        "temperature": temp,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{OPENAI_BASE}/chat/completions", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception:
            return {"items": []}

async def vision_analyze_base64(image_b64: str):
    # 先主模型
    try:
        return await _openai_chat_json(image_b64, PRIMARY_MODEL, temp=0.2, max_tokens=700)
    except Exception:
        pass
    # 退備援
    return await _openai_chat_json(image_b64, FALLBACK_MODEL, temp=0.3, max_tokens=700)
