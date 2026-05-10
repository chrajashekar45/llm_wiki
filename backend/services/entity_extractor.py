from backend.services.llm_service import call_groq


def extract_entities(text):
    prompt = f"""
Extract key entities (topics, concepts, names) from the text.
Return as a comma-separated list.

Text:
{text}
"""

    response = call_groq(prompt)

    entities = [e.strip() for e in response.split(",") if e.strip()]

    return entities
