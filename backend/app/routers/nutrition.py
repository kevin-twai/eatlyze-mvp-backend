from fastapi import APIRouter
from ..models import CalcRequest, CalcResponse, Macro
import pandas as pd
import os

router = APIRouter()
DATA_PATH = os.getenv("FOODS_CSV_PATH", "backend/app/data/foods_tw.csv")
FOODS = pd.read_csv(DATA_PATH).set_index("name")

def calc_item(canon: str, weight_g: float):
    if canon not in FOODS.index:
        return None
    row = FOODS.loc[canon]
    ratio = weight_g / 100.0
    return {
        "canonical": canon,
        "weight_g": weight_g,
        "kcal": float(row["kcal_per_100g"] * ratio),
        "protein_g": float(row["protein_g"] * ratio),
        "fat_g": float(row["fat_g"] * ratio),
        "carb_g": float(row["carb_g"] * ratio),
    }

@router.post("/calc/nutrition", response_model=CalcResponse)
def calc_nutrition(req: CalcRequest):
    breakdown = []
    for it in req.items:
        r = calc_item(it.canonical, it.weight_g)
        if r: breakdown.append(r)
    total = Macro(
        kcal=sum(x["kcal"] for x in breakdown) if breakdown else 0.0,
        protein_g=sum(x["protein_g"] for x in breakdown) if breakdown else 0.0,
        fat_g=sum(x["fat_g"] for x in breakdown) if breakdown else 0.0,
        carb_g=sum(x["carb_g"] for x in breakdown) if breakdown else 0.0,
    )
    return CalcResponse(total=total, breakdown=breakdown)