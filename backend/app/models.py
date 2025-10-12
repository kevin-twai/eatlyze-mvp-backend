from typing import Optional, List, Literal
from pydantic import BaseModel

class VisionItem(BaseModel):
    name: str
    canonical: str
    weight_g: Optional[float] = None
    is_garnish: bool = False

class VisionResult(BaseModel):
    items: List[VisionItem]

class AnalyzeResponse(BaseModel):
    status: Literal["ok","partial","fail"]
    reason: Optional[str] = None
    debug: Optional[dict] = None
    data: Optional[VisionResult] = None

class CalcItem(BaseModel):
    canonical: str
    weight_g: float

class CalcRequest(BaseModel):
    items: List[CalcItem]

class Macro(BaseModel):
    kcal: float
    protein_g: float
    fat_g: float
    carb_g: float

class CalcResponse(BaseModel):
    total: Macro
    breakdown: List[dict]