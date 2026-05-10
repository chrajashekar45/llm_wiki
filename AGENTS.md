# LLM Wiki Operating Schema

This project maintains a personal knowledge wiki from source documents.

## Layers

- `data/raw/` contains source material. Treat sources as immutable.
- `data/wiki/` contains generated markdown pages. The LLM may create and update these files.
- `AGENTS.md` documents the conventions for future maintenance.

## Ingest Workflow

When a new source is ingested:

1. Read the source as source-of-truth material.
2. Create a concise source summary page with a descriptive slug.
3. Extract important entities and concepts.
4. Search/read relevant existing wiki pages.
5. Create or update entity, concept, contradiction, open-question, and synthesis pages touched by the new source.
6. Update `data/wiki/index.md` with links and one-line summaries for changed pages.
7. Append `INGEST` and `MAINTAIN` entries to `data/wiki/log.md`.

## Query Workflow

When answering a question:

1. Search the wiki first.
2. Use vector retrieval only as supporting context.
3. Answer only from retrieved wiki/context material.
4. If the answer is not present, say that the wiki does not contain enough information.
5. Do not create source pages from questions.

## Page Conventions

- Use markdown.
- Prefer stable internal links such as `[topic](./topic.md)`.
- Keep summaries concise and factual.
- Record contradictions or uncertainty explicitly instead of smoothing them away.
- Source pages should usually be append-only historical summaries.
- Entity, concept, contradiction, open-question, and synthesis pages are maintained living pages.
