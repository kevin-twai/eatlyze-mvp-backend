# backend/app/routers/analyze.py
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

# ---- 嘗試載入新版營養模組；失敗就退回舊版 ----
try:
    from app.services import nutrition_service_v2 as nutrition
except Exception:
    from app.services import nutrition_service as nutrition  # type: ignore

# ---- OpenAI 視覺端：允許缺席時仍可回應（回傳空項目讓前端顯示提示）----
try:
    from app.services.openai_client import vision_analyze_base64
except Exception:
    vision_analyze_base64 = None  # type: ignore


# ----------------- 請求/回應模型（只用基礎型別，避免 bytes） -----------------
class ItemIn(BaseModel):
    name: Optional[str] = None
    canonical: Optional[str] = None
    weight_g: float = Field(ge=0, default=0)
    is_garnish: bool = False


class AnalyzeRequest(BaseModel):
    image_base64: str
    include_garnish: bool = False


class AnalyzeResponse(BaseModel):
    items: List[Dict[str, Any]]
    totals: Dict[str, float]


# ----------------- Router 本體 -----------------
router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.get("/ping")
def ping():
    return {"ok": True}


@router.post("/image", response_model=AnalyzeResponse)
def analyze_image(req: AnalyzeRequest):
    """
    前端送 base64 圖 → 視覺模型 → 食材清單 → 營養加總。
    回傳只含字串/數字/布林，避免 bytes 造成 500。
    """
    # 1) 用 LLM 視覺抓食材（允許失敗）
    items: List[Dict[str, Any]] = []
    if vision_analyze_base64 is not None:
        try:
            items = vision_analyze_base64(req.image_base64)
            if not isinstance(items, list):
                items = []
        except Exception as e:
            # 模型失敗 → 讓前端顯示提示，仍繼續下去
            print(f"[vision] warn: {e}")
            items = []
    else:
        # 沒有 openai_client，回傳空清單
        items = []

    # 2) 防守：把欄位收斂到我們要的鍵，避免奇怪型別
    clean_items: List[Dict[str, Any]] = []
    for it in items:
        clean_items.append(
            {
                "name": (it.get("name") or "")[:200],
                "canonical": (it.get("canonical") or "")[:200],
                "weight_g": float(it.get("weight_g") or 0),
                "is_garnish": bool(it.get("is_garnish") or False),
            }
        )

    # 3) 交給營養引擎計算（會處理別名、fuzzy/embedding、有/無配菜是否計入）
    try:
        enriched, totals = nutrition.calc(clean_items, include_garnish=req.include_garnish)
    except Exception as e:
        # 萬一 CSV 或服務有問題，回 500 但訊息乾淨
        print(f"[nutrition] error: {e}")
        raise HTTPException(status_code=500, detail="nutrition service failed")

    # 4) 確保回傳都是可 JSON 的基本型別
    safe_items: List[Dict[str, Any]] = []
    for it in enriched:
        safe_items.append(
            dict(
                name=it.get("name") or "",
                label=it.get("label") or (it.get("name") or ""),
                canonical=it.get("canonical") or "",
                weight_g=float(it.get("weight_g") or 0),
                is_garnish=bool(it.get("is_garnish") or False),
                kcal=float(it.get("kcal") or 0),
                protein_g=float(it.get("protein_g") or 0),
                fat_g=float(it.get("fat_g") or 0),
                carb_g=float(it.get("carb_g") or 0),
                matched=bool(it.get("matched") or False),
            )
        )

    safe_totals = dict(
        kcal=float(totals.get("kcal") or 0),
        protein_g=float(totals.get("protein_g") or 0),
        fat_g=float(totals.get("fat_g") or 0),
        carb_g=float(totals.get("carb_g") or 0),
    )

    return AnalyzeResponse(items=safe_items, totals=safe_totals)
