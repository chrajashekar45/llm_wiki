import io
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.graph.langgraph_app import ingest_graph, query_graph
from backend.graph.retrieval import format_sources_for_display
from backend.services.document_loader import SUPPORTED_EXTENSIONS, extract_text_from_upload
from backend.services.wiki_manager import delete_page, list_page_titles

PROJECT_ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="LLM Wiki System", layout="wide")

if "upload_queue" not in st.session_state:
    st.session_state.upload_queue = []


def _queue_key(name, size):
    return f"{name}:{size}"


def _add_files_to_queue(uploaded_files):
    for uploaded_file in uploaded_files:
        data = uploaded_file.getvalue()
        key = _queue_key(uploaded_file.name, len(data))
        if any(item["key"] == key for item in st.session_state.upload_queue):
            continue
        st.session_state.upload_queue.append(
            {
                "key": key,
                "name": uploaded_file.name,
                "data": data,
            }
        )


def _make_upload_file(item):
    buffer = io.BytesIO(item["data"])
    buffer.name = item["name"]
    return buffer


def _wiki_file_link(relative_path):
    absolute = PROJECT_ROOT / relative_path
    if absolute.exists():
        return f"`{relative_path}`"
    return relative_path


st.title("LLM Wiki Knowledge System")

# ---------------- FILE UPLOAD ---------------- #
st.sidebar.header("Upload Documents")

new_uploads = st.sidebar.file_uploader(
    "Choose files to add to the queue",
    type=list(SUPPORTED_EXTENSIONS),
    accept_multiple_files=True,
)

if new_uploads:
    _add_files_to_queue(new_uploads)

if st.session_state.upload_queue:
    st.sidebar.subheader("Files ready to ingest")
    for index, item in enumerate(st.session_state.upload_queue):
        col_name, col_remove = st.sidebar.columns([4, 1])
        col_name.write(f"- {item['name']}")
        if col_remove.button("Remove", key=f"remove_upload_{item['key']}"):
            st.session_state.upload_queue.pop(index)
            st.rerun()

    col_ingest, col_clear = st.sidebar.columns(2)
    if col_ingest.button("Ingest Documents", type="primary"):
        try:
            results = []
            for item in st.session_state.upload_queue:
                uploaded_file = _make_upload_file(item)
                content = extract_text_from_upload(uploaded_file)
                with st.spinner(f"Processing {item['name']}..."):
                    result = ingest_graph.invoke(
                        {"input": content, "source_file": item["name"]}
                    )
                results.append((item["name"], result))

            st.session_state.upload_queue = []
            st.sidebar.success(f"Processed {len(results)} document(s)!")
            for filename, result in results:
                st.sidebar.write(f"- {filename}: {result.get('title', 'wiki page')}")
        except Exception as exc:
            st.sidebar.error(str(exc))

    if col_clear.button("Clear queue"):
        st.session_state.upload_queue = []
        st.rerun()

# ---------------- MANAGE WIKI PAGES ---------------- #
st.sidebar.header("Manage Wiki Pages")

wiki_titles = list_page_titles()
if wiki_titles:
    page_to_delete = st.sidebar.selectbox("Select a wiki page to delete", wiki_titles)
    if st.sidebar.button("Delete selected page"):
        try:
            deleted = delete_page(page_to_delete)
            st.sidebar.success(f"Deleted wiki page: {deleted}")
            st.rerun()
        except Exception as exc:
            st.sidebar.error(str(exc))
else:
    st.sidebar.caption("No wiki pages yet.")

# ---------------- QUERY SECTION ---------------- #
st.header("Ask a Question")

query = st.text_input("Enter your question:")

if st.button("Get Answer"):
    if query:
        with st.spinner("Thinking..."):
            result = query_graph.invoke({"input": query})

        st.subheader("Answer")
        st.write(result["answer"])

        sources = format_sources_for_display(result.get("hybrid_results") or [])
        if sources:
            st.subheader("Sources")
            for source in sources:
                if source["kind"] == "wiki" and source.get("page_path"):
                    st.markdown(f"**{source['title']}**")
                    st.caption(_wiki_file_link(source["page_path"]))
                else:
                    st.markdown(f"**{source['title']}**")
                    if source.get("source_file"):
                        st.caption(f"From upload: `{source['source_file']}`")

                for index, snippet in enumerate(source["snippets"], start=1):
                    label = "snippet" if len(source["snippets"]) == 1 else f"snippet {index}"
                    with st.expander(label, expanded=False):
                        st.write(snippet)
    else:
        st.warning("Please enter a question")
