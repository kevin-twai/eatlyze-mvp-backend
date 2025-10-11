
# Eatlyze Taiwan — MVP Backend (FastAPI)

Render 友善版本：**使用 uvicorn (無 [standard])**，建置時會先升級 pip 並用 --no-cache-dir 安裝。

## 快速開始 (本機)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 填入 API Key 與 Notion DB ID
uvicorn main:app --reload
```
Swagger: `http://localhost:8000/docs`

## 主要端點
- `POST /upload`
- `POST /analyze/image`
- `POST /nutrition/summary`
- `POST /notion/log`
