from fastapi import APIRouter
from pydantic import BaseModel
from app.services.nutrition_calc import summarize_items

router = APIRouter()

class FoodItem(BaseModel):
    name: str
    grams: float

class SummaryReq(BaseModel):
    items: list[FoodItem]

@router.post("/summary")
async def nutrition_summary(req: SummaryReq):
    items = [i.model_dump() for i in req.items]
    return summarize_items(items)
