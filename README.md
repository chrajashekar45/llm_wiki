# LLM Wiki Knowledge System

An experimental personal knowledge-base system where an LLM maintains a persistent markdown wiki from uploaded source files.

Instead of only doing traditional RAG over raw documents, this project tries to build a compounding wiki layer. Uploaded files are summarized, indexed, stored as source pages, and used to update related concept/entity/synthesis pages over time.

## What This Project Does

- Upload source files through a Streamlit UI.
- Extract text from `.txt`, `.md`, and `.pdf` files.
- Store document chunks as embeddings in Qdrant.
- Use an LLM to summarize uploaded sources.
- Extract entities and concepts.
- Create markdown wiki pages in `data/wiki/`.
- Maintain `index.md` and `log.md`.
- Search the accumulated wiki when answering questions.
- Keep ingestion and querying as separate workflows.

## Project Structure

```text
llm_wiki/
|-- AGENTS.md
|-- Dockerfile
|-- README.md
|-- docker-compose.yml
|-- requirements.txt
|-- setup_qdrant.py
|-- test.py
|-- backend/
|   |-- main.py
|   |-- graph/
|   |   `-- langgraph_app.py
|   `-- services/
|       |-- document_loader.py
|       |-- embedding.py
|       |-- entity_extractor.py
|       |-- llm_service.py
|       |-- qdrant_service.py
|       `-- wiki_manager.py
|-- data/
|   |-- raw/
|   `-- wiki/
|       |-- index.md
|       `-- log.md
`-- frontend/
    `-- app.py
```

## Architecture

The system has three main knowledge layers:

1. **Raw sources**
   - Uploaded documents.
   - Treated as source material.
   - Currently text is extracted and processed through the app.

2. **Vector store**
   - Qdrant stores embeddings for document chunks.
   - Used as supporting retrieval infrastructure.

3. **Markdown wiki**
   - Stored in `data/wiki/`.
   - The main persistent artifact.
   - Contains source summaries, concept pages, entity pages, open questions, contradictions, `index.md`, and `log.md`.

The operating conventions are documented in `AGENTS.md`.

## Workflows

### Ingest Workflow

When a file is uploaded:

1. Streamlit receives the file.
2. `document_loader.py` extracts text.
3. `langgraph_app.py` chunks the text.
4. `embedding.py` creates local embeddings.
5. `qdrant_service.py` stores chunks in Qdrant.
6. The LLM summarizes the uploaded source.
7. The LLM extracts entities/concepts.
8. A source summary page is created in `data/wiki/`.
9. The LLM plans wiki maintenance updates.
10. Concept/entity/synthesis pages are created or updated.
11. `index.md` and `log.md` are updated.

### Query Workflow

When a user asks a question:

1. The app searches existing markdown wiki pages.
2. If needed, it can use Qdrant vector search as supporting context.
3. Retrieved context is passed to the LLM.
4. The LLM answers only from the provided context.

Questions are not ingested as source pages.

## Supported Upload Formats

- `.txt`
- `.md`
- `.pdf`

PDF support uses `pypdf`, so it works best with PDFs that contain selectable text. Scanned image-only PDFs need OCR support, which is not implemented yet.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a `.env` file:

```env
GROQ_API_KEY=your_groq_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
QDRANT_URL=your_qdrant_url
QDRANT_API_KEY=your_qdrant_api_key
```

Initialize the Qdrant collection:

```powershell
python setup_qdrant.py
```

Run the Streamlit app:

```powershell
streamlit run frontend/app.py
```

## Docker

Docker , it shows how the app can be packaged.

Build and run the app with Docker Compose:

```powershell
docker compose up --build
```

Then open:

```text
http://localhost:8501
```

The Compose setup starts:

- `app`: the Streamlit application
- `qdrant`: a local Qdrant vector database

The `data/` directory is mounted into the container so generated wiki files persist on your machine.

If you use the Compose Qdrant service, set this in `.env` or rely on the Compose override:

```env
QDRANT_URL=http://qdrant:6333
```

For local non-Docker development, use your local or cloud Qdrant URL instead.

## Deployment Plan

Cloud deployment , yet to be done:

- Containerize the Streamlit app with the included `Dockerfile`.
- Run Qdrant as a managed service, a separate container, or a persistent VM service.
- Store uploaded raw files in object storage such as S3, Azure Blob Storage, or GCS.
- Store generated wiki files in a mounted volume, object storage, or a git-backed repository.
- Move long ingestion jobs into a background worker for large PDFs and rate-limit handling.
- Keep API keys in cloud secrets or environment variables, never in source control.

## LLM Providers

LLM calls are handled in `backend/services/llm_service.py`.

Currently configured clients:

- Groq, using OpenAI-compatible API
- OpenRouter, using OpenAI-compatible API

The default generation path uses Groq:

```python
call_groq(prompt, model="llama-3.3-70b-versatile")
```

## Token Limit Note

Large files can exceed the LLM provider's token or rate limits if the entire extracted text is sent in one request.

This project currently keeps the workflow simple, but production usage should add:

- chunked summarization
- prompt/context budgeting
- retry/backoff for rate limits
- background ingestion queue for large documents

## Current Limitations

- Large PDFs may hit Groq token-per-minute limits.
- Scanned PDFs are not supported.
- Wiki maintenance quality depends on the LLM response.
- Contradiction detection is basic and prompt-driven.
- There is no dedicated lint/health-check workflow yet.
- No authentication or multi-user support.
- `backend/main.py` is currently empty; the app is Streamlit-first.

## Scope for further improvemnts

- Adding a "Lint Wiki" workflow.
- Adding OCR for scanned PDFs.
- Adding chunked summarization for large files.
- Adding a "Save this answer to wiki" button.
- Improve entity/concept page linking.
- Adding source metadata and YAML frontmatter.
- Adding better search over markdown pages.
- Adding tests around wiki updates and duplicate page handling.

## Git Commit Do’s and Don’ts 

- Do not commit `.env`.
- Do not commit `venv/`.
- Consider committing `data/wiki/` if you want your generated wiki in version control.
- Consider committing only sample files under `data/` if the wiki contains private information.
