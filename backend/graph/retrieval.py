"""Hybrid retrieval: merge wiki keyword hits with vector hits for Q&A."""

from backend.services.wiki_manager import get_page_relative_path

WIKI_TOP_K = 5
VECTOR_TOP_K = 8
MAX_CONTEXT_TOKENS = 2000
RRF_K = 60
MIN_RRF_SCORE = 0.01
SEPARATOR = "\n\n" + ("-" * 60) + "\n\n"


def _text_key(text):
    return " ".join(text.lower().split())


def reciprocal_rank_fusion(wiki_results, vector_results, k=RRF_K):
    """Combine ranked lists using Reciprocal Rank Fusion (score = 1 / (k + rank))."""
    combined = {}

    for source_label, results in (("wiki", wiki_results), ("vector", vector_results)):
        for rank, item in enumerate(results, start=1):
            text = item.get("text", "").strip()
            if not text:
                continue

            key = _text_key(text)
            if key not in combined:
                combined[key] = {**item, "rrf_score": 0.0, "sources": set()}

            combined[key]["rrf_score"] += 1.0 / (k + rank)
            combined[key]["sources"].add(source_label)

    results = []
    for item in combined.values():
        item["sources"] = list(item["sources"])
        results.append(item)

    results.sort(key=lambda row: row["rrf_score"], reverse=True)
    return [item for item in results if item["rrf_score"] >= MIN_RRF_SCORE]


def deduplicate_results(results):
    unique, seen = [], set()
    for item in results:
        text = item.get("text", "").strip()
        if not text:
            continue
        key = _text_key(text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def build_context(results, max_tokens=MAX_CONTEXT_TOKENS):
    """Turn ranked evidence into a prompt string within a token budget (~4 chars/token)."""
    max_chars = max_tokens * 4
    selected, used_chars = [], 0

    for rank, item in enumerate(results, start=1):
        text = item.get("text", "").strip()
        if not text:
            continue

        sources = ", ".join(item.get("sources", [item.get("source", "unknown")]))
        title = item.get("wiki_page") or item.get("title", "")
        header_lines = [f"Evidence {rank}", f"Source: {sources}"]
        if title:
            header_lines.append(f"Wiki Page: {title}")
        if item.get("source_file"):
            header_lines.append(f"Upload File: {item['source_file']}")

        header = "\n".join(header_lines)
        evidence = f"{header}\n{text}"
        evidence_len = len(evidence)

        if used_chars + evidence_len > max_chars:
            remaining = max_chars - used_chars
            if remaining > 300:
                selected.append(f"{header}\n{text[:remaining].rstrip()}")
            break

        selected.append(evidence)
        used_chars += evidence_len

    return (SEPARATOR).join(selected)


def merge_retrieval(wiki_results, vector_results):
    """Full hybrid pipeline: fuse, deduplicate, and build LLM context."""
    fused = reciprocal_rank_fusion(wiki_results, vector_results)
    fused = deduplicate_results(fused)
    context = build_context(fused)
    return fused, context


def _source_group_key(item):
    wiki_page = item.get("wiki_page") or item.get("title")
    if wiki_page:
        return f"wiki:{wiki_page}"
    source_file = item.get("source_file")
    if source_file:
        return f"upload:{source_file}"
    return f"chunk:{_text_key(item.get('text', ''))[:80]}"


def format_sources_for_display(results, max_pages=5):
    """Group passages by wiki page or upload file for the UI sources panel."""
    grouped = {}

    for item in results:
        key = _source_group_key(item)
        wiki_page = item.get("wiki_page") or item.get("title")
        source_file = item.get("source_file", "")

        if key not in grouped:
            if wiki_page:
                grouped[key] = {
                    "kind": "wiki",
                    "title": wiki_page,
                    "page_path": get_page_relative_path(wiki_page),
                    "source_file": source_file,
                    "snippets": [],
                    "score": item.get("rrf_score", item.get("score", 0)),
                }
            elif source_file:
                grouped[key] = {
                    "kind": "upload",
                    "title": f"Upload: {source_file}",
                    "page_path": "",
                    "source_file": source_file,
                    "snippets": [],
                    "score": item.get("rrf_score", item.get("score", 0)),
                }
            else:
                grouped[key] = {
                    "kind": "upload",
                    "title": "Upload chunk",
                    "page_path": "",
                    "source_file": "",
                    "snippets": [],
                    "score": item.get("rrf_score", item.get("score", 0)),
                }

        snippet = item.get("text", "").strip()
        if snippet and snippet not in grouped[key]["snippets"]:
            grouped[key]["snippets"].append(snippet)
        grouped[key]["score"] = max(grouped[key]["score"], item.get("rrf_score", item.get("score", 0)))

    ranked = sorted(grouped.values(), key=lambda row: row["score"], reverse=True)
    return ranked[:max_pages]
