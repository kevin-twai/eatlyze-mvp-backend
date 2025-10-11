
# Eatlyze Taiwan — MVP Backend (FastAPI)

一個可直接部署的後端：支援 **圖片上傳 → GPT Vision 分析 → 在地營養資料比對 → Notion 寫入**。

## 快速開始

```bash
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # 填入你的 API key 與 Notion Database ID
uvicorn main:app --reload
```

啟動後：`http://localhost:8000/docs` 進入 Swagger 測試。

## 主要端點

- `POST /upload`：上傳圖片（jpg/png/webp）
- `POST /analyze/image`：直接上傳圖片並得到「辨識 + 營養總結」
- `POST /nutrition/summary`：傳入 `items: [{name, grams}]` 回傳營養加總
- `POST /notion/log`：把當次結果寫入 Notion 資料庫

## 設定環境變數

請在 `.env` 中填入：

- `OPENAI_API_KEY`：OpenAI API key
- `OPENAI_MODEL`：預設 `gpt-4o-mini`（支援圖片理解）
- `NOTION_API_KEY`、`NOTION_DATABASE_ID`：Notion 整合

## 部署 Render

新增 `Web Service` 指向此 backend 目錄：

- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Python version: 3.11+

## 資料庫

`backend/data/foods_tw.csv` 為台灣常見食物基礎表，可自行擴充。
