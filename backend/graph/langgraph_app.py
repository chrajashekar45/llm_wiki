"""LangGraph workflows for document ingest and question answering."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from langgraph.graph import END, StateGraph

from backend.graph.retrieval import (
    VECTOR_TOP_K,
    WIKI_TOP_K,
    merge_retrieval,
)
from backend.services.embedding import get_embeddings
from backend.services.entity_extractor import extract_entities
from backend.services.llm_service import call_groq
from backend.services.qdrant_service import search_hits, upload_embeddings
from backend.services.wiki_manager import (
    get_wiki_overview,
    log_event,
    save_page,
    search_wiki,
    search_wiki_hits,
    unique_slug,
    update_index,
    upsert_maintained_page,
)

CHUNK_SIZE = 500
SOURCE_PREVIEW_CHARS = 4000
RELATED_WIKI_CHARS = 3000


class GraphState(TypedDict):
    input: str
    source_file: str
    chunks: list
    embeddings: list
    retrieved: list
    wiki_results: list
    summary: str
    entities: list
    context: str
    answer: str
    title: str
    maintenance: dict
    hybrid_results: list


# --- Ingest nodes ---


def chunk_text(state):
    text = state["input"]
    return {"chunks": [text[i : i + CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]}


def embed(state):
    return {"embeddings": get_embeddings(state["chunks"])}


def store_vectors(state):
    wiki_page = state.get("title") or ""
    source_file = state.get("source_file") or ""
    metadatas = [
        {
            "wiki_page": wiki_page,
            "source_file": source_file,
            "chunk_index": index,
        }
        for index in range(len(state["chunks"]))
    ]
    stored = upload_embeddings(state["chunks"], state["embeddings"], metadatas)
    maintenance = state.get("maintenance") or {}
    maintenance["qdrant_stored"] = stored
    return {"maintenance": maintenance}


def summarize(state):
    prompt = (
        "Summarize this source for a persistent personal knowledge wiki.\n"
        "Focus on reusable claims, facts, definitions, entities, concepts, and uncertainty.\n\n"
        f"Source:\n{state['input']}"
    )
    return {"summary": call_groq(prompt)}


def extract_entities_node(state):
    return {"entities": extract_entities(state["input"])}


def create_wiki(state):
    related = "\n\n".join(search_wiki(state["input"], limit=WIKI_TOP_K))
    title_prompt = (
        "Create a short, descriptive wiki page title for this source.\n"
        "Return only the title, no punctuation wrapper.\n\n"
        f"Source:\n{state['input'][:SOURCE_PREVIEW_CHARS]}"
    )
    title = unique_slug(call_groq(title_prompt))

    content = (
        f"# {title}\n\n"
        "## Type\nSource summary\n\n"
        f"## Summary\n{state['summary']}\n\n"
        f"## Entities\n{', '.join(state['entities'])}\n\n"
    )
    if related:
        content += f"## Related Existing Wiki Context\n{related[:RELATED_WIKI_CHARS]}\n"

    save_page(title, content, overwrite=True)
    update_index(title, state["summary"])
    log_event("INGEST", f"Created page: {title}")
    return {"title": title}


def parse_json_object(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def plan_maintenance(state):
    prompt = f"""
You maintain a persistent markdown knowledge wiki.

Given the new source summary, entities, and existing wiki overview,
decide which wiki pages should be created or updated.

Return strict JSON with this shape:
{{
  "pages": [
    {{
      "title": "short concept or entity page title",
      "category": "entities or concepts or syntheses",
      "summary": "one-line index summary",
      "content": "complete markdown page content"
    }}
  ],
  "contradictions": [],
  "open_questions": []
}}

Rules:
- Create or update pages for important entities and concepts.
- Keep each page concise.
- Return only JSON.

New source page: {state['title']}

New source summary:
{state['summary']}

Entities:
{', '.join(state['entities'])}

