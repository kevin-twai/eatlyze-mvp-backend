# backend/app/services/openai_client.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from openai import OpenAI

# 你可以改這兩個模型名稱，mini 作主、o 作備援
PRIMARY_MODEL = os.getenv("VISION_PRIMARY_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "gpt-4o")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = (
    "You are a nutrition assistant. You will receive a food photo. "
    "Extract all edible components you can see (ingredients). "
    "Respond STRICTLY in JSON with the shape: "
    '{"items":[{"name":"<zh or en>","canonical":"<english canonical>",'
    '"weight_g":<number or 0 if unknown>,"is_garnish":<true|false>}]}\n'
    "Rules:\n"
    "- name: use Chinese if UI text looks Chinese, otherwise English.\n"
    "- canonical: concise English name (e.g., 'cucumber','carrot','egg','soy sauce').\n"
    "- weight_g: estimate if possible; else 0.\n"
    "- is_garnish: true for decorative herbs/flakes/green onions, etc.\n"
    "- DO NOT include explanation text, ONLY the JSON."
)

USER_TEXT = (
    "Please list ingredients visible in the image and return ONLY the JSON as described."
)

# --------------------------------------------------------
# 工具函數
# --------------------------------------------------------

def _extract_json(text: str) -> Dict[str, Any]:
    """從模型回覆中抓 JSON；失敗時回空結構"""
    if not text:
        return {"items": []}
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {"items": []}
    return {"items": []}


def _call_vision_chat(model: str, image_b64: str) -> Dict[str, Any]:
    """用 Chat Completions 的 image_url data URL 呼叫 Vision"""
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_TEXT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            },
        ],
    )
    content = resp.choices[0].message.content or ""
    return _extract_json(content)


# --------------------------------------------------------
# 主函式
# --------------------------------------------------------

async def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """
    傳入 base64（不含 dataURL 前綴）→ 回傳 {"items":[...]}。
    會先用 PRIMARY_MODEL，失敗再切 FALLBACK_MODEL。
    """
    if image_b64.startswith("data:image"):
        try:
            image_b64 = image_b64.split(",", 1)[1]
        except Exception:
            pass

    # 嘗試主要模型
    try:
        parsed = _call_vision_chat(PRIMARY_MODEL, image_b64)
        if isinstance(parsed, dict) and "items" in parsed:
            return parsed
        return {"items": []}
    except Exception as e1:
        # 嘗試備援
        try:
            parsed = _call_vision_chat(FALLBACK_MODEL, image_b64)
            if isinstance(parsed, dict) and "items" in parsed:
                return parsed
            return {"items": []}
        except Exception as e2:
            raise RuntimeError(
                f"Vision analysis failed for both models ({PRIMARY_MODEL}: {e1}; {FALLBACK_MODEL}: {e2})"
            )
