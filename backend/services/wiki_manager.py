import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WIKI_PATH = PROJECT_ROOT / "data" / "wiki"
SPECIAL_FILES = {"index.md", "log.md"}


def ensure_wiki():
    WIKI_PATH.mkdir(parents=True, exist_ok=True)
    (WIKI_PATH / "index.md").touch(exist_ok=True)
    (WIKI_PATH / "log.md").touch(exist_ok=True)


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

    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    return filename


def read_page(title):
    ensure_wiki()
    filename = WIKI_PATH / f"{slugify(title)}.md"

    if not filename.exists():
        return ""

    return filename.read_text(encoding="utf-8")


def read_all_pages():
    ensure_wiki()
    pages = []

    for file in WIKI_PATH.glob("*.md"):
        if file.name not in SPECIAL_FILES:
            with open(file, "r", encoding="utf-8") as f:
                pages.append({"title": file.stem, "content": f.read()})

    return pages


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


def append_to_page(title, heading, content):
    ensure_wiki()
    slug = slugify(title)
    filename = WIKI_PATH / f"{slug}.md"
    clean_content = content.strip()

    if filename.exists():
        existing = filename.read_text(encoding="utf-8").rstrip()
        updated = f"{existing}\n\n## {heading}\n{clean_content}\n"
    else:
        updated = f"# {slug}\n\n## {heading}\n{clean_content}\n"

    filename.write_text(updated, encoding="utf-8")
    return filename


def upsert_maintained_page(title, content, summary, category="concepts"):
    slug = slugify(title)
    save_page(slug, content, overwrite=True)
    update_index(slug, summary, category=category, replace=True)
    return slug


def log_event(event_type, message):
    ensure_wiki()
    log_file = WIKI_PATH / "log.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"## [{timestamp}] {event_type}\n{message}\n\n"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(entry)


def search_wiki(query, limit=5):
    pages = read_all_pages()
    results = []
    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))

    if not query_words:
        return []

    for page in pages:
        page_words = set(re.findall(r"[a-z0-9]+", page["content"].lower()))
        title_words = set(re.findall(r"[a-z0-9]+", page["title"].lower()))
        score = len(query_words & page_words) + (2 * len(query_words & title_words))

        if score > 0:
            results.append((score, page))

    results = sorted(results, key=lambda x: x[0], reverse=True)

    return [
        f"Source page: {result['title']}\n\n{result['content']}"
        for _, result in results[:limit]
    ]


def get_wiki_overview(max_chars=12000):
    pages = read_all_pages()
    sections = []

    for page in pages:
        content = page["content"].strip()
        if len(content) > 1500:
            content = content[:1500] + "\n..."
        sections.append(f"Page: {page['title']}\n{content}")

    overview = "\n\n---\n\n".join(sections)
    return overview[:max_chars]
