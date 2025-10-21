# backend/app/services/openai_client.py
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

import httpx

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com")
PRIMARY_MODEL = os.getenv("VISION_PRIMARY_MODEL", "gpt-4o-mini")
FALLBACK_MODEL = os.getenv("VISION_FALLBACK_MODEL", "gpt-4o")

TIMEOUT = 60
RETRIES = 3


_PROMPT_STRICT = """你是一位能辨識台灣/中式/日式家常菜餚食材的專業助理。請根據照片裡的食材，輸出 JSON 物件：
{
  "items":[
    {
      "name": "<中文或英文食材名>",
      "canonical": "<英文標準名（用小寫且單數，例：cucumber, tofu, dried tofu, tofu strips, carrot, soy sauce, bonito flakes, century egg, silken tofu, firm tofu, rice, noodles, fish, salmon, chicken breast, garlic, ginger…）>",
      "weight_g": <大約重量(克，數字)>,
      "is_garnish": <true|false>  // 裝飾/配菜請用 true
    }
  ]
}

務必只回傳 JSON，不要任何多餘文字。

注意：
- 若看到青綠色段狀、表皮有小顆粒、切滾刀或段切者，優先推定為「cucumber（小黃瓜）」而不是 bell pepper。
- 若看到淺米色細長條、像麵條但表面較乾、通常與紅蘿蔔絲拌在一起，優先推定為「tofu strips / dried tofu（豆干絲/乾豆腐）」而不是任何義大利麵。
- 豆腐類：滑嫩白色多孔者 silken tofu（嫩豆腐），較結實者 firm tofu（板豆腐）。
- 日式冷奴常見：silken tofu + soy sauce (或 sweet soy sauce/醬油膏) + bonito flakes（柴魚片）。
- 皮蛋請標示為 century egg（canonical 用小寫：century egg）。
- 麵條若非明顯義大利麵，使用 noodles，若真的是義大利麵再用 pasta/spaghetti。

請估計合理重量（以 10~300g 區間為主；醬料/柴魚片 3~30g；配菜 5~30g）。"""

_PROMPT_SOFT = """請再檢查一次並輸出相同 JSON 結構。若前一次把小黃瓜辨成青椒，或把豆干絲辨成義大利麵，請修正為：
- cucumber
- tofu strips 或 dried tofu
維持只回傳 JSON，無任何其它文字。"""


def _build_message(image_b64: str, prompt: str) -> Dict[str, Any]:
    # Chat Completions multimodal 正確結構：
    # [{"type":"text","text":...},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ],
    }


async def _chat_once(model: str, messages: List[Dict[str, Any]], max_tokens: int = 400) -> str:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(base_url=OPENAI_BASE, timeout=TIMEOUT) as client:
        resp = await client.post("/v1/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _safe_parse_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        # 嘗試修復常見問題：前後有 code fence、內容多一層包裝
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`")
            # 可能出現 "json\n{...}"
            if "\n" in t:
                t = t.split("\n", 1)[1]
        try:
            return json.loads(t)
        except Exception:
            return {"items": []}


async def vision_analyze_base64(image_b64: str) -> Dict[str, Any]:
    """
    以 Vision 解析出食材清單，回傳 {"items":[...]}
    - 先用嚴格提示；失敗則改寬鬆提示再試。
    - 兩個 model：PRIMARY -> FALLBACK
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")

    async def _try(prompt: str, model: str) -> Dict[str, Any]:
        messages = [_build_message(image_b64, prompt)]
        for i in range(RETRIES):
            try:
                text = await _chat_once(model, messages, max_tokens=600)
                data = _safe_parse_json(text)
                if "items" in data and isinstance(data["items"], list):
                    return data
            except httpx.HTTPStatusError as e:
                # 429/5xx 指數退避
                if e.response.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** i)
                else:
                    raise
            except Exception:
                time.sleep(1 + i)
        raise RuntimeError(f"OpenAI API failed after retries (model={model})")

    # pass 1：嚴格
    try:
        return await _try(_PROMPT_STRICT, PRIMARY_MODEL)
    except Exception:
        pass

    # pass 2：嚴格 + fallback model
    try:
        return await _try(_PROMPT_STRICT, FALLBACK_MODEL)
    except Exception:
        pass

    # pass 3：寬鬆
    try:
        return await _try(_PROMPT_SOFT, PRIMARY_MODEL)
    except Exception:
        pass

    # pass 4：寬鬆 + fallback
    return await _try(_PROMPT_SOFT, FALLBACK_MODEL)
