
import os, json, httpx, re

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

async def vision_analyze_base64(image_b64: str):
    if not OPENAI_API_KEY:
        return []
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    sys_prompt = "你是營養助理。從餐點照片中列出主要食材及估計重量(g)，用 JSON 陣列回傳。"
    data_url = f"data:image/jpeg;base64,{image_b64}"
    body = {
        "model": OPENAI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role":"system","content": sys_prompt},
            {"role":"user","content": [
                {"type":"text","text":"請只回傳 JSON 陣列；每項提供 name、canonical、weight_g、is_garnish。"},
                {"type":"image_url","image_url":{"url": data_url}},
            ]}
        ]
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    text = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
            return parsed["items"]
    except Exception:
        pass
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return arr
        except Exception:
            pass
    return []
