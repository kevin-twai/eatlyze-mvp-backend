# backend/app/services/semvec.py
from __future__ import annotations

import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI
from openai.types import CreateEmbeddingResponse

load_dotenv()  # 允許用 .env 設 OPENAI_API_KEY

# 你可改這行成 "text-embedding-3-large"
DEFAULT_EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

def _coerce_texts(texts) -> List[str]:
    """
    將輸入整齊化成「非空字串陣列」；自動轉型並去掉空白與 None。
    """
    if texts is None:
        return []
    if isinstance(texts, str):
        arr = [texts]
    else:
        try:
            arr = list(texts)
        except Exception:
            arr = [str(texts)]

    clean: List[str] = []
    for t in arr:
        if t is None:
            continue
        s = str(t).strip()
        if s:
            clean.append(s)
    return clean

@dataclass
class SemanticIndex:
    model_name: str = DEFAULT_EMBED_MODEL

    def __post_init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set. export 或 .env 設好後再試。")
        self.client = OpenAI(api_key=api_key)
        self._labels: List[str] = []
        self._items: List[Dict] = []
        self._emb: Optional[List[List[float]]] = None

    def encode(self, texts, batch_size: int = 128) -> List[List[float]]:
        """
        以批次呼叫 embeddings.create，並確保 input 合規。
        """
        arr = _coerce_texts(texts)
        if not arr:
            raise ValueError("Embeddings input 为空或不合法（整理後沒有任何非空字串）")

        vecs: List[List[float]] = []
        for i in range(0, len(arr), batch_size):
            chunk = arr[i:i + batch_size]
            try:
                # OpenAI Python SDK v1.53：input 接 str 或 List[str]
                res: CreateEmbeddingResponse = self.client.embeddings.create(
                    model=self.model_name,
                    input=chunk
                )
            except Exception as e:
                raise RuntimeError(f"[embeddings] API 失敗：{e}") from e

            # 取出向量
            for d in res.data:
                vecs.append(d.embedding)

        return vecs

    def build(self, items: List[Dict], label_keys: Tuple[str, ...] = ("label", "name", "canonical", "id")):
        """
        items：知識庫裡的食材條目（list[dict]）
        會組一個可讀標籤陣列 -> 做 embeddings -> 內部保存
        """
        if not isinstance(items, list):
            raise ValueError("build() 需要 list[dict]")

        labels: List[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            # 盡量組出可辨識的文字標籤
            parts: List[str] = []
            for k in label_keys:
                v = it.get(k)
                if v:
                    parts.append(str(v))
            if not parts:
                # 萬一都沒有就整個 dict 丟進去（會 stringify），之後也會被 _coerce_texts 清理
                parts.append(str(it))
            labels.append(" | ".join(parts))

        labels = _coerce_texts(labels)
        if not labels:
            raise ValueError("build() 清理後沒有可以嵌入的標籤")

        self._labels = labels
        self._items = items
        self._emb = self.encode(self._labels)

    # 下面這些 getters 讓 build_index.py 可以取用
    def labels(self) -> List[str]:
        return self._labels

    def embeddings(self) -> List[List[float]]:
        if self._emb is None:
            return []
        return self._emb

    def items(self) -> List[Dict]:
        return self._items
