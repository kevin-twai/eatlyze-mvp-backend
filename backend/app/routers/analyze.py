from fastapi import APIRouter, UploadFile, File
from ..models import AnalyzeResponse, VisionResult, VisionItem
from ..utils.normalizer import normalize_name
from ..services.openai_client import vision_analyze_base64
import json, base64, logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/analyze/image", response_model=AnalyzeResponse)
async def analyze_image(file: UploadFile = File(...)):
    image_bytes = await file.read()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    reply_text = await vision_analyze_base64(image_b64)
    try:
        raw = json.loads(reply_text)
        items = raw.get("items", [])
    except Exception:
        logger.exception("vision_json_parse_failed")
        return AnalyzeResponse(
            status="fail",
            reason="vision_json_parse_failed",
            debug={"raw": reply_text[:800]}
        )
    norm_items = []
    for x in items:
        name = (x.get("name") or "").strip()
        canonical_src = (x.get("canonical") or name).strip()
        canon = normalize_name(canonical_src)
        weight = x.get("weight_g", None)
        is_garnish = bool(x.get("is_garnish", False))
        norm_items.append(VisionItem(
            name=name, canonical=canon, weight_g=weight, is_garnish=is_garnish
        ))
    non_garnish = [i for i in norm_items if not i.is_garnish]
    if not non_garnish:
        return AnalyzeResponse(status="fail", reason="no_edible_items")
    has_missing = any(i.weight_g is None for i in non_garnish)
    return AnalyzeResponse(
        status="partial" if has_missing else "ok",
        reason="missing_weight" if has_missing else None,
        data=VisionResult(items=norm_items)
    )