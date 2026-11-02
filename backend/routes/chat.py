import io
import json
import os
import textwrap

import requests

from flask import (
    Blueprint,
    Response,
    jsonify,
    request,
    send_file,
    stream_with_context,
)

from pypdf import PdfReader
from docx import Document

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from backend.ai.context import (
    build_chat_context,
    delete_messages_from,
    find_message,
    maybe_store_memory,
    save_message,
    touch_conversation,
)
from backend.ai.engine import AIUnavailable, jeffai
from backend.supabase_client import get_token, get_user, supabase_headers


chat_bp = Blueprint("chat", __name__)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


# ==========================================
# AUTH
# ==========================================
#
# get_token / get_user / supabase_headers live in
# backend.supabase_client so every blueprint shares one implementation.

# ==========================================
# CONVERSATIONS
# ==========================================

@chat_bp.route(
    "/api/conversations",
    methods=["GET"]
)
def conversations():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    try:

        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/conversations",
            headers=supabase_headers(token),
            params={
                "user_id": f"eq.{user['id']}",
                "select": "*",
                "order": "updated_at.desc"
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True,
            "conversations": response.json()
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


@chat_bp.route(
    "/api/conversations",
    methods=["POST"]
)
def create_conversation():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    data = request.get_json(
        silent=True
    ) or {}

    title = data.get(
        "title",
        "New conversation"
    ).strip()

    if not title:
        title = "New conversation"

    try:

        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/conversations",
            headers=supabase_headers(token),
            json={
                "user_id": user["id"],
                "title": title
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True,
            "conversation": response.json()[0]
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


@chat_bp.route(
    "/api/conversations/<conversation_id>/messages",
    methods=["GET"]
)
def get_messages(conversation_id):

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    try:

        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/messages",
            headers=supabase_headers(token),
            params={
                "conversation_id":
                    f"eq.{conversation_id}",
                "user_id":
                    f"eq.{user['id']}",
                "select":
                    "*",
                "order":
                    "created_at.asc"
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True,
            "messages": response.json()
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# RENAME CONVERSATION
# ==========================================

@chat_bp.route(
    "/api/conversations/<conversation_id>",
    methods=["PATCH"]
)
def rename_conversation(conversation_id):

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    data = request.get_json(
        silent=True
    ) or {}

    title = data.get(
        "title",
        ""
    ).strip()

    if not title:

        return jsonify({
            "success": False,
            "error": "Conversation name cannot be empty."
        }), 400

    if len(title) > 100:

        return jsonify({
            "success": False,
            "error":
                "Conversation name cannot exceed 100 characters."
        }), 400

    try:

        response = requests.patch(
            f"{SUPABASE_URL}/rest/v1/conversations",
            headers=supabase_headers(token),
            params={
                "id":
                    f"eq.{conversation_id}",
                "user_id":
                    f"eq.{user['id']}"
            },
            json={
                "title": title
            },
            timeout=15
        )

        if response.status_code >= 400:

            print(
                "Rename conversation error:",
                response.text
            )

            return jsonify({
                "success": False,
                "error":
                    "Failed to rename conversation."
            }), response.status_code

        return jsonify({
            "success": True,
            "title": title
        })

    except Exception as error:

        print(
            "Rename conversation exception:",
            error
        )

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# DELETE CONVERSATION
# ==========================================

@chat_bp.route(
    "/api/conversations/<conversation_id>",
    methods=["DELETE"]
)
def delete_conversation(conversation_id):

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    try:

        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/conversations",
            headers=supabase_headers(token),
            params={
                "id":
                    f"eq.{conversation_id}",
                "user_id":
                    f"eq.{user['id']}"
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# LONG TERM MEMORY
# ==========================================

@chat_bp.route(
    "/api/memories",
    methods=["GET"]
)
def get_memories():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    try:

        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/memories",
            headers=supabase_headers(token),
            params={
                "user_id":
                    f"eq.{user['id']}",
                "select":
                    "*",
                "order":
                    "created_at.desc"
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True,
            "memories": response.json()
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


@chat_bp.route(
    "/api/memories",
    methods=["POST"]
)
def create_memory():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    data = request.get_json(
        silent=True
    ) or {}

    memory = data.get(
        "memory",
        ""
    ).strip()

    if not memory:

        return jsonify({
            "success": False,
            "error": "Memory cannot be empty."
        }), 400

    try:

        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/memories",
            headers=supabase_headers(token),
            json={
                "user_id":
                    user["id"],
                "memory":
                    memory
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True,
            "memory": response.json()[0]
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


@chat_bp.route(
    "/api/memories/<memory_id>",
    methods=["DELETE"]
)
def delete_memory(memory_id):

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    try:

        response = requests.delete(
            f"{SUPABASE_URL}/rest/v1/memories",
            headers=supabase_headers(token),
            params={
                "id":
                    f"eq.{memory_id}",
                "user_id":
                    f"eq.{user['id']}"
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# DOCUMENTS
# ==========================================

def extract_text(
    file_bytes,
    filename
):

    extension = (
        filename
        .lower()
        .split(".")[-1]
    )

    # ==========================================
    # TXT
    # ==========================================

    if extension == "txt":

        return file_bytes.decode(
            "utf-8",
            errors="ignore"
        )

    # ==========================================
    # PDF
    # ==========================================

    if extension == "pdf":

        pdf = PdfReader(
            io.BytesIO(file_bytes)
        )

        pages = []

        for page in pdf.pages:

            text = page.extract_text()

            if text:

                pages.append(text)

        return "\n\n".join(pages)

    # ==========================================
    # DOCX
    # ==========================================

    if extension == "docx":

        document = Document(
            io.BytesIO(file_bytes)
        )

        paragraphs = []

        for paragraph in document.paragraphs:

            if paragraph.text.strip():

                paragraphs.append(
                    paragraph.text
                )

        return "\n".join(paragraphs)

    raise ValueError(
        "Supported files are PDF, DOCX and TXT."
    )


@chat_bp.route(
    "/api/documents",
    methods=["POST"]
)
def upload_document():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    if "file" not in request.files:

        return jsonify({
            "success": False,
            "error": "No file uploaded."
        }), 400

    file = request.files["file"]

    if not file.filename:

        return jsonify({
            "success": False,
            "error": "No file selected."
        }), 400

    filename = file.filename

    allowed_extensions = {
        "pdf",
        "txt",
        "docx"
    }

    extension = (
        filename
        .lower()
        .split(".")[-1]
    )

    if extension not in allowed_extensions:

        return jsonify({
            "success": False,
            "error":
                "Only PDF, DOCX and TXT files are supported."
        }), 400

    try:

        file_bytes = file.read()

        # ==========================================
        # 10 MB LIMIT
        # ==========================================

        if len(file_bytes) > 10 * 1024 * 1024:

            return jsonify({
                "success": False,
                "error":
                    "File is too large. Maximum size is 10 MB."
            }), 400

        extracted_text = extract_text(
            file_bytes,
            filename
        )

        if not extracted_text.strip():

            return jsonify({
                "success": False,
                "error":
                    "No readable text was found in this document."
            }), 400

        storage_path = (
            f"{user['id']}/"
            f"{filename}"
        )

        # ==========================================
        # UPLOAD TO SUPABASE STORAGE
        # ==========================================

        storage_response = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/documents/"
            f"{storage_path}",
            headers={
                "apikey":
                    SUPABASE_KEY,
                "Authorization":
                    f"Bearer {token}",
                "Content-Type":
                    file.content_type
                    or "application/octet-stream"
            },
            data=file_bytes,
            timeout=60
        )

        if storage_response.status_code >= 400:

            return jsonify({
                "success": False,
                "error":
                    "Could not save document: "
                    + storage_response.text
            }), storage_response.status_code

        # ==========================================
        # SAVE DOCUMENT RECORD
        # ==========================================

        database_response = requests.post(
            f"{SUPABASE_URL}/rest/v1/documents",
            headers=supabase_headers(token),
            json={
                "user_id":
                    user["id"],
                "filename":
                    filename,
                "file_path":
                    storage_path,
                "file_type":
                    extension,
                "extracted_text":
                    extracted_text[:500000]
            },
            timeout=30
        )

        if database_response.status_code >= 400:

            return jsonify({
                "success": False,
                "error":
                    database_response.text
            }), database_response.status_code

        return jsonify({
            "success": True,
            "document":
                database_response.json()[0]
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


@chat_bp.route(
    "/api/documents",
    methods=["GET"]
)
def get_documents():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    try:

        response = requests.get(
            f"{SUPABASE_URL}/rest/v1/documents",
            headers=supabase_headers(token),
            params={
                "user_id":
                    f"eq.{user['id']}",
                "select":
                    "id,filename,file_type,created_at",
                "order":
                    "created_at.desc"
            },
            timeout=15
        )

        if response.status_code >= 400:

            return jsonify({
                "success": False,
                "error": response.text
            }), response.status_code

        return jsonify({
            "success": True,
            "documents": response.json()
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


# ==========================================
# TEXT → PDF
# ==========================================

@chat_bp.route(
    "/api/convert/text-to-pdf",
    methods=["POST"]
)
def text_to_pdf():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    try:

        data = request.get_json(
            silent=True
        ) or {}

        text = (
            data.get("text", "")
            .strip()
        )

        if not text:

            return jsonify({
                "success": False,
                "error":
                    "Please enter some text first."
            }), 400

        # ==========================================
        # CREATE PDF IN MEMORY
        # ==========================================

        pdf_buffer = io.BytesIO()

        pdf = canvas.Canvas(
            pdf_buffer,
            pagesize=A4
        )

        page_width, page_height = A4

        left_margin = 20 * mm
        right_margin = 20 * mm
        top_margin = 20 * mm
        bottom_margin = 20 * mm

        usable_width = (
            page_width
            - left_margin
            - right_margin
        )

        font_name = "Helvetica"
        font_size = 11
        line_height = 16

        pdf.setFont(
            font_name,
            font_size
        )

        y = (
            page_height
            - top_margin
        )

        # ==========================================
        # CONVERT TEXT INTO PDF LINES
        # ==========================================

        for paragraph in text.splitlines():

            if not paragraph.strip():

                y -= line_height

                continue

            # Approximate line length.
            # This keeps text inside the page.
            max_chars = 90

            lines = textwrap.wrap(
                paragraph,
                width=max_chars,
                replace_whitespace=False,
                drop_whitespace=True
            )

            for line in lines:

                # Create a new page when
                # the current page is full.
                if y <= bottom_margin:

                    pdf.showPage()

                    pdf.setFont(
                        font_name,
                        font_size
                    )

                    y = (
                        page_height
                        - top_margin
                    )

                pdf.drawString(
                    left_margin,
                    y,
                    line
                )

                y -= line_height

        pdf.save()

        pdf_buffer.seek(0)

        # ==========================================
        # RETURN PDF TO USER
        # ==========================================

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="JeffAI-Document.pdf"
        )

    except Exception as error:

        print(
            "TEXT TO PDF ERROR:",
            error
        )

        return jsonify({
            "success": False,
            "error":
                "Unable to create the PDF."
        }), 500


# ==========================================
# CHAT
# ==========================================

RATE_LIMIT_MESSAGE = (
    "JeffAI is taking a short break \u2615\n\n"
    "I've reached today's usage limit, so I can't process this "
    "message right now.\n\n"
    "Please try again a little later. "
    "Your conversations and documents are safe. \U0001F499"
)

RATE_LIMIT_MARKERS = (
    "429",
    "rate_limit_exceeded",
    "rate limit reached",
    "quota",
    "too many requests",
)


def is_rate_limit(error):
    text = str(error).lower()
    return any(marker in text for marker in RATE_LIMIT_MARKERS)


def parse_chat_request():
    """Read the shared JSON body for both chat routes."""

    data = request.get_json(silent=True) or {}

    payload = {
        "message": (data.get("message") or "").strip(),
        "conversation_id": data.get("conversation_id"),
        "model": data.get("model"),
        "mode": data.get("mode") or "chat",
        "regenerate": bool(data.get("regenerate")),
        "edit_message_id": data.get("edit_message_id"),
        "attachments": data.get("attachments") or [],
        "use_memory": data.get("use_memory", True) is not False,
    }

    temperature = data.get("temperature")

    try:
        payload["temperature"] = (
            0.7 if temperature is None else max(0.0, min(1.5, float(temperature)))
        )
    except (TypeError, ValueError):
        payload["temperature"] = 0.7

    return payload


def prepare_turn(user, token, payload):
    """Apply edit/regenerate rules and build the prompt bundle."""

    conversation_id = payload["conversation_id"]

    edit_message_id = payload["edit_message_id"]

    if edit_message_id:

        original = find_message(token, user["id"], edit_message_id)

        if original:

            conversation_id = original.get("conversation_id")

            delete_messages_from(
                token,
                user["id"],
                conversation_id,
                original.get("created_at"),
            )

    return build_chat_context(
        token,
        user,
        payload["message"],
        conversation_id=conversation_id,
        mode=payload["mode"],
        attachments=payload["attachments"],
        regenerate=payload["regenerate"],
        use_memory=payload["use_memory"],
    )


@chat_bp.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    payload = parse_chat_request()

    if not payload["message"] and not payload["regenerate"]:

        return jsonify({
            "success": False,
            "error": "Message cannot be empty."
        }), 400

    try:

        context = prepare_turn(user, token, payload)

    except ValueError as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except Exception as error:

        print("Chat context error:", error)

        return jsonify({
            "success": False,
            "error": "Something went wrong while preparing your chat."
        }), 500

    try:

        ai_response = jeffai.respond(
            context["prompt"],
            model=payload["model"],
            mode=payload["mode"],
            temperature=payload["temperature"],
        )

    except AIUnavailable as ai_error:

        if is_rate_limit(ai_error):

            print("JeffAI rate limit reached:", ai_error)

            return jsonify({
                "success": True,
                "conversation_id": context["conversation_id"],
                "response": RATE_LIMIT_MESSAGE,
                "error_type": "rate_limit"
            }), 200

        print("JeffAI error:", ai_error)

        return jsonify({
            "success": False,
            "error": "JeffAI is temporarily unavailable. "
                     "Please try again in a moment."
        }), 503

    except Exception as ai_error:

        print("JeffAI error:", ai_error)

        return jsonify({
            "success": False,
            "error": "JeffAI is temporarily unavailable. "
                     "Please try again in a moment."
        }), 503

    try:

        save_message(
            token,
            user["id"],
            context["conversation_id"],
            "assistant",
            ai_response,
        )

        touch_conversation(
            token,
            context["conversation_id"],
            user["id"],
        )

    except Exception as error:

        print("Saving reply failed:", error)

    if not payload["regenerate"] and payload["use_memory"]:

        maybe_store_memory(token, user["id"], context["message"])

    return jsonify({
        "success": True,
        "conversation_id": context["conversation_id"],
        "response": ai_response
    })


@chat_bp.route(
    "/api/chat/stream",
    methods=["POST"]
)
def chat_stream():

    user = get_user()

    if not user:

        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = get_token()

    payload = parse_chat_request()

    if not payload["message"] and not payload["regenerate"]:

        return jsonify({
            "success": False,
            "error": "Message cannot be empty."
        }), 400

    try:

        context = prepare_turn(user, token, payload)

    except ValueError as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 400

    except Exception as error:

        print("Chat context error:", error)

        return jsonify({
            "success": False,
            "error": "Something went wrong while preparing your chat."
        }), 500

    if not payload["regenerate"] and payload["use_memory"]:

        maybe_store_memory(token, user["id"], context["message"])

    messages = [
        {
            "role": "user",
            "content": context["prompt"],
        }
    ]

    def sse(event, data):

        return (
            "event: " + event + "\n"
            "data: " + json.dumps(data) + "\n\n"
        )

    def generate():

        yield sse("meta", {
            "conversation_id": context["conversation_id"],
            "memory_count": context["memory_count"],
            "document_count": context["document_count"],
        })

        collected = []
        saved = False
        failure = None

        try:

            for piece in jeffai.stream(
                messages,
                model=payload["model"],
                mode=payload["mode"],
                temperature=payload["temperature"],
            ):
                collected.append(piece)
                yield sse("delta", {"text": piece})

        except AIUnavailable as error:

            failure = "rate_limit" if is_rate_limit(error) else "unavailable"

            print("JeffAI stream error:", error)

        except GeneratorExit:

            failure = "cancelled"
            raise

        except Exception as error:

            failure = "unavailable"

            print("JeffAI stream error:", error)

        text = "".join(collected).strip()

        if failure == "rate_limit":

            yield sse("error", {
                "error": RATE_LIMIT_MESSAGE,
                "error_type": "rate_limit",
            })
            return

        if failure == "unavailable" and not text:

            yield sse("error", {
                "error": "JeffAI is temporarily unavailable. "
                         "Please try again in a moment.",
                "error_type": "unavailable",
            })
            return

        if not text:

            yield sse("error", {
                "error": "I could not produce a reply. Please try again.",
                "error_type": "empty",
            })
            return

        try:

            save_message(
                token,
                user["id"],
                context["conversation_id"],
                "assistant",
                text,
            )

            touch_conversation(
                token,
                context["conversation_id"],
                user["id"],
            )

            saved = True

        except Exception as error:

            print("Saving streamed reply failed:", error)

        yield sse("done", {
            "conversation_id": context["conversation_id"],
            "response": text,
            "saved": saved,
            "partial": bool(failure),
        })

    response = Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )

    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"

    return response
