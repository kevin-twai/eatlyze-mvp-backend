# backend/app/services/openai_client.py
from __future__ import annotations

import os
import json
from typing import Any, Dict, List

from openai import OpenAI

# 主要/備援多模態模型
PRIMARY_MODEL = os.getenv("VISION_PRIMARY_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "gpt-4o")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---- 常見誤判校正 (Vision→Text 標籤) ----
# 目的：把模型常見的錯誤標籤，修正成我們 CSV/服務端能吃的 canonical
COMMON_CORRECTIONS: Dict[str, str] = {
    # 豆乾絲 vs 麵條
    "yi noodles": "shredded tofu",
    "yi noodle": "shredded tofu",
    "wheat noodles": "shredded tofu",
    "noodles": "shredded tofu",

    # 小黃瓜/胡瓜族
    "gourd": "cucumber",
    "taiwanese cucumber": "cucumber",
    "japanese cucumber": "cucumber",

    # 甜椒/辣椒族 — 視你的資料表而定
    "red peppercorns": "red chili",
    "sweet pepper": "red bell pepper",
}

# 常見「處理/切法」詞，拿掉以利對表
PREP_TOKENS = ("shredded", "sliced", "diced", "minced", "julienned")


def _apply_corrections(label: str) -> str:
    k = (label or "").strip().lower()
    return COMMON_CORRECTIONS.get(k, label)


def _strip_prep_words(s: str) -> str:
    """拿掉切法/處理前綴，讓對表更穩定。"""
    tokens = (s or "").strip().lower().split()
    tokens = [t for t in tokens if t not in PREP_TOKENS]
    out = " ".join(tokens)
    return out if out else s


def _safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        return None


SYSTEM_PROMPT = (
    "You are a food-ingredient detector for nutrition analysis. "
    "Return a compact JSON with an array 'items'. Each item must include: "
    "{name, canonical, weight_g, is_garnish}. "
    "Use common English ingredient names for 'canonical'. "
    "If something looks like Taiwanese '豆乾絲', label canonical as 'shredded tofu'. "
    "If cucumber variants appear, canonical should be 'cucumber'. "
    "Weights are rough estimates in grams. Keep is_garnish true for tiny condiments."
)

USER_PROMPT = (
    "Analyze this single photo and list main edible ingredients only. "
    "Do not include plate, plastic wrap, or background. "
    "Return JSON like: {\"items\":[{\"name\":\"...\",\"canonical\":\"...\",\"weight_g\":123,\"is_garnish\":false}, ...]}"
)


def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """
    1) 呼叫 OpenAI Vision 取得結構化 JSON
    2) 修正常見誤判 + 去除切法前綴
    3) 回傳 items (name/canonical/weight_g/is_garnish)
    """
    def _ask(model: str) -> str:
        # 用「multi-modal」格式：text + image(base64 data url）
        resp = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                },
            ],
        )
        return resp.choices[0].message.content or ""

    raw = _ask(PRIMARY_MODEL)
    if not raw and FALLBACK_MODEL:
        raw = _ask(FALLBACK_MODEL)

    # 嘗試把模型回覆中的 JSON 擷取出來
    data = _safe_json_loads(raw)
    if not data:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = _safe_json_loads(raw[start:end + 1]) or {"items": []}
        else:
            data = {"items": []}

    items: List[Dict[str, Any]] = []
    for it in (data.get("items") or []):
        name = str(it.get("name") or "").strip()
        canonical = str(it.get("canonical") or name)

        # 套用修正與切法清理
        name = _apply_corrections(name)
        canonical = _apply_corrections(canonical)

        name = _strip_prep_words(name)
        canonical = _strip_prep_words(canonical)

        weight_g = float(it.get("weight_g") or 0.0)
        is_garnish = bool(it.get("is_garnish") or False)

        items.append(
            {
                "name": name,
                "canonical": canonical,
                "weight_g": weight_g,
                "is_garnish": is_garnish,
            }
        )

    return {"items": items}
