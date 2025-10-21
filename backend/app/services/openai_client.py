# backend/app/services/openai_client.py
from __future__ import annotations

import json
import os
import re
import base64
import csv
from typing import List, Dict, Any

from openai import OpenAI
from aiohttp import ClientSession  # 若你不想帶 aiohttp，可移除；這裡保留以便未來做外部取檔


# -----------------------------
# 讀 CSV 取出 canonical 與常見別名（簡單作法）
# -----------------------------
FOODS_CSV_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "data", "foods_tw.csv"),
    os.path.join(os.getcwd(), "backend", "app", "data", "foods_tw.csv"),
    os.path.join(os.getcwd(), "app", "data", "foods_tw.csv"),
]


def _load_csv_vocab() -> List[str]:
    for p in FOODS_CSV_PATHS:
        p = os.path.normpath(p)
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                words = set()
                for r in reader:
                    cano = (r.get("canonical") or "").strip()
                    if cano:
                        words.add(cano.lower())
                # 補幾個常用 alias（你可再擴充或改從 nutrition_service_v2 載入）
                words.update(
                    {
                        "cucumber", "shredded tofu", "tamagoyaki", "soy sauce", "dashi",
                        "carrot", "onion", "garlic", "egg", "white rice",
                        "bell pepper", "green pepper", "red bell pepper",
                    }
                )
                return sorted(list(words))
    return []


VOCAB = _load_csv_vocab()

VISION_GUIDE = f"""
You are a food ingredient detector. Return STRICT JSON only.

Output shape:
{{
  "items":[
    {{"name":"(中文或英文)","canonical":"(MUST be from allowed list)","weight_g":(float),"is_garnish":(true|false)}},
    ...
  ]
}}

Rules (IMPORTANT):
1) Use ONLY the following allowed canonical list (case-insensitive, prefer lower-case): {", ".join(VOCAB) or "[]"}.
2) 'name' use Chinese if obvious (e.g., 小黃瓜、豆乾絲、玉子燒), otherwise English.
3) 'is_garnish' TRUE only for decorative, tiny amount (<5 g): parsley, cilantro, sesame sprinkle, scallion garnish, lemon zest etc.
   In cold dishes like cucumber salad, carrot shreds/garlic slices ARE ingredients, DO NOT mark as garnish.
4) If you see tamagoyaki/dashimaki tamago (Japanese omelette), you MAY return just one item with "canonical":"tamagoyaki",
   the backend will expand it to egg + dashi + soy sauce.
5) 'weight_g' is a rough per-portion estimate from the photo (±30% is acceptable).
6) Return pure JSON, no commentary.
"""


def _strip_b64_prefix(b64: str) -> str:
    return re.sub(r"^data:image/[^;]+;base64,", "", b64.strip(), flags=re.I)


def _build_vision_messages(image_b64: str) -> List[Dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": VISION_GUIDE.strip(),
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Identify ingredients from this photo and return JSON."},
                {"type": "input_image", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        },
    ]


def _clean_json(s: str) -> dict:
    # 容錯：把可能包裝 code block 的字去掉
    s = s.strip()
    s = re.sub(r"^```json\s*|\s*```$", "", s)
    return json.loads(s)


async def vision_analyze_base64(image_b64: str, model_primary="gpt-4o-mini", model_fallback="gpt-4o") -> dict:
    """
    回傳 {"items":[{name, canonical, weight_g, is_garnish}, ...]}
    """
    b64 = _strip_b64_prefix(image_b64)
    try:
        # 驗證 base64
        base64.b64decode(b64, validate=True)
    except Exception as e:
        raise RuntimeError(f"invalid base64 image: {e}")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages = _build_vision_messages(b64)

    async def _call(model: str) -> dict:
        res = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=messages,
        )
        txt = res.choices[0].message.content
        return _clean_json(txt)

    # primary
    try:
        return await _call(model_primary)
    except Exception:
        pass

    # fallback
    try:
        return await _call(model_fallback)
    except Exception as e:
        raise RuntimeError(f"OpenAI API failed after retries: {e}")
