from backend.services.llm_service import call_groq

ENTITY_TEXT_LIMIT = 8000


def extract_entities(text):
    prompt = (
        "Extract key entities (topics, concepts, names) from the text.\n"
        "Return as a comma-separated list.\n\n"
        f"Text:\n{text[:ENTITY_TEXT_LIMIT]}"
    )
    response = call_groq(prompt)
    return [item.strip() for item in response.split(",") if item.strip()]
