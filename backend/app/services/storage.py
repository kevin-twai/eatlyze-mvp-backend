# backend/app/services/storage.py
from __future__ import annotations
import os
import uuid
import base64
from typing import Optional

# 共用 httpx
import httpx

# 只有 R2/S3 會用到
try:
    import boto3  # type: ignore
except Exception:
    boto3 = None  # 沒裝也可跑 IMGUR/local

# 讀環境變數決定儲存後端
PROVIDER = os.getenv("STORAGE_PROVIDER", "local").lower()
# 通用：服務對外基底 URL（local 時回傳 /image 用）
BASE_URL = os.getenv("BASE_URL", "https://eatlyze-backend.onrender.com")

# Local 靜態資料夾（作為備援或 provider=local）
LOCAL_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
os.makedirs(LOCAL_DIR, exist_ok=True)

# R2 / S3 相容儲存設定
R2_ACCOUNT_ID   = os.getenv("R2_ACCOUNT_ID", "")   # e.g. "abcdef1234567890"
R2_ACCESS_KEY   = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY   = os.getenv("R2_SECRET_KEY", "")
R2_BUCKET       = os.getenv("R2_BUCKET", "")
# R2 S3 endpoint => f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
R2_ENDPOINT     = os.getenv("R2_ENDPOINT", f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com")
# 公開讀取 URL（建議用自訂 domain/CNAME），否則就用官方 public base
R2_PUBLIC_BASE  = os.getenv("R2_PUBLIC_BASE", "").rstrip("/")

# Imgur（匿名上傳可用 client id）
IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID", "")


def _gen_filename(original_name: str) -> str:
    stem = uuid.uuid4().hex
    ext = ""
    if "." in original_name:
        ext = "." + original_name.split(".")[-1].lower()
    return f"{stem}{ext}"


def store_local(raw: bytes, original_name: str) -> str:
    """存本機（Render ephemeral），回傳 /image URL。"""
    fname = _gen_filename(original_name)
    path  = os.path.join(LOCAL_DIR, fname)
    with open(path, "wb") as f:
        f.write(raw)
    return f"{BASE_URL}/image/{fname}"


def store_imgur(raw: bytes, original_name: str) -> str:
    """上傳 Imgur（匿名），回傳 https URL。"""
    if not IMGUR_CLIENT_ID:
        # 沒設定就退回 local
        return store_local(raw, original_name)

    b64 = base64.b64encode(raw).decode("utf-8")
    headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
    data = {"image": b64, "type": "base64"}
    with httpx.Client(timeout=20.0) as client:
        r = client.post("https://api.imgur.com/3/image", headers=headers, data=data)
        r.raise_for_status()
        j = r.json()
        link = j.get("data", {}).get("link")
        if not link:
            # 回退 local
            return store_local(raw, original_name)
        return link


def store_r2(raw: bytes, original_name: str) -> str:
    """上傳 Cloudflare R2（S3 相容），回傳公開 URL。"""
    if not (R2_ACCESS_KEY and R2_SECRET_KEY and R2_BUCKET and R2_ENDPOINT):
        return store_local(raw, original_name)

    if boto3 is None:
        # 套件未安裝，回退 local
        return store_local(raw, original_name)

    fname = _gen_filename(original_name)
    key   = f"uploads/{fname}"

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
    )
    # 上傳
    s3.put_object(Bucket=R2_BUCKET, Key=key, Body=raw, ContentType=_guess_content_type(original_name))

    if R2_PUBLIC_BASE:
        # 你在 R2 bucket 設好「公開讀取」與 CNAME/自訂網域，這樣連結最好用
        return f"{R2_PUBLIC_BASE}/{key}"
    else:
        # 沒有自訂公開 base，退而求其次（需 Bucket public 或用 pre-signed URL）
        return f"{R2_ENDPOINT}/{R2_BUCKET}/{key}"


def _guess_content_type(name: str) -> str:
    name = name.lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    # 預設 jpeg
    return "image/jpeg"


def store_image_and_get_url(raw: bytes, original_name: str) -> str:
    """
    統一的入口：依 PROVIDER 儲存後回傳外部可讀取的 URL。
    PROVIDER ∈ {"r2", "imgur", "local"}，沒設或錯誤就 fallback local。
    """
    prov = PROVIDER
    try:
        if prov == "r2":
            return store_r2(raw, original_name)
        if prov == "imgur":
            return store_imgur(raw, original_name)
        # default local
        return store_local(raw, original_name)
    except Exception:
        # 任何失敗都回退 local，確保服務不中斷
        return store_local(raw, original_name)