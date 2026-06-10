import os
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

load_dotenv()

client = None
COLLECTION_NAME = "wiki_vectors"


def _get_client():
    global client
    if client is not None:
        return client

    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )
    return client


def create_collection(vector_size=384):
    qclient = _get_client()
    if qclient.collection_exists(collection_name=COLLECTION_NAME):
        return

    qclient.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upload_embeddings(texts, embeddings):
    try:
        _upsert_embeddings(texts, embeddings)
    except Exception:
        try:
            create_collection()
            _upsert_embeddings(texts, embeddings)
        except Exception:
            return False

    return True


def _upsert_embeddings(texts, embeddings):
    qclient = _get_client()
    points = []
    for text, emb in zip(texts, embeddings):
        points.append({
            "id": str(uuid.uuid4()),
            "vector": emb,
            "payload": {"text": text},
        })

    qclient.upsert(collection_name=COLLECTION_NAME, points=points)


def search(query_embedding, limit=5):
    try:
        qclient = _get_client()
        results = qclient.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=limit,
        )
    except Exception:
        return []

    texts = []
    for point in results.points:
        if point.payload and "text" in point.payload:
            texts.append(point.payload["text"])

    return texts
