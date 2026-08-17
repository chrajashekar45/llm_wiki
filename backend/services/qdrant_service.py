import os
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams

load_dotenv()

_client = None
COLLECTION_NAME = "wiki_vectors"
MIN_VECTOR_SCORE = 0.25


def _get_client():
    global _client
    if _client is not None:
        return _client

    _client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY"),
    )
    return _client


def create_collection(vector_size):
    client = _get_client()

    if client.collection_exists(collection_name=COLLECTION_NAME):
        info = client.get_collection(collection_name=COLLECTION_NAME)
        existing_size = info.config.params.vectors.size
        if existing_size == vector_size:
            return
        client.delete_collection(collection_name=COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )


def upload_embeddings(texts, embeddings, metadatas=None):
    if not texts or not embeddings:
        raise RuntimeError("Texts and embeddings are required.")
    if len(texts) != len(embeddings):
        raise RuntimeError("Texts and embeddings count mismatch.")

    create_collection(vector_size=len(embeddings[0]))

    points = []
    for index, (text, vector) in enumerate(zip(texts, embeddings)):
        payload = {"text": text}
        if metadatas and index < len(metadatas):
            payload.update({k: v for k, v in metadatas[index].items() if v is not None})
        points.append({"id": str(uuid.uuid4()), "vector": vector, "payload": payload})

    _get_client().upsert(collection_name=COLLECTION_NAME, points=points)
    return True


def search_hits(query_embedding, limit=8, min_score=MIN_VECTOR_SCORE):
    try:
        results = _get_client().query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=limit,
        )
    except Exception:
        return []

    hits = []
    for point in results.points:
        if not point.payload:
            continue
        score = float(point.score if point.score is not None else 0.0)
        if score < min_score:
            continue

        text = point.payload.get("text")
        if not text:
            continue

        hit = {
            "source": "vector",
            "text": text,
            "score": score,
            "point_id": str(point.id),
        }
        if point.payload.get("wiki_page"):
            hit["wiki_page"] = point.payload["wiki_page"]
            hit["title"] = point.payload["wiki_page"]
        if point.payload.get("source_file"):
            hit["source_file"] = point.payload["source_file"]
        if point.payload.get("chunk_index") is not None:
            hit["chunk_index"] = point.payload["chunk_index"]

        hits.append(hit)

    return hits


def delete_vectors_for_wiki_page(wiki_page):
    client = _get_client()
    if not client.collection_exists(collection_name=COLLECTION_NAME):
        return 0

    selector = Filter(
        must=[FieldCondition(key="wiki_page", match=MatchValue(value=wiki_page))]
    )
    result = client.delete(collection_name=COLLECTION_NAME, points_selector=selector)
    return getattr(result, "operation_id", None)
