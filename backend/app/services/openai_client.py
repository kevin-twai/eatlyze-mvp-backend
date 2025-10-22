# backend/app/services/openai_client.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Tuple

from openai import OpenAI

# 你可以改用環境變數切換模型
PRIMARY_MODEL = os.getenv("VISION_PRIMARY_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "gpt-4o")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = (
    "You are a nutrition photo analyzer. "
    "Return ONLY a JSON object with key 'items'. "
    "Each item must be an object with keys: "
    "name (string), canonical (string), weight_g (number), is_garnish (boolean). "
    "No explanations."
)

ALLOWED_KEYS = {"name", "canonical", "weight_g", "is_garnish"}

JSON_BLOCK = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

def _extract_json(text: str) -> Dict[str, Any] | None:
    """從任意文字中盡力抽出 JSON 物件（抓第一個大括號區塊再 parse）"""
    if not text:
        return None
    # 先試直接 parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # 抓第一個 { ... } 區塊
    m = JSON_BLOCK.search(text)
    if not m:
        return None
    snippet = m.group(0)
    try:
        obj = json.loads(snippet)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None

def _sanitize_items(raw_items: Any) -> List[Dict[str, Any]]:
    """只保留允許欄位，補上預設值，過濾掉壞 item"""
    out: List[Dict[str, Any]] = []
    if not isinstance(raw_items, list):
        return out
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        clean = {
            "name": str(it.get("name") or "").strip(),
            "canonical": str(it.get("canonical") or "").strip(),
            "weight_g": float(it.get("weight_g") or 0.0),
            "is_garnish": bool(it.get("is_garnish") or False),
        }
        # 允許 name/canonical 其一為空，但兩個都空就跳過
        if not clean["name"] and not clean["canonical"]:
            continue
        out.append(clean)
    return out

def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """回傳 dict: {items: [...]} 或 {items: [], reason: "..."}"""
    if not image_b64:
        return {"items": [], "reason": "no_image"}

    def _call(model: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this meal photo and respond with JSON only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                },
            ],
        )
        return resp.choices[0].message.content or ""

    # 主模型
    text = ""
    try:
        text = _call(PRIMARY_MODEL)
    except Exception as e:
        # 備援模型
        try:
            text = _call(FALLBACK_MODEL)
        except Exception as e2:
            return {"items": [], "reason": f"vision_error: {e2}"}

    data = _extract_json(text)
    if not data:
        return {"items": [], "reason": "parse_fail", "raw": text[:4000]}

    raw_items = data.get("items")
    items = _sanitize_items(raw_items)
    return {"items": items}
