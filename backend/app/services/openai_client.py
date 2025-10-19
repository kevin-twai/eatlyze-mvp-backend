# backend/app/services/openai_client.py
from __future__ import annotations
import os, json, re, base64, logging, httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_SYS = (
    "你是餐點影像辨識與營養標記助手。"
    "必須輸出 JSON 物件，格式："
    '{"items":[{"name":"中文食材名","canonical":"英文或中文通用名","weight_g":數字,"is_garnish":布林}, ...]}。'
    "請務必：1) 至少輸出一項主要食材（肉/飯/麵/主食/醬）; 2) 盡量推測克數(整數或小數); "
    "3) 醬料與點綴(is_garnish=true); 4) 不可輸出多餘字段; 5) 絕對不要包覆程式碼圍欄。"
)

_USER_TEMPLATE = (
    "這是一張餐點照片（base64）：data:image/jpeg;base64,{b64}\n"
    "請只輸出 JSON 物件，鍵為 items。至少輸出 1 個主要食材（例：雞肉、白飯、麵、咖哩醬…）。"
)

# 簡單移除可能的圍欄
def _strip_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r'^```(json)?', '', s, flags=re.I).strip()
    s = re.sub(r'```$', '', s).strip()
    return s

async def _openai_chat_json(b64: str, temp: float = 0.2, max_tokens: int = 450) -> dict:
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "temperature": temp,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYS},
            {"role": "user", "content": _USER_TEMPLATE.format(b64=b64)},
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    content = data["choices"][0]["message"]["content"]
    content = _strip_fences(content)
    try:
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
        return parsed
    except Exception as e:
        logger.error("OpenAI content not JSON: %r", content[:400])
        raise RuntimeError("OpenAI content not JSON") from e

async def vision_analyze_base64(image_b64: str) -> dict:
    """
    回傳 dict，至少包含 {"items":[...]}。
    策略：先保守（低溫、短 tokens），若 items 為空 → 進一步重試（高溫、長 tokens）。
    """
    # 第一次：保守
    try:
        parsed = await _openai_chat_json(image_b64, temp=0.2, max_tokens=450)
        items = parsed.get("items") or []
        logger.info("[vision] pass1 items=%d", len(items))
        if isinstance(items, list) and items:
            return {"items": items}
    except Exception as e:
        logger.exception("vision pass1 failed")

    # 第二次：積極（稍高溫 + 更明確要求）
    global _SYS
    strong_sys = _SYS + " 若你不確定，也要用常見餐點類別合理猜測，務必至少輸出 1 項主要食材。"
    old_sys = _SYS
    _SYS = strong_sys
    try:
        parsed = await _openai_chat_json(image_b64, temp=0.4, max_tokens=600)
        items = parsed.get("items") or []
        logger.info("[vision] pass2 items=%d", len(items))
        return {"items": items}
    finally:
        _SYS = old_sys
