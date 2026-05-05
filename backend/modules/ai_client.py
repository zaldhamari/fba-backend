"""
Shared OpenAI client. Falls back gracefully if no API key is set.
Use gpt-4o-mini everywhere — fast and cheap (~$0.15/1M input tokens).
"""
import os
import json
from typing import Any

try:
    from openai import OpenAI
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    AI_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))
except Exception:
    _client = None
    AI_AVAILABLE = False

MODEL = "gpt-4o-mini"


def chat(system: str, user: str, max_tokens: int = 800) -> str:
    """Send a chat completion and return the text response."""
    if not AI_AVAILABLE or _client is None:
        raise RuntimeError("OPENAI_API_KEY not set")
    resp = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def chat_json(system: str, user: str, max_tokens: int = 800) -> Any:
    """Send a chat completion and parse the JSON response."""
    system_with_json = system + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
    raw = chat(system_with_json, user, max_tokens)
    # Strip markdown code fences if present
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)
