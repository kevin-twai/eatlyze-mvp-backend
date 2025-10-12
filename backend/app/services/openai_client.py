import os
from openai import AsyncOpenAI

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

VISION_PROMPT = (
    "你是一個專業的營養分析 AI。\n"
    "請分析這張照片中的「可食用食材」，並忽略任何器皿、竹簾、托盤、餐具、標籤紙、裝飾葉與背景。\n\n"
    "輸出格式：必須是合法 JSON（不得有註解或額外文字）。\n\n"
    "若有裝飾用食材（例如蔥花、海苔、山葵、香菜等），請標記 \"is_garnish\": true 並給 weight_g 約 3～5 克。\n"
    "若無法估出重量，請設為 null（不要省略欄位）。\n\n"
    "---\n"
    "輸出範例：\n"
    "{\n"
    "  \"items\": [\n"
    "    {\"name\": \"牛肉\", \"canonical\": \"牛肉\", \"weight_g\": 150, \"is_garnish\": false},\n"
    "    {\"name\": \"洋蔥\", \"canonical\": \"洋蔥\", \"weight_g\": 40, \"is_garnish\": false},\n"
    "    {\"name\": \"胡蘿蔔\", \"canonical\": \"胡蘿蔔\", \"weight_g\": 25, \"is_garnish\": false},\n"
    "    {\"name\": \"青椒\", \"canonical\": \"青椒\", \"weight_g\": 20, \"is_garnish\": false},\n"
    "    {\"name\": \"蕎麥麵\", \"canonical\": \"蕎麥麵\", \"weight_g\": 200, \"is_garnish\": false},\n"
    "    {\"name\": \"海苔\", \"canonical\": \"海苔\", \"weight_g\": 3, \"is_garnish\": true},\n"
    "    {\"name\": \"蔥\", \"canonical\": \"蔥\", \"weight_g\": 4, \"is_garnish\": true},\n"
    "    {\"name\": \"芥末(山葵)\", \"canonical\": \"芥末(山葵)\", \"weight_g\": 3, \"is_garnish\": true}\n"
    "  ]\n"
    "}\n"
    "---\n"
    "規則：\n"
    "- 食材名稱請盡量用中文（若無法，保留日文/英文原文）\n"
    "- 若同一類食材出現多次，請合併為單一項並給總重量\n"
    "- 只分析可食部分，不含裝飾或容器\n"
    "- 必須回傳 JSON 格式\n"
)

async def vision_analyze_base64(base64_str: str) -> str:
    completion = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "請分析這張食物照片"},
        {"role": "user", "content": [
            {"type": "text", "text": "請列出主要食材與推測重量(克)。"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64," + base64_str,
                    "detail": "high"
                }
            }
        ]}
    ],
    max_tokens=800,
)
    return completion.choices[0].message.content
