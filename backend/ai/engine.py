"""
JeffAI AI engine.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Design goals:
- Never crash the whole Flask app because one key is missing.
- Prefer the model the user picked, then fail over quietly.
- Support both a blocking call and a token stream.
- Keep every provider call in one place so new providers are cheap.
"""

import os

from dotenv import load_dotenv
from groq import Groq
from openai import OpenAI

from backend.ai.models import (
    DEFAULT_MODEL,
    MODELS,
    TRANSCRIPTION_MODELS,
    VISION_MODELS,
    resolve_model,
)
from backend.ai.prompts import BASE_IDENTITY, build_prompt


load_dotenv()


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _env(*names):
    for name in names:
        value = os.getenv(name)

        if value and value.strip():
            return value.strip()

    return None


def groq_api_key():
    return _env("GROQ_API_KEY", "GROQ_KEY")


def openrouter_api_key():
    return _env("OPENROUTER_API_KEY", "OPENROUTER_KEY")


def provider_available(provider):

    if provider == "groq":
        return bool(groq_api_key())

    if provider == "openrouter":
        return bool(openrouter_api_key())

    return False


# =========================================================
# CLIENTS (lazy - a missing key must not break the app)
# =========================================================

_clients = {}


def get_client(provider):

    if provider in _clients:
        return _clients[provider]

    if provider == "groq":

        key = groq_api_key()

        if not key:
            return None

        client = Groq(api_key=key)

    elif provider == "openrouter":

        key = openrouter_api_key()

        if not key:
            return None

        client = OpenAI(
            api_key=key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": os.getenv(
                    "APP_URL",
                    "https://jeffai-pwit.onrender.com",
                ),
                "X-Title": "JeffAI",
            },
        )

    else:
        return None

    _clients[provider] = client

    return client


class AIUnavailable(Exception):
    """Raised when no provider could answer at all."""


class JeffAI:
    """The JeffAI model router."""

    def __init__(self):
        self.name = "JeffAI"

    # -----------------------------------------------------
    # CANDIDATES
    # -----------------------------------------------------

    def candidates(self, model_key=None):
        """Ordered list of (provider, model_id) to try."""

        selected = resolve_model(model_key)

        chain = [
            (selected["provider"], selected["id"]),
            ("groq", MODELS[DEFAULT_MODEL]["id"]),
            (
                "openrouter",
                MODELS["jeff-cloud"]["id"],
            ),
        ]

        seen = set()
        ordered = []

        for provider, model_id in chain:

            signature = (provider, model_id)

            if signature in seen:
                continue

            if not provider_available(provider):
                continue

            seen.add(signature)
            ordered.append(signature)

        return ordered

    # -----------------------------------------------------
    # BLOCKING
    # -----------------------------------------------------

    def respond(self, message, model=None, mode="chat", temperature=0.7):
        """Legacy helper: one prompt in, one string out."""

        messages = [
            {
                "role": "user",
                "content": message,
            }
        ]

        text, _ = self.chat(messages, model=model, mode=mode, temperature=temperature)

        return text

    def chat(
        self,
        messages,
        model=None,
        mode="chat",
        temperature=0.7,
        max_tokens=2048,
    ):
        """Return (text, used_model_entry)."""

        candidates = self.candidates(model)

        if not candidates:
            raise AIUnavailable(
                "No AI provider keys are configured."
            )

        last_error = None

        for provider, model_id in candidates:

            client = get_client(provider)

            if not client:
                continue

            try:

                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )

                text = (
                    response.choices[0].message.content or ""
                ).strip()

                if not text:
                    raise RuntimeError("Empty response")

                return text, {"provider": provider, "id": model_id}

            except Exception as error:

                last_error = error

                print(f"[JeffAI] {provider}/{model_id} failed: {error}")

        raise AIUnavailable(str(last_error) if last_error else "AI unavailable")

    # -----------------------------------------------------
    # STREAMING
    # -----------------------------------------------------

    def stream(
        self,
        messages,
        model=None,
        mode="chat",
        temperature=0.7,
        max_tokens=2048,
    ):
        """Yield text deltas. Raises AIUnavailable if nothing worked."""

        candidates = self.candidates(model)

        if not candidates:
            raise AIUnavailable(
                "No AI provider keys are configured."
            )

        last_error = None

        for provider, model_id in candidates:

            client = get_client(provider)

            if not client:
                continue

            produced = False

            try:

                response = client.chat.completions.create(
                    model=model_id,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )

                for chunk in response:

                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    piece = getattr(delta, "content", None)

                    if piece:
                        produced = True
                        yield piece

                if produced:
                    return

                raise RuntimeError("Empty stream")

            except Exception as error:

                last_error = error

                print(f"[JeffAI] stream {provider}/{model_id} failed: {error}")

                # If we already streamed text, do not restart with
                # another model and repeat the answer.
                if produced:
                    return

        raise AIUnavailable(str(last_error) if last_error else "AI unavailable")

    # -----------------------------------------------------
    # VISION
    # -----------------------------------------------------

    def vision(self, image_data_url, question, model=None):
        """Describe or answer a question about an image."""

        prompt = question or (
            "Describe this image in detail. Mention any text, numbers, "
            "code, or important visual details."
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            }
        ]

        last_error = None

        for entry in VISION_MODELS:

            if not provider_available(entry["provider"]):
                continue

            client = get_client(entry["provider"])

            if not client:
                continue

            try:

                response = client.chat.completions.create(
                    model=entry["id"],
                    messages=messages,
                    temperature=0.4,
                    max_tokens=1600,
                )

                text = (
                    response.choices[0].message.content or ""
                ).strip()

                if text:
                    return text

                raise RuntimeError("Empty vision response")

            except Exception as error:

                last_error = error

                print(
                    f"[JeffAI] vision {entry['provider']}/{entry['id']} "
                    f"failed: {error}"
                )

        raise AIUnavailable(
            str(last_error)
            if last_error
            else "Image understanding is unavailable right now."
        )

    # -----------------------------------------------------
    # TRANSCRIPTION
    # -----------------------------------------------------

    def transcribe(self, file_bytes, filename="audio.webm", mimetype=None):

        client = get_client("groq")

        if not client:
            raise AIUnavailable(
                "Voice transcription needs GROQ_API_KEY."
            )

        last_error = None

        for model_id in TRANSCRIPTION_MODELS:

            try:

                result = client.audio.transcriptions.create(
                    file=(
                        filename,
                        file_bytes,
                        mimetype or "audio/webm",
                    ),
                    model=model_id,
                    response_format="json",
                )

                text = getattr(result, "text", "") or ""

                if text.strip():
                    return text.strip()

                raise RuntimeError("Empty transcript")

            except Exception as error:

                last_error = error

                print(
                    f"[JeffAI] transcription {model_id} failed: {error}"
                )

        raise AIUnavailable(
            str(last_error) if last_error else "Transcription failed."
        )


jeffai = JeffAI()

__all__ = [
    "JeffAI",
    "jeffai",
    "AIUnavailable",
    "provider_available",
    "build_prompt",
    "BASE_IDENTITY",
]
