# backend/app/services/openai_client.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from openai import OpenAI, OpenAIError

# === 可調參數 ===
PRIMARY_MODEL = os.getenv("VISION_PRIMARY_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_client: OpenAI | None = None


def _client_ok() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = (
    "You are a nutrition vision assistant. Look at the photo and extract a short "
    "list of food items with weights (in grams). Output STRICT JSON with this schema:\n"
    "{ \"items\": [ {\"name\": str, \"canonical\": str, \"weight_g\": number, \"is_garnish\": bool} ] }\n"
    "- name: human-readable label (English) you see/decide\n"
    "- canonical: lowercase english key usable to join nutrition table (e.g. 'silken tofu', 'cucumber')\n"
    "- weight_g: best estimate in grams for each item\n"
    "- is_garnish: True for tiny toppings (spring onion, parsley, etc.)\n"
    "If unsure, keep the list small. If it's miso soup, typical components can be "
    "[\"silken tofu\", \"miso paste\", \"spring onion\", \"wakame\", \"dashi\"] with reasonable weights."
)

# 常見品項 → 建議 canonical（避免模型產生奇怪大小寫/同義字）
_CANON_SUGGEST = {
    # soups
    "miso soup": "miso soup",
    "silken tofu": "silken tofu",
    "tofu": "silken tofu",
    "spring onion": "spring onion",
    "green onion": "spring onion",
    "scallion": "spring onion",
    "wakame": "wakame",
    "seaweed": "wakame",
    "dashi": "dashi",
    # salads / cold plates
    "cucumber": "cucumber",
    "carrot": "carrot",
    "shredded carrot": "carrot",
    "shredded tofu": "shredded tofu",
    "bean curd strips": "shredded tofu",
    "red pepper": "red pepper",
    "sweet pepper": "red pepper",
}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    for ch in (" ", "_"):
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _post_fixup(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把模型輸出的 canonical 做最小校正，並確保欄位完整可序列化。"""
    fixed: List[Dict[str, Any]] = []
    for it in items or []:
        name = str(it.get("name") or "").strip()
        canonical = str(it.get("canonical") or name).strip()
        weight = it.get("weight_g", 0)
        is_garnish = bool(it.get("is_garnish", False))

        nkey = _norm(canonical or name)
        canonical2 = _CANON_SUGGEST.get(nkey, nkey)  # 統一小寫 key

        try:
            weight = float(weight) if weight is not None else 0.0
        except Exception:
            weight = 0.0

        fixed.append(
            {
                "name": name or canonical2 or "item",
                "canonical": canonical2 or "item",
                "weight_g": round(weight, 1),
                "is_garnish": bool(is_garnish),
            }
        )
    return fixed


def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """
    以 base64 圖片做食材抽取。必定回傳可 JSON 化的 dict：
    { "items": [...], "model": "...", "error": None|str }
    """
    client = _client_ok()

    # 建立 Chat 請求（強制輸出 JSON 物件）
    def _call(model: str) -> Dict[str, Any]:
        resp = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Extract food items."},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image_b64}"},
                    ],
                },
            ],
            temperature=0.2,
        )
        txt = (resp.choices[0].message.content or "").strip()
        # 有些版本會把 json 包在 ```json 區塊
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:].strip()
        try:
            data = json.loads(txt)
        except Exception:
            # 如果不是 JSON，嘗試容錯
            data = {"items": []}
        # 強制結構與後處理
        items = _post_fixup(list(data.get("items") or []))
        return {"items": items, "model": model, "error": None}

    try:
        try:
            return _call(PRIMARY_MODEL)
        except OpenAIError:
            # 轉用備援模型
            return _call(FALLBACK_MODEL)
    except Exception as e:
        # 保證回傳可序列化
        return {"items": [], "model": PRIMARY_MODEL, "error": f"{type(e).__name__}: {e}"}
