from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict
from app.services.notion_client import create_food_log

router = APIRouter()

class FoodEntry(BaseModel):
    name: str
    grams: float
    kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None

class NotionReq(BaseModel):
    date: str
    meal: str
    items: list[FoodEntry]
    totals: Dict[str, float]
    image_url: str | None = None
    notes: str | None = ""

@router.post("/log")
async def notion_log(req: NotionReq):
    payload = req.model_dump()
    return create_food_log(payload)
