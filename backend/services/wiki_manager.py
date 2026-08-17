import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WIKI_PATH = PROJECT_ROOT / "data" / "wiki"
SPECIAL_FILES = {"index.md", "log.md"}
WORD_PATTERN = re.compile(r"[a-z0-9]+")

_pages_cache = None
_pages_cache_signature = None


def ensure_wiki():
    WIKI_PATH.mkdir(parents=True, exist_ok=True)
    (WIKI_PATH / "index.md").touch(exist_ok=True)
    (WIKI_PATH / "log.md").touch(exist_ok=True)


def invalidate_pages_cache():
    global _pages_cache, _pages_cache_signature
    _pages_cache = None
    _pages_cache_signature = None
    from backend.services.wiki_index import invalidate_index

    invalidate_index()


def _wiki_signature():
    ensure_wiki()
    mtimes = []
    for file in WIKI_PATH.glob("*.md"):
        if file.name not in SPECIAL_FILES:
            mtimes.append((file.name, file.stat().st_mtime))
    return tuple(sorted(mtimes))


def slugify(title, fallback="untitled"):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()
    return slug[:80] or fallback


def unique_slug(title):
    ensure_wiki()
    base_slug = slugify(title)
    candidate = base_slug
    counter = 2
    while (WIKI_PATH / f"{candidate}.md").exists():
        candidate = f"{base_slug}_{counter}"
        counter += 1
    return candidate


def save_page(title, content, overwrite=False):
    ensure_wiki()
    page_slug = slugify(title) if overwrite else unique_slug(title)
    filename = WIKI_PATH / f"{page_slug}.md"
    filename.write_text(content, encoding="utf-8")
    invalidate_pages_cache()
    return filename


def read_all_pages():
    global _pages_cache, _pages_cache_signature

    signature = _wiki_signature()
    if _pages_cache is not None and _pages_cache_signature == signature:
        return _pages_cache

    pages = []
    for file in WIKI_PATH.glob("*.md"):
        if file.name not in SPECIAL_FILES:
            pages.append({"title": file.stem, "content": file.read_text(encoding="utf-8")})

    _pages_cache = pages
    _pages_cache_signature = signature
    return pages


def list_page_titles():
    return [page["title"] for page in read_all_pages()]


def get_page_relative_path(title):
    return f"data/wiki/{slugify(title)}.md"


def delete_page(title):
    ensure_wiki()
    slug = slugify(title)
    page_path = WIKI_PATH / f"{slug}.md"

    if not page_path.exists():
        raise FileNotFoundError(f"Wiki page not found: {slug}")

    page_path.unlink()

    index_file = WIKI_PATH / "index.md"
    if index_file.exists():
        lines = index_file.read_text(encoding="utf-8").splitlines(keepends=True)
        lines = [line for line in lines if f"](./{slug}.md)" not in line]
        index_file.write_text("".join(lines), encoding="utf-8")

    from backend.services.qdrant_service import delete_vectors_for_wiki_page

    delete_vectors_for_wiki_page(slug)
    invalidate_pages_cache()
    log_event("DELETE", f"Removed page: {slug}")
    return slug


def update_index(title, summary, category="sources", replace=False):
    ensure_wiki()
    index_file = WIKI_PATH / "index.md"
    slug = slugify(title)
    safe_summary = " ".join(summary.split())
    entry = f"- [{slug}](./{slug}.md): {safe_summary}\n"

    existing = index_file.read_text(encoding="utf-8").splitlines(keepends=True)
    if replace:
        existing = [line for line in existing if f"]({f'./{slug}.md'})" not in line]

    if not existing:
        existing = ["# Wiki Index\n\n", f"## {category.title()}\n"]
    elif not any(line.strip() == f"## {category.title()}" for line in existing):
        if existing[-1].strip():
            existing.append("\n")
        existing.append(f"## {category.title()}\n")

    existing.append(entry)
    index_file.write_text("".join(existing), encoding="utf-8")


def upsert_maintained_page(title, content, summary, category="concepts"):
    slug = slugify(title)
    save_page(slug, content, overwrite=True)
    update_index(slug, summary, category=category, replace=True)
    return slug


def log_event(event_type, message):
    ensure_wiki()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"## [{timestamp}] {event_type}\n{message}\n\n"
    with open(WIKI_PATH / "log.md", "a", encoding="utf-8") as log_file:
        log_file.write(entry)


def _words(text):
    return set(WORD_PATTERN.findall(text.lower()))


def _split_passages(content, passage_chars=900):
    sections = re.split(r"\n(?=#{1,6}\s)", content)
    passages = []

    for section in sections:
        section = section.strip()
        if not section:
            continue

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]
        if not paragraphs:
            paragraphs = [section]

        for paragraph in paragraphs:
            for start in range(0, len(paragraph), passage_chars):
                chunk = paragraph[start : start + passage_chars].strip()
                if chunk:
                    passages.append(chunk)

    return passages


def search_wiki(query, limit=5):
    return [
        f"Source page: {hit['title']}\n\n{hit['text']}"
        for hit in search_wiki_hits(query, limit)
    ]


def search_wiki_hits(query, limit=5, passage_chars=900):
    from backend.services.wiki_index import search_wiki_bm25

    return search_wiki_bm25(query, limit=limit)


def get_wiki_overview(max_chars=12000):
    sections = []
    for page in read_all_pages():
        content = page["content"].strip()
        if len(content) > 1500:
            content = content[:1500] + "\n..."
        sections.append(f"Page: {page['title']}\n{content}")
    return "\n\n---\n\n".join(sections)[:max_chars]
