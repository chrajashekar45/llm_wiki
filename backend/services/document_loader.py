from pathlib import Path


SUPPORTED_EXTENSIONS = ("txt", "md", "pdf")


def extract_text_from_upload(uploaded_file):
    extension = Path(uploaded_file.name).suffix.lower().lstrip(".")

    if extension in {"txt", "md"}:
        return uploaded_file.read().decode("utf-8", errors="replace")

    if extension == "pdf":
        return extract_pdf_text(uploaded_file)

    supported = ", ".join(f".{item}" for item in SUPPORTED_EXTENSIONS)
    raise ValueError(f"Unsupported file type. Supported types: {supported}")


def extract_pdf_text(uploaded_file):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF support requires pypdf. Install it with: pip install pypdf"
        ) from exc

    reader = PdfReader(uploaded_file)
    pages = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"--- Page {index} ---\n{text.strip()}")

    content = "\n\n".join(pages).strip()

    if not content:
        raise ValueError("No extractable text found in this PDF.")

    return content









