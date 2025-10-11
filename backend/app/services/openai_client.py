import os, base64, json
from typing import Dict, Any
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    b64 = _b64(image_bytes)
    prompt = (
        "你是一位台灣在地的營養估算助手。請根據餐點圖片，列出每一項『食物名稱』與『估計重量(克)』，"
        "使用台灣常見菜名，例如：白飯、雞胸肉、青花菜、滷肉飯、滷味拼盤、便當炸雞塊等。"
        "輸出 JSON 陣列，格式：[{\"name\":\"食物\",\"grams\":數字,\"confidence\":0-1}]. "
        "僅輸出 JSON，不要附加解說文字。"
    )
    messages = [
        {"role": "system", "content": "你是專業的食物辨識與份量估算助手。"},
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
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
