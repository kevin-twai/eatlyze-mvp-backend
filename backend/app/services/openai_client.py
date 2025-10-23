# backend/app/services/openai_client.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import OpenAI, OpenAIError

# ===== 可調參數 =====
PRIMARY_MODEL = os.getenv("VISION_PRIMARY_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "gpt-4o")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

_client: OpenAI | None = None


def _client_ok() -> OpenAI:
    """Singleton OpenAI client with API key check."""
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _strip_data_url_prefix(b64: str) -> str:
    """去掉 data URL 前綴，保留純 base64。"""
    if not b64:
        return b64
    s = b64.strip()
    if "base64," in s:
        return s.split("base64,", 1)[-1].strip()
    if s.startswith("data:") and "," in s:
        return s.split(",", 1)[-1].strip()
    return s


# === 提示：以「整體菜餚 + 關鍵食材」為主，嚴格 JSON ===
SYSTEM_PROMPT = (
    "You are a professional food nutrition vision assistant.\n"
    "Look at the meal photo and identify the overall dish type and only its major components. "
    "Output STRICT JSON ONLY with this schema:\n"
    '{ "items": [ {"name": string, "canonical": string, "weight_g": number, "is_garnish": boolean} ] }\n'
    "- Keep the list short and realistic (2–6 items).\n"
    "- Use lowercase english for `canonical` that can join a nutrition table "
    "(e.g. 'fried noodles', 'noodles', 'fried egg', 'silken tofu', 'bean sprouts', 'carrot').\n"
    "- Estimate weights in grams.\n"
    "- Mark tiny toppings as is_garnish=true (spring onion, parsley, red pepper flakes, etc.).\n"
    "- Composite dishes should be recognized as a dish, not as many tiny fragments.\n"
    "Examples:\n"
    "• Taiwanese fried noodles with a fried egg and bean sprouts → "
    'items ≈ [{"canonical":"fried noodles"}, {"canonical":"fried egg"}, {"canonical":"bean sprouts"}, {"canonical":"carrot","is_garnish":true}]\n'
    "• miso soup with tofu, wakame and spring onion → "
    'items ≈ [{"canonical":"miso soup"}, {"canonical":"silken tofu"}, {"canonical":"wakame","is_garnish":true}, {"canonical":"spring onion","is_garnish":true}]\n"
    "⚠️ Do NOT confuse fried/stir-fried noodles with soy-based shredded tofu (豆干絲/bean curd strips). "
    "If you see oily noodles with egg/meat/sprouts/greens, classify as 'fried noodles' or 'noodles', not 'shredded tofu'.\n"
)

# === 同義詞收斂（canonical） ===
_CANON_SUGGEST: Dict[str, str] = {
    # noodles / dishes
    "noodle": "noodles",
    "noodles": "noodles",
    "wheat noodles": "noodles",
    "egg noodles": "noodles",
    "yi noodles": "noodles",
    "yimin": "noodles",
    "yimin noodles": "noodles",
    "ramen": "noodles",
    "udon": "noodles",
    "spaghetti": "noodles",
    "lo mein": "fried noodles",
    "chow mein": "fried noodles",
    "fried noodles": "fried noodles",
    "stir-fried noodles": "fried noodles",
    "taiwanese fried noodles": "fried noodles",

    # eggs
    "egg": "egg",
    "fried egg": "fried egg",
    "sunny side up": "fried egg",
    "omelette": "omelette",

    # vegetables
    "bean sprouts": "bean sprouts",
    "soybean sprouts": "bean sprouts",
    "mung bean sprouts": "bean sprouts",
    "carrot": "carrot",
    "shredded carrot": "carrot",
    "cucumber": "cucumber",
    "red pepper": "red pepper",
    "sweet pepper": "red pepper",
    "spring onion": "spring onion",
    "green onion": "spring onion",
    "scallion": "spring onion",
    "vegetables": "vegetables",

    # tofu / soy
    "tofu": "silken tofu",
    "silken tofu": "silken tofu",
    "firm tofu": "firm tofu",
    "shredded tofu": "shredded tofu",
    "bean curd strips": "shredded tofu",
    "bean curd threads": "shredded tofu",
    "dried tofu strips": "shredded tofu",
    "tofu strips": "shredded tofu",

    # soups / broth
    "miso soup": "miso soup",
    "miso": "miso paste",
    "miso paste": "miso paste",
    "broth": "broth",
    "dashi": "dashi",
    "wakame": "wakame",

    # seafood / meats (常見)
    "shrimp": "shrimp",
    "prawn": "shrimp",
    "fish fillet": "fish fillet",
    "ground pork": "ground pork",
    "minced pork": "ground pork",
    "pork mince": "ground pork",
}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    return " ".join(s.replace("_", " ").split())


def _looks_like_soup(canon_list: List[str]) -> bool:
    soup_keys = {"miso soup", "broth", "dashi", "soup"}
    return any(c in soup_keys for c in canon_list)


def _is_cold_shredded_tofu_pattern(canon_list: List[str], total_weight: float) -> bool:
    """
    判斷是否像「冷盤豆干絲」：
    - 有 shredded tofu/bean curd strips 同時有 carrot/cucumber/red pepper
    - 沒有蛋/肉/豆芽/炒麵等熱炒特徵
    - 總重量偏小（例如 < 250g）
    """
    s = set(canon_list)
    has_tofu_shredded = "shredded tofu" in s
    has_cold_garnish = bool(
        {"carrot", "cucumber", "red pepper"} & s
    )
    hot_cues = {"fried egg", "egg", "ground pork", "bean sprouts", "fried noodles", "noodles"}
    has_hot_cues = bool(s & hot_cues)
    return has_tofu_shredded and has_cold_garnish and not has_hot_cues and (total_weight < 250)


def _post_fixup(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """收斂同義詞、估重、移除明顯誤判；偏向保留麵而非豆干絲。"""
    prelim: List[Dict[str, Any]] = []
    for it in items or []:
        name = str(it.get("name") or "").strip()
        canon_raw = str(it.get("canonical") or name).strip()
        canon_key = _norm(canon_raw or name)
        canonical = _CANON_SUGGEST.get(canon_key, canon_key) or "item"

        w = it.get("weight_g", 0)
        try:
            weight = float(w) if w is not None else 0.0
        except Exception:
            weight = 0.0

        prelim.append(
            {
                "name": name or canonical,
                "canonical": canonical,
                "weight_g": weight,
                "is_garnish": bool(it.get("is_garnish", False)),
            }
        )

    if not prelim:
        return []

    canon_list = [p["canonical"] for p in prelim]
    total_weight = sum(float(p.get("weight_g") or 0.0) for p in prelim)
    soup_like = _looks_like_soup(canon_list)

    # 若同時存在 noodles 與 shredded tofu，預設保留麵、移除誤判的 shredded tofu
    has_noodles = any(c in {"noodles", "fried noodles"} for c in canon_list)
    if has_noodles and "shredded tofu" in canon_list and not soup_like:
        prelim = [p for p in prelim if p["canonical"] != "shredded tofu"]

    # 只有在明顯像「冷盤豆干絲」時才保留 shredded tofu
    if "shredded tofu" in [p["canonical"] for p in prelim] and not soup_like:
        if not _is_cold_shredded_tofu_pattern([p["canonical"] for p in prelim], total_weight):
            # 不是冷盤 → 偏向移除豆干絲，避免把炒麵看成豆干絲
            prelim = [p for p in prelim if p["canonical"] != "shredded tofu"]

    # 整理輸出
    fixed: List[Dict[str, Any]] = []
    for p in prelim:
        fixed.append(
            {
                "name": p["name"],
                "canonical": p["canonical"],
                "weight_g": round(float(p["weight_g"] or 0.0), 1),
                "is_garnish": bool(p["is_garnish"]),
            }
        )
    return fixed


def _call_model(client: OpenAI, model: str, image_b64: str) -> Dict[str, Any]:
    """呼叫模型（強制 JSON 輸出），回傳 {items, model, error}。"""
    pure_b64 = _strip_data_url_prefix(image_b64)

    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},  # 強制 JSON 物件輸出
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Identify the dish and list only major components with grams."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{pure_b64}"},
                    },
                ],
            },
        ],
        temperature=0.2,
    )

    txt = (resp.choices[0].message.content or "").strip()
    # 有些情況會包在 ```json ... ```
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:].strip()

    try:
        data = json.loads(txt)
    except Exception:
        data = {"items": []}

    items = _post_fixup(list(data.get("items") or []))
    return {"items": items, "model": model, "error": None}


def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """
    以 base64 圖片做食材抽取。固定回傳：
    { "items": list, "model": str, "error": None|str }
    """
    client = _client_ok()
    try:
        try:
            return _call_model(client, PRIMARY_MODEL, image_b64)
        except OpenAIError:
            # 轉用備援模型
            return _call_model(client, FALLBACK_MODEL, image_b64)
    except Exception as e:
        return {"items": [], "model": PRIMARY_MODEL, "error": f"{type(e).__name__}: {e}"}
