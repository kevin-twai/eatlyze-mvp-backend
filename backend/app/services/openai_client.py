import os, base64, json
from typing import Dict, Any
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"items": [], "error": "Missing OPENAI_API_KEY"}
    client = OpenAI(api_key=api_key)
    b64 = _b64(image_bytes)
    messages = [
        {"role": "system", "content": "你是專業的食物辨識與份量估算助手。"},
        {"role": "user", "content": [
            {"type": "text", "text": "請依圖片輸出食物清單及估計重量（g），JSON 陣列 items。"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]},
    ]
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=600,
        response_format={"type": "json_object"}
    )
    try:
        content = resp.choices[0].message.content
        data = json.loads(content)
        items = data.get("items") or data
        clean = []
        for it in items:
            name = str(it.get("name", "")).strip()
            grams = float(it.get("grams", 0))
            conf = float(it.get("confidence", 0.6))
            if name:
                clean.append({"name": name, "grams": grams, "confidence": conf})
        return {"items": clean}
    except Exception as e:
        return {"items": [], "error": str(e)}
