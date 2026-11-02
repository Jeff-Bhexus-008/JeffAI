"""
JeffAI conversation context.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Everything the model needs to answer well - recent turns, long term
memory, and the user's documents - is assembled here so both the
blocking chat route and the streaming route share one implementation.
"""

import os

import requests

from backend.ai.prompts import build_prompt, build_title
from backend.supabase_client import (
    rest,
    signed_storage_url,
    supabase_headers,
    supabase_key,
    supabase_url,
)


TIMEOUT = 20


# =========================================================
# LOW LEVEL
# =========================================================

def get_memories(token, user_id, limit=20):

    try:

        response = requests.get(
            rest("memories"),
            headers=supabase_headers(token),
            params={
                "user_id": f"eq.{user_id}",
                "select": "id,memory",
                "order": "created_at.desc",
                "limit": str(limit),
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        return response.json()

    except Exception:

        return []


def get_history(token, user_id, conversation_id, limit=20):

    try:

        response = requests.get(
            rest("messages"),
            headers=supabase_headers(token),
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "select": "role,content",
                "order": "created_at.desc",
                "limit": str(limit),
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        return list(reversed(response.json()))

    except Exception:

        return []


def get_documents(token, user_id, limit=5):

    try:

        response = requests.get(
            rest("documents"),
            headers=supabase_headers(token),
            params={
                "user_id": f"eq.{user_id}",
                "select": "filename,extracted_text",
                "order": "created_at.desc",
                "limit": str(limit),
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return []

        return response.json()

    except Exception:

        return []


# =========================================================
# CONVERSATIONS
# =========================================================

def create_conversation(token, user_id, title):

    response = requests.post(
        rest("conversations"),
        headers=supabase_headers(token),
        json={
            "user_id": user_id,
            "title": build_title(title),
        },
        timeout=TIMEOUT,
    )

    if response.status_code >= 400:
        raise RuntimeError(response.text)

    return response.json()[0]["id"]


def ensure_conversation(token, user_id, conversation_id, message):

    if conversation_id:
        return conversation_id

    return create_conversation(token, user_id, message)


def save_message(token, user_id, conversation_id, role, content):

    response = requests.post(
        rest("messages"),
        headers=supabase_headers(token),
        json={
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content,
        },
        timeout=TIMEOUT,
    )

    if response.status_code >= 400:
        raise RuntimeError(response.text)

    rows = response.json()

    return rows[0] if rows else {}


def touch_conversation(token, conversation_id, user_id):

    try:

        requests.patch(
            rest("conversations"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
            },
            json={},
            timeout=TIMEOUT,
        )

    except Exception:

        pass


# =========================================================
# EDIT / REGENERATE
# =========================================================

def find_message(token, user_id, message_id):

    try:

        response = requests.get(
            rest("messages"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{message_id}",
                "user_id": f"eq.{user_id}",
                "select": "id,conversation_id,role,content,created_at",
                "limit": "1",
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return None

        rows = response.json()

        return rows[0] if rows else None

    except Exception:

        return None


def delete_messages_from(token, user_id, conversation_id, created_at):

    """Remove a message and every message after it."""

    response = requests.delete(
        rest("messages"),
        headers=supabase_headers(token),
        params={
            "conversation_id": f"eq.{conversation_id}",
            "user_id": f"eq.{user_id}",
            "created_at": f"gte.{created_at}",
        },
        timeout=TIMEOUT,
    )

    return response.status_code < 400


def delete_last_assistant_message(token, user_id, conversation_id):

    try:

        response = requests.get(
            rest("messages"),
            headers=supabase_headers(token),
            params={
                "conversation_id": f"eq.{conversation_id}",
                "user_id": f"eq.{user_id}",
                "role": "eq.assistant",
                "select": "id,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return False

        rows = response.json()

        if not rows:
            return False

        requests.delete(
            rest("messages"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{rows[0]['id']}",
                "user_id": f"eq.{user_id}",
            },
            timeout=TIMEOUT,
        )

        return True

    except Exception:

        return False


# =========================================================
# MEMORY CAPTURE
# =========================================================

MEMORY_TRIGGERS = (
    "remember that",
    "remember this",
    "my name is",
    "i am",
    "i'm",
    "i like",
    "i prefer",
    "i work",
    "i study",
    "call me",
)


def maybe_store_memory(token, user_id, message):

    lower = (message or "").lower()

    if not any(phrase in lower for phrase in MEMORY_TRIGGERS):
        return None

    try:

        response = requests.post(
            rest("memories"),
            headers=supabase_headers(token),
            json={
                "user_id": user_id,
                "memory": message[:500],
            },
            timeout=TIMEOUT,
        )

        if response.status_code >= 400:
            return None

        return response.json()

    except Exception:

        return None


# =========================================================
# CONTEXT BUNDLE
# =========================================================

def build_chat_context(
    token,
    user,
    message,
    conversation_id=None,
    mode="chat",
    attachments=None,
    regenerate=False,
    persist_user=True,
    use_memory=True,
):
    """Prepare one AI turn.

    Normal turn: history is read first, then the new user message is
    stored, so the prompt never repeats the current message.

    Regenerate: the previous assistant reply is removed and the last
    user message is answered again without storing a duplicate.
    """

    user_id = user["id"]

    conversation_id = ensure_conversation(
        token,
        user_id,
        conversation_id,
        message or "New conversation",
    )

    if regenerate and conversation_id:

        delete_last_assistant_message(token, user_id, conversation_id)

        history = get_history(token, user_id, conversation_id)

        current = message

        if history and history[-1].get("role") == "user":
            current = current or history[-1].get("content", "")
            history = history[:-1]

        if not current:
            raise ValueError("There is nothing to regenerate yet.")

        message = current

    else:

        history = get_history(token, user_id, conversation_id)

        if persist_user and message:
            save_message(token, user_id, conversation_id, "user", message)

    memories = get_memories(token, user_id) if use_memory else []
    documents = get_documents(token, user_id)

    prompt = build_prompt(
        message,
        memories=[item["memory"] for item in memories if item.get("memory")],
        history=history,
        documents=documents,
        mode=mode,
        attachments=attachments,
    )

    return {
        "conversation_id": conversation_id,
        "prompt": prompt,
        "message": message,
        "memory_count": len(memories),
        "history_count": len(history),
        "document_count": len(documents),
    }


__all__ = [
    "build_chat_context",
    "create_conversation",
    "delete_last_assistant_message",
    "delete_messages_from",
    "ensure_conversation",
    "find_message",
    "get_documents",
    "get_history",
    "get_memories",
    "maybe_store_memory",
    "save_message",
    "signed_storage_url",
    "supabase_key",
    "supabase_url",
    "touch_conversation",
]
