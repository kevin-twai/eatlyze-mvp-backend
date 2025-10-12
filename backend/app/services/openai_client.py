import os, base64, json
from typing import Dict, Any, List
from openai import OpenAI

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

def _fake_items() -> List[Dict[str, Any]]:
    # Demo/備援資料，避免展示時出現空白
    return [
        {"name": "咖哩雞腿", "grams": 350, "confidence": 0.78},
        {"name": "白飯", "grams": 180, "confidence": 0.75},
        {"name": "南瓜片", "grams": 40, "confidence": 0.7},
    ]

def analyze_food_image(image_bytes: bytes) -> Dict[str, Any]:
    # 允許用環境變數強制走假資料：DEMO_FAKE=1
    if os.getenv("DEMO_FAKE", "").strip() == "1":
        return {"items": _fake_items(), "debug": "DEMO_FAKE=1"}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # 沒 key 也回 demo，避免整條 UX 中斷
        return {"items": _fake_items(), "error": "Missing OPENAI_API_KEY (returned demo items)"}

    client = OpenAI(api_key=api_key)
    b64 = _b64(image_bytes)

    # 要求嚴格 JSON 輸出
    system = "你是台灣在地的營養估算助手，請只輸出 JSON，不要任何說明。"
    user_text = (
        "根據這張餐點照片，列出每一項『食物名稱』與『估計重量(克)』。"
        "請用台灣常見菜名。輸出格式如下（只要 JSON）：\n"
        "{\"items\":[{\"name\":\"食物\",\"grams\":數字,\"confidence\":0~1}]}"
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}" }},
                ]},
            ],
            temperature=0.2,
            max_tokens=700,
            response_format={"type": "json_object"},
        )

        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)

        # 支援 {items:[...]} 或直接是陣列
        items = data.get("items", data if isinstance(data, list) else [])
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

        # 若模型回空，提供友善備援
        if not cleaned:
            return {"items": _fake_items(), "error": "LLM returned empty; fallback to demo items"}

        return {"items": cleaned}

    except Exception as e:
        # 任意錯誤也給 demo，避免前端完全空白
        return {"items": _fake_items(), "error": f"OpenAI error: {e.__class__.__name__}: {e}"}
