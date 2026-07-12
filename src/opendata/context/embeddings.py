"""Embedding providers for semantic retrieval (architecture §4).

Pluggable, like the LLM layer. Selection via OPENDATA_EMBEDDINGS:

    unset / "auto"  → Voyage if VOYAGE_API_KEY set, else local fastembed if
                      installed, else None (retrieval falls back to lexical)
    "hash"          → dependency-free deterministic hashing embedder (always
                      available; captures lexical/substring similarity, not deep
                      semantics — good for tests and a zero-dep default)
    "fastembed"     → local ONNX model (needs the [embeddings] extra)
    "voyage"        → Voyage API (Anthropic's recommended embeddings; needs
                      voyageai + VOYAGE_API_KEY)
    "none"          → disable; use lexical retrieval

Installing `opendata[embeddings]` turns semantic retrieval on automatically.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Optional, Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        ...


class HashingEmbedder:
    """Deterministic, dependency-free embeddings: word tokens + char 3-grams
    hashed into a fixed-dim vector, L2-normalized. Not deep-semantic, but robust
    to substrings/typos and identical across processes (uses hashlib, not the
    salted builtin hash). The always-available default for the vector pipeline."""

    name = "hash"

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _features(self, text: str):
        s = text.lower()
        for tok in _TOKEN.findall(s):
            yield tok
            for i in range(len(tok) - 2):
                yield tok[i : i + 3]

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for feat in self._features(text):
            idx = int(hashlib.md5(feat.encode()).hexdigest(), 16) % self.dim
            v[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in v))
        return [x / norm for x in v] if norm else v

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [self._one(t) for t in texts]


class FastEmbedProvider:
    """Local semantic embeddings via ONNX (no API key). Needs the [embeddings] extra."""

    name = "fastembed"

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding  # lazy

        self._model = TextEmbedding(model_name=model)

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [list(map(float, e)) for e in self._model.embed(texts)]


class VoyageEmbedder:
    """Voyage AI embeddings (Anthropic's recommended). Needs voyageai + VOYAGE_API_KEY."""

    name = "voyage"

    def __init__(self, model: str = "voyage-3"):
        import voyageai  # lazy

        self._client = voyageai.Client()
        self._model = model

    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        it = "query" if input_type == "query" else "document"
        return self._client.embed(texts, model=self._model, input_type=it).embeddings


def _importable(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except Exception:  # noqa: BLE001
        return False


def get_embedder(name: Optional[str] = None) -> Optional[Embedder]:
    name = name if name is not None else os.getenv("OPENDATA_EMBEDDINGS")
    try:
        if name in (None, "", "auto"):
            if os.getenv("VOYAGE_API_KEY") and _importable("voyageai"):
                return VoyageEmbedder()
            if _importable("fastembed"):
                return FastEmbedProvider()
            return None
        if name in ("none", "off", "lexical"):
            return None
        if name in ("hash", "hashing"):
            return HashingEmbedder()
        if name == "fastembed":
            return FastEmbedProvider()
        if name == "voyage":
            return VoyageEmbedder()
    except Exception:  # noqa: BLE001 — missing SDK/model → fall back to lexical
        return None
    return None
