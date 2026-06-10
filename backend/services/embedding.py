import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = None
DEFAULT_EMBEDDING_MODEL = os.getenv("OPENROUTER_EMBEDDING_MODEL", "openai/text-embedding-3-small")


def _get_client():
    global client

    if client is not None:
        return client

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to your .env file before using embeddings."
        )

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    return client


def get_embeddings(texts):
    if not texts:
        return []

    if isinstance(texts, str):
        texts = [texts]

    response = _get_client().embeddings.create(
        model=DEFAULT_EMBEDDING_MODEL,
        input=texts,
    )

    return [item.embedding for item in response.data]
