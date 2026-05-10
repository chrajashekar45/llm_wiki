from langgraph.graph import END, StateGraph
from typing import TypedDict
import json
import re

# Services
from backend.services.llm_service import call_groq
from backend.services.embedding import get_embeddings
from backend.services.qdrant_service import upload_embeddings, search
from backend.services.wiki_manager import (
    save_page,
    update_index,
    log_event,
    search_wiki,
    unique_slug,
    upsert_maintained_page,
    get_wiki_overview,
)
from backend.services.entity_extractor import extract_entities


# ---------------- STATE ---------------- #

class GraphState(TypedDict):
    input: str
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


# ---------------- NODES ---------------- #

# 1. Chunking
def chunk_text(state):
    text = state["input"]
    chunks = [text[i:i+500] for i in range(0, len(text), 500)]
    return {"chunks": chunks}


# 2. Embedding
def embed(state):
    embeddings = get_embeddings(state["chunks"])
    return {"embeddings": embeddings}


# 3. Store in Qdrant
def store(state):
    upload_embeddings(state["chunks"], state["embeddings"])
    return {}


# 4. Summarization
def summarize(state):
    prompt = f"""
Summarize this source for a persistent personal knowledge wiki.
Focus on reusable claims, facts, definitions, entities, concepts, and notable uncertainty.

Source:
{state['input']}
"""
    summary = call_groq(prompt)
    return {"summary": summary}


# 5. Entity extraction
def extract_entities_node(state):
    entities = extract_entities(state["input"])
    return {"entities": entities}


# 6. Create Wiki Page
def create_wiki(state):
    existing_context = "\n\n".join(search_wiki(state["input"], limit=5))
    title_prompt = f"""
Create a short, descriptive wiki page title for this source.
Return only the title, no punctuation wrapper.

Source:
{state['input'][:4000]}
"""
    title = unique_slug(call_groq(title_prompt))

    content = f"# {title}\n\n"
    content += "## Type\nSource summary\n\n"
    content += f"## Summary\n{state['summary']}\n\n"
    content += f"## Entities\n{', '.join(state['entities'])}\n\n"

    if existing_context:
        content += "## Related Existing Wiki Context\n"
        content += existing_context[:3000]
        content += "\n"

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
    wiki_overview = get_wiki_overview()
    prompt = f"""
You maintain a persistent markdown knowledge wiki.

Given the new source summary, entities, and existing wiki overview, decide which wiki pages should be created or updated.
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
  "contradictions": ["brief contradiction or tension notes"],
  "open_questions": ["brief questions worth investigating"]
}}

Rules:
- Create or update pages for important entities, concepts, comparisons, and syntheses.
- Include links to the new source page as [{state['title']}](./{state['title']}.md) where relevant.
- Preserve uncertainty and contradictions instead of smoothing them away.
- Keep each page concise but useful.
- Return only JSON.

New source page: {state['title']}
New source summary:
{state['summary']}

Entities:
{', '.join(state['entities'])}

Existing wiki overview:
{wiki_overview}
"""
    maintenance = parse_json_object(call_groq(prompt))

    if not isinstance(maintenance.get("pages"), list):
        maintenance["pages"] = []
    if not isinstance(maintenance.get("contradictions"), list):
        maintenance["contradictions"] = []
    if not isinstance(maintenance.get("open_questions"), list):
        maintenance["open_questions"] = []

    return {"maintenance": maintenance}


def apply_maintenance(state):
    maintenance = state.get("maintenance") or {}
    touched_pages = []

    for page in maintenance.get("pages", []):
        title = page.get("title")
        content = page.get("content")
        summary = page.get("summary") or "Maintained wiki page."
        category = page.get("category") or "concepts"

        if not title or not content:
            continue

        touched_pages.append(upsert_maintained_page(title, content, summary, category))

    if maintenance.get("contradictions"):
        content = "\n".join(f"- {item}" for item in maintenance["contradictions"])
        touched_pages.append(
            upsert_maintained_page(
                "contradictions",
                f"# contradictions\n\n## Current Tensions\n{content}\n",
                "Contradictions and tensions found across sources.",
                "syntheses",
            )
        )

    if maintenance.get("open_questions"):
        content = "\n".join(f"- {item}" for item in maintenance["open_questions"])
        touched_pages.append(
            upsert_maintained_page(
                "open_questions",
                f"# open_questions\n\n## Questions To Investigate\n{content}\n",
                "Open questions and research gaps.",
                "syntheses",
            )
        )

    if touched_pages:
        log_event("MAINTAIN", f"Updated pages: {', '.join(touched_pages)}")

    return {"maintenance": {**maintenance, "touched_pages": touched_pages}}


