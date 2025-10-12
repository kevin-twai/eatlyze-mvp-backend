
# Eatlyze Backend Patch (Vision partial + Normalizer + Nutrition calc)

## Endpoints
- `POST /analyze/image` → 解析圖片，允許缺重，回傳 `ok` / `partial` / `fail`
- `POST /calc/nutrition` → 前端補完重量後計算營養素

## Env
- `OPENAI_API_KEY` 必填
- `FOODS_CSV_PATH`（可選）指定食材表路徑，預設 `backend/app/data/foods_tw.csv`

## 說明
- Vision 回傳 JSON 嚴格化（prompt 已約束），若解析失敗會回 `vision_json_parse_failed`
- 名稱正規化支援中/日/英常見寫法（見 `utils/normalizer.py`）
- `is_garnish=true` 項目可在前端忽略或設定極小權重
