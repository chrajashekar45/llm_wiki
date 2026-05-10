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

uploaded_file = st.sidebar.file_uploader(
    "Upload a source file",
    type=list(SUPPORTED_EXTENSIONS),
)

if uploaded_file:
    if st.sidebar.button("Ingest Document"):
        try:
            content = extract_text_from_upload(uploaded_file)

            with st.spinner("Processing..."):
                result = ingest_graph.invoke({"input": content})

            st.sidebar.success("Document added to knowledge base!")
            st.sidebar.write(f"Created: `{result.get('title', 'wiki page')}`")

            touched_pages = (result.get("maintenance") or {}).get("touched_pages") or []
            if touched_pages:
                st.sidebar.write("Updated:")
                for page in touched_pages:
                    st.sidebar.write(f"- `{page}`")
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
