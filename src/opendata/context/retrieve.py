"""Retrieval entry point — vector when embeddings are configured, else lexical.

The engine calls `retrieve_context(store, question)` and never worries which is
active. Vector retrieval kicks in when an embedder is available (VOYAGE_API_KEY,
the [embeddings] extra, or OPENDATA_EMBEDDINGS=hash) *and* the store was indexed
with embeddings; otherwise it falls back to the lexical retriever, so the offline
path always works.
"""

from __future__ import annotations

from .embeddings import get_embedder
from .store import ContextStore, Retrieved


def retrieve_context(store: ContextStore, question: str, k: int = 5) -> Retrieved:
    embedder = get_embedder()
    if embedder and store.vectors:
        try:
            qvec = embedder.embed([question], input_type="query")[0]
            return store.vector_retrieve(qvec, k)
        except Exception:  # noqa: BLE001 — embedding failed at query time → lexical
            pass
    return store.retrieve(question, k)
