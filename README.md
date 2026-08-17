# LLM Wiki Knowledge System

A personal knowledge-base app that turns uploaded documents into a **living markdown wiki** and lets you **ask questions** against everything it has learned.

Think of it like a research assistant who:

1. Reads documents you upload
2. Writes organized notes in a folder you control
3. Keeps those notes updated over time
4. Answers questions using only those notes

---

## Table of Contents

- [The Big Idea (Non-Technical)](#the-big-idea-non-technical)
- [How It Works in Practice](#how-it-works-in-practice)
- [Architecture](#architecture)
- [Performance Optimizations](#performance-optimizations)
- [Project Structure](#project-structure)
- [Technical Deep Dive](#technical-deep-dive)
- [Setup (Local Development)](#setup-local-development)
- [Run with Docker](#run-with-docker)
- [Environment Variables](#environment-variables)
- [Supported File Types](#supported-file-types)
- [LLM Providers](#llm-providers)
- [Managing Uploads and Wiki Pages](#managing-uploads-and-wiki-pages)
- [Current Limitations](#current-limitations)
- [Deployment Checklist](#deployment-checklist)
- [Smoke Test](#smoke-test)

---

## The Big Idea (Non-Technical)

Most chatbots answer from general training data. This project is different.

**When you upload a file**, the system summarizes it, extracts important topics, creates wiki pages as plain markdown files, and updates related concept pages.

**When you ask a question**, the system searches your wiki and its vector memory, combines the best evidence, and asks an LLM to answer using only that evidence.

If the wiki does not contain enough information, it should say so instead of guessing.

Your knowledge lives in `data/wiki/` as readable `.md` files.

---

## How It Works in Practice

### 1. Upload a document

1. Open the Streamlit app sidebar
2. Choose files — they are added to an **upload queue** (not ingested immediately)
3. Review the queue and click **Remove** on any accidental upload
4. Click **Ingest Documents** when ready

The ingest pipeline:

```text
chunk → embed → summarize → entities → wiki → store_vectors → plan_maintenance → apply_maintenance
```

### 2. Ask a question

1. Type a question in the main area
2. Click **Get Answer**

The query pipeline:

```text
retrieve_all (parallel) → merge → generate
```

Answers typically return in a few seconds (see [Performance Optimizations](#performance-optimizations)).

### 3. Delete a wiki page

Use **Manage Wiki Pages** in the sidebar to select and delete a page. This removes the markdown file, its index entry, and linked Qdrant vectors.

### 4. Sources in answers

- **Answer** — clean prose at the top
- **Sources** — grouped by **wiki page title** (with `data/wiki/page.md` path) or **upload filename** for vector chunks
- Expand **snippet** under each source to see the passage used internally by retrieval

---

## Architecture

```text
┌─────────────────────────────────────────────────────────┐
│                    Streamlit UI                         │
│     upload queue · ingest · delete pages · Q&A          │
└─────────────────────────┬───────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
   ┌──────────────┐               ┌──────────────┐
   │ Ingest Graph │               │  Query Graph │
   │  (LangGraph) │               │  (LangGraph) │
   └──────┬───────┘               └──────┬───────┘
          │                               │
          ▼                               ▼
 ┌────────────────┐              ┌────────────────┐
 │ Markdown Wiki  │◄────────────►│ Vector Store   │
 │  data/wiki/    │   hybrid     │    Qdrant      │
 └────────────────┘  retrieval   └────────────────┘
```

| Layer | Location | Role |
|-------|----------|------|
| **Markdown wiki** | `data/wiki/*.md` | Main persistent knowledge (human-readable) |
| **Vector store** | Qdrant `wiki_vectors` | Semantic search over document chunks |
| **BM25 search index** | `data/wiki/.search_index/` | Fast keyword ranking over wiki passages (Whoosh) |
| **Upload queue** | Streamlit session | Lets you review/remove files before ingest |

Wiki conventions: [`AGENTS.md`](AGENTS.md)

---

## Performance Optimizations

These changes keep Q&A responsive in production:

| Optimization | What it does | Impact |
|--------------|--------------|--------|
| **Groq for all LLM calls** | Ingest + Q&A use `llama-3.3-70b-versatile` | Q&A dropped from 60s+ to ~4s |
| **Parallel retrieval** | Wiki search and vector search run at the same time | Cuts retrieval latency roughly in half |
| **Embedding cache** | Repeated questions skip the embedding API call | Warm queries ~1s vs ~4s cold |
| **Wiki page cache** | Markdown pages loaded once, refreshed on edits | Faster keyword search as wiki grows |
| **BM25 wiki index** | Whoosh index rebuilt when pages change | Reliable keyword ranking; avoids scanning every page on each query |
| **Page-level sources** | UI groups passages by wiki page or upload file | Cleaner citations with `.md` paths |
| **Vector metadata** | Qdrant stores `wiki_page`, `source_file`, `chunk_index` | Upload chunks link back to wiki pages and filenames |
| **Upload queue** | Files are not ingested until you confirm | Prevents accidental processing |

### Scaling note: wiki search

Earlier versions scanned all wiki files on every question via `read_all_pages()` + keyword overlap. That approach gets **slow as the wiki grows** (many pages, many passages).

This project now uses a **BM25 index (Whoosh)** stored under `data/wiki/.search_index/`. The index rebuilds automatically when wiki pages are added, updated, or deleted.

| Wiki size | Recommended approach |
|-----------|---------------------|
| Small (under ~50 pages) | BM25 index (built-in) + in-memory page cache |
| Medium / many pages | Keep BM25; monitor index rebuild time on ingest |
| Multi-user production | BM25 + Qdrant hybrid RRF; consider Elasticsearch/OpenSearch for very large wikis |

For **multiple users in production**, do not rely on full filesystem scans per query — use the BM25 index (or an external search service) plus the existing Qdrant vector index.

---

## Project Structure

```text
llm_wiki/
├── AGENTS.md
├── README.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── setup_qdrant.py
├── scripts/
│   └── smoke_test.py         # Manual end-to-end check
├── frontend/
│   └── app.py                # Streamlit UI
├── backend/
│   ├── graph/
│   │   ├── langgraph_app.py  # Ingest + query workflows
│   │   └── retrieval.py      # Hybrid search (RRF, dedup, context)
│   └── services/
│       ├── document_loader.py
│       ├── embedding.py      # Embeddings + cache
│       ├── entity_extractor.py
│       ├── llm_service.py    # Groq chat API
│       ├── qdrant_service.py
│       ├── wiki_manager.py   # Wiki files + in-memory cache
│       └── wiki_index.py     # BM25 search index (Whoosh)
└── data/
    ├── raw/
    └── wiki/
        ├── index.md
        └── log.md
```

---

## Technical Deep Dive

### Ingest Workflow

| Step | What happens |
|------|----------------|
| **chunk** | Split text into 500-character pieces |
| **embed** | Create embeddings (OpenRouter, cached per text) |
| **summarize** | Groq writes a source summary |
| **entities** | Groq extracts key entities |
| **wiki** | Create source page, update index and log |
| **store_vectors** | Upsert chunks into Qdrant with `wiki_page`, `source_file`, `chunk_index` |
| **plan_maintenance** | Groq returns JSON plan for concept pages |
| **apply_maintenance** | Write/update maintained wiki pages |

### Query Workflow

| Step | What happens |
|------|----------------|
| **retrieve_all** | Parallel: BM25 wiki search + Qdrant vector search (min similarity filter) |
| **merge** | Reciprocal Rank Fusion, dedup, token budget (~2000 tokens) |
| **generate** | Groq answers strictly from retrieved evidence |

### Hybrid retrieval (internal vs UI)

| Layer | Behavior |
|-------|----------|
| **Internal retrieval** | Passage/chunk level hybrid RRF (wiki BM25 + Qdrant vectors) |
| **UI sources** | Grouped by wiki page title + `data/wiki/{page}.md` path, or `Upload: filename` |
| **snippet** | Collapsed under each source; passages/chunks retrieval used as LLM context |

Keyword search uses a **BM25 index** (Whoosh). Vector search uses Qdrant. RRF merges both ranked lists. The top passages become the LLM context.

Details: `backend/graph/retrieval.py`

---

## Setup (Local Development)

### Prerequisites

- Python 3.11+
- Groq API key
- OpenRouter API key (embeddings only)
- Qdrant instance (cloud or local)

### 1. Virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Environment file

Create `.env`:

```env
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_api_key
```

Optional:

```env
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

### 3. Initialize Qdrant

```powershell
python setup_qdrant.py
```

### 4. Run the app

```powershell
streamlit run frontend/app.py
```

Open: http://localhost:8501

---

## Run with Docker

```powershell
docker compose up --build
```

Open http://localhost:8501. The `data/` folder is mounted for persistence.

---

## Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROQ_API_KEY` | Yes | All LLM calls (ingest + Q&A) |
| `OPENROUTER_API_KEY` | Yes | Embeddings only |
| `QDRANT_URL` | Yes | Vector database endpoint |
| `QDRANT_API_KEY` | Depends on host | Qdrant authentication |
| `GROQ_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `OPENROUTER_EMBEDDING_MODEL` | No | Default: `openai/text-embedding-3-small` |

Never commit `.env` to git.

---

## Supported File Types

| Type | Notes |
|------|-------|
| `.txt` | Plain text |
| `.md` | Markdown |
| `.pdf` | Text-based PDFs via `pypdf` |

Scanned/image PDFs need OCR (not implemented).

---

## LLM Providers

| Task | Provider | Model |
|------|----------|-------|
| Summarize, entities, maintenance, Q&A | **Groq** | `llama-3.3-70b-versatile` |
| Embeddings | **OpenRouter** | `text-embedding-3-small` |

Groq handles all text generation because it is fast and reliable for multi-step pipelines. OpenRouter is kept only for embeddings (Groq does not offer an embedding API). Embedding results are cached in memory for repeated questions.

All API clients use a 120-second timeout.

---

## Managing Uploads and Wiki Pages

### Upload queue (before ingest)

- Files you select are added to a **queue** in the sidebar
- Each file has a **Remove** button — use this if you picked the wrong file
- **Clear queue** removes all pending files
- **Ingest Documents** only processes the queue

### Delete wiki pages (after ingest)

- Sidebar → **Manage Wiki Pages**
- Select a page → **Delete selected page**
- Removes the `.md` file and its entry from `index.md`
- Logs a `DELETE` event in `log.md`

Note: Deleting a wiki page removes its markdown file, index entry, BM25 index entries (on rebuild), and Qdrant vectors tagged with that `wiki_page`.

---

## Current Limitations

- Large documents may hit Groq rate/token limits
- No OCR for scanned PDFs
- Ingest runs synchronously in the UI (no background queue)
- No authentication or multi-user support
- Vector orphans may remain for legacy chunks ingested before metadata was added (re-ingest to fix)

---

## Deployment Checklist

- [ ] Store secrets in a vault, not in the Docker image
- [ ] Run Qdrant as a managed or dedicated service
- [ ] Persist `data/wiki/` to durable storage
- [ ] Add background worker for large-file ingest
- [ ] Add authentication in front of Streamlit
- [ ] Pin Qdrant client version to match server
- [ ] Add structured logging and health checks

---

## Smoke Test

After setup, verify ingest and Q&A:

```powershell
python scripts/smoke_test.py
```

Expected: ingest completes in ~15–30s, first query in ~3–5s, repeated query faster due to embedding cache.

---

## Summary

**Theory:** Build compounding knowledge as markdown, not throwaway chat context.

**Practice:** Upload → review queue → ingest writes wiki + vectors → ask questions → parallel hybrid retrieval → Groq answers from evidence only.

The system gets smarter as you feed it documents, while keeping human-readable files you fully control.
