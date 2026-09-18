"""Embeddings: the one capability the semantic metrics need, and nothing more.

This adds no package. `openai` is already a core dependency — `pyproject.toml`
lists it with the comment "(and embeddings)" — and the memory backends already
call it this way: `SupabaseFactStore` embeds `"subject: content"` with
`text-embedding-3-small` to retrieve facts, and `langmem_store` does the same.

What it does need is a key. `OPENAI_API_KEY` and `OPENAI_EMBED_MODEL` are the
same two variables those backends use, so anyone who has configured either of
them already has this working, and anyone who has not gets `None` — which is the
designed answer, not a failure. The four semantic metrics say so in their filler
rather than reporting a zero.
"""

from __future__ import annotations

import math
import os

DEFAULT_MODEL = "text-embedding-3-small"


def key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def model() -> str:
    return os.getenv("OPENAI_EMBED_MODEL", "").strip() or DEFAULT_MODEL


def available() -> bool:
    """Whether an embedding call could be made at all. Callers check this before
    building a prompt, so a keyless install never pays for the attempt."""
    return bool(key())


def embed(texts: list[str]) -> list[list[float]] | None:
    """One vector per text, or None when there is no key or the call failed.

    Never raises: a metric that cannot be computed is None, and a missing
    embedding must not take the batch run down with it.
    """
    if not texts or not available():
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key())
        response = client.embeddings.create(model=model(), input=texts)
    except Exception:  # noqa: BLE001 — any failure means "no vectors", not a crash
        return None
    return [item.embedding for item in response.data]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity. Returns 0.0 for a zero vector rather than raising —
    a seat that said nothing has no position, and 0 is the honest stand-in."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0
