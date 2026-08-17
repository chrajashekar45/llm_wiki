"""BM25 search index for wiki passages (Whoosh)."""

import re
from pathlib import Path

from whoosh import index
from whoosh.fields import ID, STORED, TEXT, Schema
from whoosh.qparser import MultifieldParser, OrGroup

from backend.services.wiki_manager import WIKI_PATH, _split_passages, read_all_pages

INDEX_DIR = WIKI_PATH / ".search_index"
SCHEMA = Schema(
    passage_id=ID(stored=True, unique=True),
    title=TEXT(stored=True),
    text=TEXT(stored=True),
)

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "what", "who", "how", "when",
    "where", "why", "which", "do", "does", "did", "can", "could", "should",
    "would", "will", "to", "of", "in", "on", "for", "with", "and", "or", "it",
    "this", "that", "be", "by", "from", "at", "as", "about",
}

WORD_PATTERN = re.compile(r"[a-z0-9]+")

_index = None
_index_signature = None


def _current_signature():
    from backend.services.wiki_manager import _wiki_signature

    return _wiki_signature()


def invalidate_index():
    global _index, _index_signature
    _index = None
    _index_signature = None


def _build_index():
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    if index.exists_in(str(INDEX_DIR)):
        return index.open_dir(str(INDEX_DIR))

    return index.create_in(str(INDEX_DIR), SCHEMA)


def _rebuild_index():
    global _index, _index_signature

    if INDEX_DIR.exists():
        import shutil

        shutil.rmtree(INDEX_DIR, ignore_errors=True)

    ix = _build_index()
    writer = ix.writer()

    for page in read_all_pages():
        title = page["title"]
        for chunk_index, passage in enumerate(_split_passages(page["content"])):
            passage_id = f"{title}::{chunk_index}"
            writer.add_document(
                passage_id=passage_id,
                title=title,
                text=passage,
            )

    writer.commit()
    _index = ix
    _index_signature = _current_signature()
    return ix


def _get_index():
    global _index, _index_signature

    signature = _current_signature()
    if _index is not None and _index_signature == signature:
        return _index

    if index.exists_in(str(INDEX_DIR)):
        stored_sig = (INDEX_DIR / "signature.txt").read_text(encoding="utf-8") if (INDEX_DIR / "signature.txt").exists() else ""
        if stored_sig == str(signature):
            _index = index.open_dir(str(INDEX_DIR))
            _index_signature = signature
            return _index

    ix = _rebuild_index()
    (INDEX_DIR / "signature.txt").write_text(str(signature), encoding="utf-8")
    return ix


def _normalize_query(query):
    terms = [term for term in WORD_PATTERN.findall(query.lower()) if term not in STOPWORDS]
    return " ".join(terms) if terms else query


def search_wiki_bm25(query, limit=5):
    normalized = _normalize_query(query)
    if not normalized.strip():
        return []

    ix = _get_index()
    parser = MultifieldParser(["title", "text"], schema=ix.schema, group=OrGroup)
    parsed = parser.parse(normalized)

    hits = []
    with ix.searcher() as searcher:
        results = searcher.search(parsed, limit=limit * 3)
        for result in results:
            hits.append(
                {
                    "source": "wiki",
                    "title": result["title"],
                    "text": result["text"],
                    "score": float(result.score),
                    "wiki_page": result["title"],
                }
            )

    unique, seen = [], set()
    for item in sorted(hits, key=lambda row: row["score"], reverse=True):
        key = item["text"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= limit:
            break

    return unique
