
# Eatlyze Backend (Clean Start)

Local:
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Render env:
- OPENAI_API_KEY
- ALLOWED_ORIGINS (optional)

Start:
```
uvicorn main:app --host 0.0.0.0 --port $PORT
```
