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


SYSTEM_PROMPT = (
    "You are a nutrition vision assistant. Look at the photo and extract a SHORT list "
    "of food items with weights (in grams). Output STRICT JSON with this schema only:\n"
    '{ "items": [ {"name": string, "canonical": string, "weight_g": number, "is_garnish": boolean} ] }\n'
    "- name: human-readable label (English)\n"
    "- canonical: lowercase english key usable to join nutrition table (e.g. 'silken tofu', 'cucumber')\n"
    "- weight_g: best estimate in grams\n"
    "- is_garnish: True for tiny toppings (spring onion, parsley, bonito flakes, etc.)\n"
    "If unsure, keep the list small.\n"
    "⚠️ Do NOT confuse soy-based shredded tofu (豆干絲/豆乾絲; dried tofu strips; bean curd strips) with noodles. "
    "If strands look pale beige, slightly rough/fibrous, or appear in a cold side dish with carrot shreds, "
    "treat it as 'shredded tofu' instead of any kind of noodles.\n"
    "For miso soup, typical components may be ['silken tofu','miso paste','spring onion','wakame','dashi'] "
    "with reasonable weights."
)

# 常見品項 → 建議 canonical（收斂大小寫/同義詞）
_CANON_SUGGEST: Dict[str, str] = {
    # soups / Japanese
    "miso soup": "miso soup",
    "miso": "miso paste",
    "miso paste": "miso paste",
    "tofu": "silken tofu",
    "silken tofu": "silken tofu",
    "firm tofu": "firm tofu",
    "spring onion": "spring onion",
    "green onion": "spring onion",
    "scallion": "spring onion",
    "wakame": "wakame",
    "seaweed": "wakame",
    "dashi": "dashi",

    # salads / cold plates
    "cucumber": "cucumber",
    "cucumbers": "cucumber",
    "carrot": "carrot",
    "shredded carrot": "carrot",

    # shredded tofu（豆干絲/豆乾絲）相關別名
    "shredded tofu": "shredded tofu",
    "bean curd strips": "shredded tofu",
    "bean curd threads": "shredded tofu",
    "dried tofu strips": "shredded tofu",
    "tofu strips": "shredded tofu",
    "tofu noodles": "shredded tofu",   # 常被誤標
    "soy noodles": "shredded tofu",

    # peppers
    "red pepper": "red pepper",
    "sweet pepper": "red pepper",

    # seafood quick map
    "shrimp": "shrimp",
    "prawn": "shrimp",
    "fish fillet": "fish fillet",

    # 常見麵名詞（若確定是麵才保留；後處理還會再判斷）
    "noodles": "noodles",
    "wheat noodles": "noodles",
    "egg noodles": "noodles",
    "yi noodles": "noodles",
}


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    return " ".join(s.replace("_", " ").split())


def _looks_like_soup(all_canon: List[str]) -> bool:
    """是否看起來像湯品（用來避免把湯麵誤改成豆干絲）。"""
    soup_keys = {"soup", "miso", "miso soup", "miso paste", "broth", "dashi"}
    return any(key in c for c in all_canon for key in soup_keys)


def _post_fixup(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    將模型輸出做最小校正，確保欄位完整可序列化。
    並加入『麵條→豆干絲』的保守矯正（非湯品時）。
    """
    # 先做第一輪正規化，方便整體判斷
    prelim: List[Dict[str, Any]] = []
    for it in items or []:
        name = str(it.get("name") or "").strip()
        canon_raw = str(it.get("canonical") or name).strip()
        nkey = _norm(canon_raw or name)
        canonical = _CANON_SUGGEST.get(nkey, nkey) or "item"

        weight = it.get("weight_g", 0)
        try:
            weight = float(weight) if weight is not None else 0.0
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

    # 第二步：若出現「noodles」但不是湯品，傾向矯正為 shredded tofu（豆干絲）
    canon_list = [p["canonical"] for p in prelim]
    soup_like = _looks_like_soup(canon_list)

    fixed: List[Dict[str, Any]] = []
    for p in prelim:
        canonical = p["canonical"]
        name = p["name"]

        if (("noodle" in canonical) or canonical == "noodles") and not soup_like:
            canonical = "shredded tofu"
            name = "shredded tofu"

        fixed.append(
            {
                "name": name,
                "canonical": canonical,
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
                    {"type": "text", "text": "Extract food items as the schema."},
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