# 7. Retrieve from Qdrant
def retrieve(state):
    if state.get("wiki_results"):
        return {"retrieved": []}

    query_embedding = get_embeddings([state["input"]])[0]
    results = search(query_embedding)
    return {"retrieved": results}


# 8. Retrieve from Wiki
def retrieve_wiki(state):
    wiki_results = search_wiki(state["input"])
    return {"wiki_results": wiki_results}


# 9. Merge Context
def merge_context(state):
    context_parts = []

    if state.get("wiki_results"):
        context_parts.append("Relevant Wiki Content:")
        context_parts.extend(state["wiki_results"])

    if state.get("retrieved"):
        context_parts.append("Relevant Retrieved Chunks:")
        context_parts.extend(state["retrieved"])

    context = "\n\n".join(context_parts)

    return {"context": context}


# 10. Generate Answer
def generate_answer(state):
    prompt = f"""
You are a strict question-answering system.

Answer ONLY from the provided context.
If the answer is present in the context, extract it clearly.
Include the source page names when they are available.
DO NOT use outside knowledge.
DO NOT guess.
If the context does not contain the answer, say: "I don't have enough information in the wiki to answer that."

Context:
{state['context']}

Question:
{state['input']}

Answer:
"""
    answer = call_groq(prompt)
    return {"answer": answer}


# 11. (Optional) Store insight back to wiki
def store_insight(state):
    title = "insight_" + state["input"][:20].replace(" ", "_")

    content = f"# Insight\n\n{state['answer']}"

    save_page(title, content)
    log_event("QUERY_INSIGHT", f"Stored insight: {title}")

    return {}


# ---------------- INGEST GRAPH ---------------- #

ingest_builder = StateGraph(GraphState)

ingest_builder.add_node("chunk", chunk_text)
ingest_builder.add_node("embed", embed)
ingest_builder.add_node("store", store)
ingest_builder.add_node("summarize", summarize)
ingest_builder.add_node("entities", extract_entities_node)
ingest_builder.add_node("wiki", create_wiki)
ingest_builder.add_node("plan_maintenance", plan_maintenance)
ingest_builder.add_node("apply_maintenance", apply_maintenance)

ingest_builder.set_entry_point("chunk")
ingest_builder.add_edge("chunk", "embed")
ingest_builder.add_edge("embed", "store")
ingest_builder.add_edge("store", "summarize")
ingest_builder.add_edge("summarize", "entities")
ingest_builder.add_edge("entities", "wiki")
ingest_builder.add_edge("wiki", "plan_maintenance")
ingest_builder.add_edge("plan_maintenance", "apply_maintenance")
ingest_builder.add_edge("apply_maintenance", END)

ingest_graph = ingest_builder.compile()


# ---------------- QUERY GRAPH ---------------- #

query_builder = StateGraph(GraphState)

query_builder.add_node("retrieve", retrieve)
query_builder.add_node("retrieve_wiki", retrieve_wiki)
query_builder.add_node("merge", merge_context)
query_builder.add_node("generate", generate_answer)

query_builder.set_entry_point("retrieve_wiki")
query_builder.add_edge("retrieve_wiki", "retrieve")
query_builder.add_edge("retrieve", "merge")
query_builder.add_edge("merge", "generate")
query_builder.add_edge("generate", END)

query_graph = query_builder.compile()

# Backward-compatible alias for older scripts. Use ingest_graph or query_graph
# directly in new code so uploads and questions stay separate.
graph = query_graph
