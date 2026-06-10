import os
import sys

import streamlit as st

# Fix import path when Streamlit runs from the frontend directory.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.graph.langgraph_app import ingest_graph, query_graph
from backend.services.document_loader import SUPPORTED_EXTENSIONS, extract_text_from_upload

st.set_page_config(page_title="LLM Wiki System", layout="wide")

st.title("LLM Wiki Knowledge System")

# ---------------- FILE UPLOAD ---------------- #
st.sidebar.header("Upload Document")

uploaded_files = st.sidebar.file_uploader(
    "Upload source files",
    type=list(SUPPORTED_EXTENSIONS),
    accept_multiple_files=True,
)

if uploaded_files:
    if st.sidebar.button("Ingest Documents"):
        try:
            results = []
            for uploaded_file in uploaded_files:
                content = extract_text_from_upload(uploaded_file)

                with st.spinner(f"Processing {uploaded_file.name}..."):
                    result = ingest_graph.invoke({"input": content})
                results.append((uploaded_file.name, result))

            st.sidebar.success(f"Processed {len(results)} document(s)!")
            for filename, result in results:
                qdrant_stored = (result.get("maintenance") or {}).get("qdrant_stored", True)
                status_text = "stored in vector store" if qdrant_stored else "processed without vector store"
                st.sidebar.write(f"- {filename}: {result.get('title', 'wiki page')} ({status_text})")
        except Exception as exc:
            st.sidebar.error(str(exc))

# ---------------- QUERY SECTION ---------------- #
st.header("Ask a Question")

query = st.text_input("Enter your question:")

if st.button("Get Answer"):
    if query:
        with st.spinner("Thinking..."):
            result = query_graph.invoke({"input": query})

        st.subheader("Answer:")
        st.write(result["answer"])
    else:
        st.warning("Please enter a question")
