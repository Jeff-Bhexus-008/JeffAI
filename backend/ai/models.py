"""
JeffAI model catalogue.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Every entry is a text model JeffAI can talk through. Requests are
resolved against this catalogue so the frontend never has to know
real provider model ids, and so unknown/retired ids fall back safely.
"""

DEFAULT_MODEL = "jeff-balanced"


MODELS = {
    "jeff-balanced": {
        "label": "JeffAI Balanced",
        "provider": "groq",
        "id": "openai/gpt-oss-120b",
        "description": "The default. Fast, careful, and strong at reasoning.",
        "badge": "Default",
    },
    "jeff-fast": {
        "label": "JeffAI Fast",
        "provider": "groq",
        "id": "llama-3.1-8b-instant",
        "description": "Instant replies for quick questions and short chats.",
        "badge": "Fastest",
    },
    "jeff-smart": {
        "label": "JeffAI Smart",
        "provider": "groq",
        "id": "llama-3.3-70b-versatile",
        "description": "Deeper answers for writing, analysis, and long context.",
        "badge": "Deep",
    },
    "jeff-coder": {
        "label": "JeffAI Coder",
        "provider": "groq",
        "id": "openai/gpt-oss-20b",
        "description": "Tuned towards code, debugging, and technical work.",
        "badge": "Code",
    },
    "jeff-cloud": {
        "label": "JeffAI Cloud",
        "provider": "openrouter",
        "id": "openai/gpt-oss-120b",
        "description": "OpenRouter route used automatically when Groq is busy.",
        "badge": "Failover",
    },
}


# =========================================================
# VISION
# =========================================================

# Tried in order. Vision support varies between providers, so the
# first model that answers wins.
VISION_MODELS = [
    {
        "provider": "groq",
        "id": "meta-llama/llama-4-scout-17b-16e-instruct",
    },
    {
        "provider": "groq",
        "id": "meta-llama/llama-4-maverick-17b-128e-instruct",
    },
    {
        "provider": "openrouter",
        "id": "google/gemini-2.0-flash-001",
    },
    {
        "provider": "openrouter",
        "id": "openai/gpt-4o-mini",
    },
]


# =========================================================
# AUDIO
# =========================================================

TRANSCRIPTION_MODELS = [
    "whisper-large-v3-turbo",
    "whisper-large-v3",
]


def resolve_model(model_key):
    """Return a catalogue entry for a key, or the default."""

    if isinstance(model_key, dict):
        return model_key

    entry = MODELS.get(model_key) if model_key else None

    return entry or MODELS[DEFAULT_MODEL]


def public_model_list():
    """The model list shown in the UI selector."""

    return [
        {
            "key": key,
            "label": entry["label"],
            "description": entry["description"],
            "badge": entry.get("badge", ""),
            "provider": entry["provider"],
        }
        for key, entry in MODELS.items()
    ]
