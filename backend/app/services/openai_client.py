import os, base64, json
from typing import Dict, Any, List
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def _fake_items() -> List[Dict[str, Any]]:
    return [
        {"name": "咖哩雞肉", "grams": 150, "confidence": 0.78},
        {"name": "白飯", "grams": 180, "confidence": 0.75},
        {"name": "南瓜", "grams": 50, "confidence": 0.7},
        {"name": "玉米筍", "grams": 20, "confidence": 0.7},
        {"name": "蓮藕", "grams": 30, "confidence": 0.7},
        {"name": "溫泉蛋", "grams": 50, "confidence": 0.7},
    ]

def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    if os.getenv("DEMO_FAKE", "").strip() == "1":
        return {"items": _fake_items(), "debug": "DEMO_FAKE=1"}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"items": _fake_items(), "error": "Missing OPENAI_API_KEY (demo items used)"}

    client = OpenAI(api_key=api_key)
    b64 = _b64(image_bytes)

    system = "你是台灣在地的營養估算助手，請只輸出 JSON，不要任何說明。"
    user_text = (
        "根據這張餐點照片，列出所有主要食材與推測重量(克)。"
        "請用台灣常見菜名；若難以辨識請輸出最可能的名稱。"
        "請嚴格輸出如下 JSON：{\"items\":[{\"name\":\"食物\",\"grams\":數字,\"confidence\":0~1}]}"
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]},
            ],
            temperature=0.2,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        items = data.get("items", [])
        cleaned: List[Dict[str, Any]] = []
        for it in items:
            name = str(it.get("name", "")).strip()
            try:
                grams = float(it.get("grams", 0))
            except Exception:
                grams = 0.0
            conf = float(it.get("confidence", 0.6))
            if name and grams >= 0:
                cleaned.append({"name": name, "grams": grams, "confidence": conf})
        if not cleaned:
            return {"items": _fake_items(), "error": "LLM returned empty; fallback to demo items"}
        return {"items": cleaned}
    except Exception as e:
        return {"items": _fake_items(), "error": f"OpenAI error: {e.__class__.__name__}: {e}"}
