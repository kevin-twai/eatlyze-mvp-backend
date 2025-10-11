# Eatlyze Taiwan — MVP Backend (FastAPI, No Pandas)

純 Python 依賴，Render 免費方案可直接部署；附 `runtime.txt` (3.11.9)。

## 本機啟動
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
# http://localhost:8000/docs
```

## Render 部署（用 render.yaml）
- Build Command: `pip install --upgrade pip && pip install --no-cache-dir -r backend/requirements.txt`
- Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
