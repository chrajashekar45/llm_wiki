import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

groq_client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY"),
    timeout=120.0,
)


def call_groq(prompt, model=None):
    model = model or GROQ_MODEL
    response = groq_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )

    if not response or not response.choices:
        raise RuntimeError("Groq returned no choices.")

    content = getattr(response.choices[0].message, "content", None)
    if not content:
        raise RuntimeError("Groq returned no content.")

    return content.strip()
