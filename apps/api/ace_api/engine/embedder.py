"""Pluggable embeddings. Default 'hash': deterministic char/word-ngram hashing — no network, stable
across runs, adequate for topic mapping + near-dupe checks at MVP scale. 'proxy' uses the gateway
/embeddings route (dimension must match migration: vector(256))."""

from __future__ import annotations

import hashlib
import math
import re

import httpx

from ace_api.config import settings

DIM = 256


def _hash_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    words = re.findall(r"[a-z0-9]+", text.lower())
    grams = words + [" ".join(p) for p in zip(words, words[1:])]
    for g in grams:
        h = int.from_bytes(hashlib.blake2b(g.encode(), digest_size=8).digest(), "big")
        vec[h % DIM] += 1.0 if (h >> 63) else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def embed(texts: list[str]) -> list[list[float]]:
    s = settings()
    if s.embedder == "proxy" and s.llm_api_key:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{s.llm_base_url}/embeddings",
                headers={"Authorization": f"Bearer {s.llm_api_key}"},
                json={"model": "text-embedding-3-small", "input": texts, "dimensions": DIM},
            )
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]
    return [_hash_embed(t) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def to_pgvector(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
