# LLM Wiki Knowledge System

**A personal knowledge-base application that transforms uploaded documents into a living markdown wiki and enables intelligent question-answering against your curated knowledge.**

Build compounding knowledge as persistent, human-readable markdown files—not throwaway chat context.

---

##  Vision

Most AI chatbots answer from general training data. **LLM Wiki is different:**

- **Upload documents** → system creates organized wiki pages
- **Questions are answered** → using only information from your wiki
- **Knowledge compounds over time** → as you feed more documents
- **You own your data** → all knowledge lives in `data/wiki/` as readable `.md` files

The system learns from your documents and gets smarter, while staying grounded in evidence.

---

##  Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
  - [Upload Workflow](#upload-workflow)
  - [Query Workflow](#query-workflow)
  - [Delete Workflow](#delete-workflow)
- [Architecture](#architecture)
- [Performance](#performance)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Docker Deployment](#docker-deployment)
- [Supported File Types](#supported-file-types)
- [LLM & Embedding Providers](#llm--embedding-providers)
- [Managing Your Wiki](#managing-your-wiki)
- [Technical Deep Dive](#technical-deep-dive)
- [Limitations & Roadmap](#limitations--roadmap)
- [Deployment Checklist](#deployment-checklist)

---

##  Quick Start

### Local Development (3 minutes)

```powershell
# 1. Clone and setup
git clone https://github.com/chrajashekar45/llm_wiki.git
cd llm_wiki
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configure environment
# Create .env file with your API keys (see Environment Variables section)
copy .env.example .env
# Edit .env with your keys

# 3. Run locally
streamlit run frontend/app.py
```

Open **http://localhost:8501**

### Docker (1 command)

```powershell
docker compose up --build
```

Open **http://localhost:8501**

---

##  How It Works

### Upload Workflow

```
User selects files
    ↓
Files added to queue
    ↓
User clicks "Ingest Documents"
    ↓
Pipeline runs:
┌─────────────────────────────────────────────────┐
│ chunk → embed → summarize → entities → wiki    │
│   ↓        ↓        ↓          ↓       ↓        │
│  500ch   embeddings Groq     Groq   markdown   │
│         cached    summary    extract  file     │
│                                                  │
│ store_vectors → plan_maintenance → apply       │
│   Qdrant        (LLM decides      maintenance  │
│   w/ metadata   what to update)    (write/     │
│                                    update)      │
└─────────────────────────────────────────────────┘
    ↓
Wiki updated, vectors stored, concepts linked
```

**What happens:**
1. **Chunk** — split text into 500-character pieces for granular retrieval
2. **Embed** — create embeddings with caching (avoid API calls on re-ingests)
3. **Summarize** — Groq writes a concise, reusable summary
4. **Extract** — Groq identifies key entities (people, concepts, projects)
5. **Create source page** — markdown file with summary + entities + related wiki context
6. **Store vectors** — upload all chunks to Qdrant with metadata (wiki_page, source_file, chunk_index)
7. **Plan maintenance** — Groq analyzes summary and returns JSON: pages to create/update, contradictions, open questions
8. **Apply maintenance** — write/update concept pages, maintain a "contradictions" page, track open questions

### Query Workflow

```
User asks a question
    ↓
Parallel retrieval (runs simultaneously):
┌────────────────────────────────────────┐
│ Wiki search (BM25)  │  Vector search   │
│ (Whoosh index)      │  (Qdrant)        │
│ Keyword ranking     │  Semantic match  │
│ Fast & reliable     │  Captures intent │
└────────────────────────────────────────┘
    ↓
Merge results (Reciprocal Rank Fusion)
    ↓
Deduplicate passages
    ↓
Build LLM context (~2000 tokens max)
    ↓
Groq generates answer (from evidence only)
    ↓
Results grouped by wiki page or upload file
```

**What you see:**
- **Answer** — clean prose at the top (no citations in the answer itself)
- **Sources** — grouped by wiki page (with `.md` path) or upload filename
- **Snippets** — expandable passages showing which text was used internally

### Delete Workflow

1. Sidebar → **Manage Wiki Pages**
2. Select a page → **Delete selected page**
3. System removes:
   - The `.md` file
   - Entry from `index.md`
   - All Qdrant vectors tagged with that `wiki_page`
   - Logs a `DELETE` event in `log.md`

---

##  Architecture

### System Diagram

```
┌──────────────────────────────────────────────────────────┐
│                    Streamlit UI                          │
│  Upload queue · Review files · Ingest · Delete · Q&A     │
└──────────────────────┬───────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ↓                         ↓
    ┌──────────────┐        ┌──────────────┐
    │ Ingest Graph │        │ Query Graph  │
    │  (LangGraph) │        │ (LangGraph)  │
    └──────┬───────┘        └──────┬───────┘
           │                        │
           ↓                        ↓
    ┌────────────────┐     ┌────────────────┐
    │ Markdown Wiki  │←───→│ Vector Store   │
    │  data/wiki/    │     │ Qdrant (RRF)   │
    ├────────────────┤     └────────────────┘
    │ index.md       │
    │ log.md         │     ┌────────────────┐
    │ *.md (sources) │     │ BM25 Search    │
    │ entity/concept │     │ Whoosh Index   │
    │ syntheses      │     │ data/wiki/     │
    │ contradictions │     │ .search_index/ │
    └────────────────┘     └────────────────┘
```

### Storage Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| **Markdown Wiki** | `data/wiki/*.md` | Primary knowledge store (human-readable) |
| **Vector Store** | Qdrant `wiki_vectors` collection | Semantic search over all document chunks |
| **Search Index** | `data/wiki/.search_index/` | BM25 keyword ranking (Whoosh) for wiki passages |
| **Upload Queue** | Streamlit session state | Lets you review/remove files before ingest |
| **Event Log** | `data/wiki/log.md` | Audit trail of all ingests, updates, deletes |

---

##  Performance

### Key Optimizations

| Optimization | Impact | How |
|--------------|--------|-----|
| **Groq for all LLM** | Q&A: 60s+ → ~4s | Uses `llama-3.3-70b-versatile` (fast inference) |
| **Parallel retrieval** | Retrieval latency cut ~50% | Wiki search + vector search run simultaneously |
| **Embedding cache** | Warm queries: ~1s vs ~4s cold | Cached embeddings skip OpenRouter API |
| **Wiki page cache** | Faster keyword search as wiki grows | In-memory markdown pages, refreshed on edits |
| **BM25 index** | Scales to many pages | Whoosh index rebuilt on page change, not rescanned |
| **Page-level sources** | Cleaner citations | Results grouped by wiki page, not individual chunks |
| **Qdrant metadata** | Fast filtering | `wiki_page`, `source_file`, `chunk_index` enable targeted deletes |
| **Upload queue** | Prevents accidents | Files reviewed before processing |

### Scaling Notes

| Wiki Size | Recommended Approach |
|-----------|---------------------|
| **Small** (~50 pages) | BM25 index + in-memory cache (built-in) |
| **Medium** (many pages) | Keep BM25; monitor index rebuild time on ingest |
| **Large / Multi-user** | BM25 + Qdrant + consider Elasticsearch for very large wikis |

As your wiki grows:
- **BM25 index** keeps keyword search fast (does not scan all files per query)
- **Page cache** avoids re-reading markdown on every question
- **Parallel retrieval** means wiki + vector search latency stays constant

For **production with multiple users**, do not rely on full filesystem scans. Use the BM25 index + Qdrant hybrid search (already built in).

---

##  Setup

### Prerequisites

- **Python 3.11+**
- **API Keys:**
  - Groq API key (free tier available)
  - OpenRouter API key (for embeddings)
- **Qdrant instance** (cloud or local Docker)

### Step 1: Clone & Install

```powershell
git clone https://github.com/chrajashekar45/llm_wiki.git
cd llm_wiki
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 2: Create Environment File

Create `.env` in the project root:

```env
# Required
GROQ_API_KEY=your_groq_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_qdrant_key_or_leave_empty_for_local

# Optional (defaults shown)
GROQ_MODEL=llama-3.3-70b-versatile
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
```

**Get API Keys:**
- [Groq Console](https://console.groq.com) — free tier
- [OpenRouter](https://openrouter.ai) — supports many embedding models
- [Qdrant Cloud](https://cloud.qdrant.io) — free tier includes one collection

### Step 3: Initialize Qdrant

**Option A: Local Docker**
```powershell
docker run -p 6333:6333 qdrant/qdrant:latest
```

**Option B: Use Qdrant Cloud**
- Skip this step; use `QDRANT_URL` and `QDRANT_API_KEY` from your cloud dashboard

### Step 4: Run the Application

```powershell
streamlit run frontend/app.py
```

Open **http://localhost:8501**

---

##  Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `GROQ_API_KEY` | ✅ Yes | — | All LLM calls (ingest, summarize, Q&A) |
| `OPENROUTER_API_KEY` | ✅ Yes | — | Embeddings (Groq does not offer embedding API) |
| `QDRANT_URL` | ✅ Yes | — | Qdrant vector database endpoint |
| `QDRANT_API_KEY` | Depends* | — | Qdrant API key (required if using cloud) |
| `GROQ_MODEL` | ❌ No | `llama-3.3-70b-versatile` | LLM model for all text generation |
| `OPENROUTER_EMBEDDING_MODEL` | ❌ No | `openai/text-embedding-3-small` | Embedding model |

*Local Qdrant does not require a key; cloud does.

**Never commit `.env` to git.** Add `.env` to `.gitignore`.

---

##  Docker Deployment

### Quick Start

```powershell
docker compose up --build
```

This starts:
- **App container** — Streamlit on port 8501
- **Qdrant container** — Vector database on port 6333

The `data/` folder persists across restarts.

### Production Tips

```yaml
# docker-compose.yml example
services:
  app:
    build: .
    ports:
      - "8501:8501"
    env_file:
      - .env
    volumes:
      - ./data:/app/data
    restart: unless-stopped

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./qdrant_storage:/qdrant/storage
    restart: unless-stopped
```

**See [Deployment Checklist](#deployment-checklist) for production hardening.**

---

##  Supported File Types

| Format | Status | Notes |
|--------|--------|-------|
| `.txt` | ✅ Supported | Plain text |
| `.md` | ✅ Supported | Markdown |
| `.pdf` | ✅ Supported | Text-based PDFs (via `pypdf`) |
| `.pdf` (scanned) | ❌ Not supported | Requires OCR (not implemented) |

To add more formats, extend `backend/services/document_loader.py`.

---

##  LLM & Embedding Providers

### LLM Provider: Groq

**Used for:** All text generation (ingest, Q&A)

**Model:** `llama-3.3-70b-versatile`

**Why Groq?**
- Extremely fast inference (sub-second for most calls)
- Reliable for multi-step pipelines (ingest graph runs reliably)
- No hallucination filter blocking legitimate use cases
- Free tier available

**Timeout:** 120 seconds per API call

### Embedding Provider: OpenRouter

**Used for:** Vector embeddings only

**Model:** `openai/text-embedding-3-small`

**Why separate from Groq?**
- Groq does not offer an embedding API
- OpenRouter provides a unified interface to many embedding models
- Embeddings are cached per text chunk (no repeated API calls on re-ingest)

**Timeout:** 120 seconds per API call

---

##  Managing Your Wiki

### Upload Documents

1. **Sidebar** → **Upload Documents**
2. Choose one or more files (`.txt`, `.md`, `.pdf`)
3. Files appear in the **Files ready to ingest** section
4. **Remove** any accidental uploads
5. Click **Ingest Documents** to process the queue

**What happens:**
- Each file is chunked, embedded, summarized
- A source page is created in `data/wiki/`
- Related concept pages are created or updated
- All chunks are stored in Qdrant with metadata

### Ask Questions

1. **Main area** → **Ask a Question**
2. Type your question
3. Click **Get Answer**
4. Results show:
   - **Answer** — clean prose from evidence
   - **Sources** — grouped by wiki page or upload file
   - **Snippets** — expandable passages used in retrieval

### Delete Wiki Pages

1. **Sidebar** → **Manage Wiki Pages**
2. Select a page from the dropdown
3. Click **Delete selected page**

**Removed:**
- The markdown file
- Index entry
- All related Qdrant vectors
- Event logged in `log.md`

### Review Wiki Events

The `data/wiki/log.md` file records all activity:

```markdown
## [2026-08-17 14:30] INGEST
Created page: python_basics

## [2026-08-17 14:35] MAINTAIN
Updated pages: functions, variables

## [2026-08-17 14:40] DELETE
Removed page: old_notes
```

---

##  Technical Deep Dive

### Project Structure

```
llm_wiki/
├── README.md                    # This file
├── AGENTS.md                    # LLM-facing operating schema
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Container image definition
├── docker-compose.yml           # Docker orchestration
│
├── frontend/
│   └── app.py                   # Streamlit UI (upload, query, delete)
│
├── backend/
│   ├── graph/
│   │   ├── langgraph_app.py     # LangGraph: ingest + query workflows
│   │   └── retrieval.py         # Hybrid search: RRF, dedup, context building
│   │
│   └── services/
│       ├── document_loader.py   # Extract text from PDF, TXT, MD
│       ├── embedding.py         # OpenRouter embeddings + caching
│       ├── entity_extractor.py  # Extract entities using Groq
│       ├── llm_service.py       # Groq API client
│       ├── qdrant_service.py    # Qdrant vector storage + search
│       ├── wiki_manager.py      # Markdown file + index management
│       └── wiki_index.py        # BM25 search index (Whoosh)
│
└── data/
    ├── raw/                     # Source documents (immutable)
    └── wiki/
        ├── index.md             # Central index (all pages + summaries)
        ├── log.md               # Event audit trail
        ├── .search_index/       # BM25 Whoosh index
        └── *.md                 # Wiki pages (sources, entities, concepts)
```

### Ingest Pipeline

| Step | Function | Input | Output | Purpose |
|------|----------|-------|--------|---------|
| **chunk** | `chunk_text()` | Document text | List[str] | 500-char chunks for retrieval granularity |
| **embed** | `embed()` | Chunks | List[vector] | OpenRouter embeddings (cached) |
| **summarize** | `summarize()` | Full text | Summary string | Groq writes concise wiki summary |
| **entities** | `extract_entities_node()` | Text | List[str] | Groq extracts key concepts/people |
| **wiki** | `create_wiki()` | Summary + entities | Markdown page | Source summary page written to disk |
| **store_vectors** | `store_vectors()` | Chunks + embeddings | (Qdrant) | Upload to Qdrant with metadata |
| **plan_maintenance** | `plan_maintenance()` | Summary + entities + wiki overview | JSON plan | Groq decides: create/update pages, contradictions? |
| **apply_maintenance** | `apply_maintenance()` | JSON plan | (Qdrant + wiki files) | Write concept pages, maintain syntheses |

### Query Pipeline

| Step | Function | Input | Output | Purpose |
|------|----------|-------|--------|---------|
| **retrieve_all** | `retrieve_all()` | Question | wiki_results, retrieved | Parallel: BM25 wiki search + Qdrant vector search |
| **merge** | `merge_context()` | Both result sets | hybrid_results, context | RRF rank fusion, dedup, build prompt context |
| **generate** | `generate_answer()` | Question + context | Answer string | Groq generates evidence-based answer |

### Hybrid Retrieval (Internal)

**Wiki Search (BM25):**
- Whoosh keyword index over all wiki passages
- Fast, reliable keyword ranking
- Handles synonym expansion via query normalization
- Stops on common words (a, the, is, etc.)

**Vector Search (Qdrant):**
- Semantic embedding similarity
- Captures intent and paraphrase
- Similarity threshold filter (avoids low-match noise)
- Includes upload chunk metadata

**Merging (Reciprocal Rank Fusion):**
- Combines ranked lists without assuming one is better
- Formula: `score = 1 / (k + rank)` for each source
- Deduplicates by normalized text
- Respects token budget (~2000 tokens for LLM context)

**Result Format:**
```python
{
    "text": "passage content",
    "wiki_page": "concept_name",      # for wiki pages
    "source_file": "upload.pdf",      # for uploads
    "chunk_index": 5,                 # chunk number
    "rrf_score": 0.045,               # fused rank score
    "sources": ["wiki", "vector"],    # which retrieved it
}
```

### Wiki Conventions

See `AGENTS.md` for LLM-facing conventions:

- Source pages are append-only historical summaries
- Entity/concept/synthesis pages are living documents
- Use stable internal links: `[topic](./topic.md)`
- Record contradictions explicitly
- Keep summaries concise and factual

---

##  Limitations & Roadmap

### Current Limitations

- **Large documents** — may hit Groq rate limits or token limits (split into smaller files)
- **Scanned PDFs** — OCR not implemented (text-based PDFs work fine)
- **Synchronous ingest** — UI blocks while processing (no background queue)
- **No authentication** — not suitable for multi-user production without added auth layer
- **Vector orphans** — legacy chunks ingested before metadata support may not delete cleanly (re-ingest to fix)

### Future Improvements

- [ ] Background worker queue for large file ingest
- [ ] OCR support for scanned PDFs
- [ ] User authentication + multi-user support
- [ ] Advanced search syntax (AND, OR, NOT)
- [ ] Scheduled automatic document refresh
- [ ] Integration with external knowledge bases
- [ ] Undo/restore deleted wiki pages
- [ ] Streaming answers (for long generations)

---

##  Deployment Checklist

Before going from prototype deploying to production, ensure:

- [ ] **Secrets management** — store API keys in a vault (AWS Secrets Manager, etc.), not in Docker image
- [ ] **Qdrant backend** — run as managed service (Qdrant Cloud) or dedicated container, not in-process
- [ ] **Data persistence** — mount `data/wiki/` to durable storage (S3, persistent volume, etc.)
- [ ] **Authentication** — add OAuth2 or reverse proxy (nginx with auth) in front of Streamlit
- [ ] **Rate limiting** — add per-user or per-IP rate limits at API gateway
- [ ] **Logging** — structured logging (JSON) to centralized service (ELK, CloudWatch, etc.)
- [ ] **Monitoring** — health checks, error tracking (Sentry, New Relic), uptime monitoring
- [ ] **Qdrant versioning** — pin client version to match server version
- [ ] **Resource limits** — CPU, memory limits for containers
- [ ] **Input validation** — sanitize all user inputs before processing
- [ ] **Timeouts** — all API calls have 120s timeout; consider async/await for UI responsiveness

---



##  Architecture & Design Decisions

### Why LangGraph?

- Modular, composable workflows
- Clear state management
- Easy to add/remove steps or branches
- Good for multi-step LLM pipelines
- Plays well with Groq + OpenRouter async calls

### Why Whoosh (BM25)?

- Local, no external dependency (except filesystem)
- Fast keyword search at wiki scale
- Index rebuilds incrementally on page change
- Avoids scanning all files on every query

### Why Qdrant?

- Lightweight vector database (can run locally or cloud)
- Metadata filtering (filter by `wiki_page`, `source_file`)
- REST API (easy to work with from Python)
- Good performance for retrieval-augmented workflows

### Why Groq?

- Sub-second latency for LLM calls
- Reliable for multi-step pipelines (ingest graph runs smoothly)
- No hallucination filters blocking legitimate use
- Free tier

---

##  Example Use Cases

1. **Research Project** — upload papers, articles, notes → system creates concept map, tracks contradictions
2. **Personal Learning** — upload course notes, textbooks → system creates entity index, enables fast recall
3. **Documentation** — upload internal docs, RFCs, ADRs → system maintains a searchable knowledge base
4. **News Aggregation** — upload daily news → system tracks entities, open questions, contradictions across time

---



