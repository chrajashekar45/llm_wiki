import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_CACHE_SIZE = 256

_client = None
_cache = {}


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env (required for embeddings).")

    _client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=120.0,
    )
    return _client


def _cache_key(text):
    return text.strip().lower()


def _embed_batch(texts):
    response = _get_client().embeddings.create(model=EMBEDDING_MODEL, input=texts)
    if not response or not response.data:
        raise RuntimeError("Embedding API returned no embeddings.")

    embeddings = [item.embedding for item in response.data if item.embedding is not None]
    if not embeddings:
        raise RuntimeError("Embedding API returned empty embeddings.")
    return embeddings


def get_embeddings(texts):
    if not texts:
        return []
    if isinstance(texts, str):
        texts = [texts]

    if len(texts) == 1:
        key = _cache_key(texts[0])
        cached = _cache.get(key)
        if cached is not None:
            return [cached]

        vector = _embed_batch(texts)[0]
        if len(_cache) >= EMBEDDING_CACHE_SIZE:
            _cache.pop(next(iter(_cache)))
        _cache[key] = vector
        return [vector]

    return _embed_batch(texts)


def clear_embedding_cache():
    _cache.clear()