Existing wiki overview:
{get_wiki_overview()}
"""
    maintenance = parse_json_object(call_groq(prompt))
    for key in ("pages", "contradictions", "open_questions"):
        if not isinstance(maintenance.get(key), list):
            maintenance[key] = []
    return {"maintenance": maintenance}


def apply_maintenance(state):
    maintenance = state.get("maintenance") or {}
    touched_pages = []

    for page in maintenance.get("pages", []):
        title = page.get("title")
        content = page.get("content")
        if not title or not content:
            continue
        touched_pages.append(
            upsert_maintained_page(
                title,
                content,
                page.get("summary") or "Maintained wiki page.",
                page.get("category") or "concepts",
            )
        )

    if maintenance.get("contradictions"):
        body = "\n".join(f"- {item}" for item in maintenance["contradictions"])
        touched_pages.append(
            upsert_maintained_page(
                "contradictions",
                f"# contradictions\n\n## Current Tensions\n{body}\n",
                "Contradictions and tensions found across sources.",
                "syntheses",
            )
        )

    if maintenance.get("open_questions"):
        body = "\n".join(f"- {item}" for item in maintenance["open_questions"])
        touched_pages.append(
            upsert_maintained_page(
                "open_questions",
                f"# open_questions\n\n## Questions To Investigate\n{body}\n",
                "Open questions and research gaps.",
                "syntheses",
            )
        )

    if touched_pages:
        log_event("MAINTAIN", f"Updated pages: {', '.join(touched_pages)}")

    return {"maintenance": {**maintenance, "touched_pages": touched_pages}}


# --- Query nodes ---


def _vector_search(question):
    query_vector = get_embeddings([question])[0]
    return search_hits(query_vector, limit=VECTOR_TOP_K)


def retrieve_all(state):
    """Run wiki keyword search and vector search in parallel."""
    question = state["input"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        wiki_future = executor.submit(search_wiki_hits, question, WIKI_TOP_K)
        vector_future = executor.submit(_vector_search, question)
        wiki_results = wiki_future.result()
        retrieved = vector_future.result()

    return {"wiki_results": wiki_results, "retrieved": retrieved}


def merge_context(state):
    fused, context = merge_retrieval(
        state.get("wiki_results") or [],
        state.get("retrieved") or [],
    )
    return {"hybrid_results": fused, "context": context}


def generate_answer(state):
    prompt = f"""
You are a strict retrieval-augmented question-answering system.
Answer ONLY using the evidence below.

Rules:
1. Do not use outside knowledge.
2. Do not guess or invent facts.
3. Write a clear, standalone answer in plain prose.
4. Do NOT include citations, source names, evidence numbers, or footnotes in the answer.
5. Do NOT repeat or quote long passages from the evidence.
6. If evidence is insufficient, say: "I don't have enough information in the wiki to answer that."

Retrieved Evidence:
--------------------------------------------------
{state["context"]}
--------------------------------------------------

Question:
{state["input"]}

Answer:
"""
    return {"answer": call_groq(prompt)}


# --- Graph wiring ---


def _build_ingest_graph():
    graph = StateGraph(GraphState)
    graph.add_node("chunk", chunk_text)
    graph.add_node("embed", embed)
    graph.add_node("summarize", summarize)
    graph.add_node("entities", extract_entities_node)
    graph.add_node("wiki", create_wiki)
    graph.add_node("store_vectors", store_vectors)
    graph.add_node("plan_maintenance", plan_maintenance)
    graph.add_node("apply_maintenance", apply_maintenance)

    graph.set_entry_point("chunk")
    graph.add_edge("chunk", "embed")
    graph.add_edge("embed", "summarize")
    graph.add_edge("summarize", "entities")
    graph.add_edge("entities", "wiki")
    graph.add_edge("wiki", "store_vectors")
    graph.add_edge("store_vectors", "plan_maintenance")
    graph.add_edge("plan_maintenance", "apply_maintenance")
    graph.add_edge("apply_maintenance", END)
    return graph.compile()


def _build_query_graph():
    graph = StateGraph(GraphState)
    graph.add_node("retrieve_all", retrieve_all)
    graph.add_node("merge", merge_context)
    graph.add_node("generate", generate_answer)

    graph.set_entry_point("retrieve_all")
    graph.add_edge("retrieve_all", "merge")
    graph.add_edge("merge", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


ingest_graph = _build_ingest_graph()
query_graph = _build_query_graph()
