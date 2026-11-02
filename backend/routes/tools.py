"""
JeffAI tool routes: models, image studio, image understanding, voice
transcription and saved files.

Created by Amedu Vincent Onjefu (Jeff Bhexus).
"""

import base64
import io

import requests

from flask import Blueprint, jsonify, request

from backend.ai.engine import AIUnavailable, jeffai, provider_available
from backend.ai.images import data_url, generate_image, save_image
from backend.ai.models import public_model_list
from backend.supabase_client import (
    get_token,
    get_user,
    rest,
    signed_storage_url,
    supabase_headers,
    supabase_key,
    supabase_url,
)


tools_bp = Blueprint("tools", __name__)


MAX_IMAGE_BYTES = 8 * 1024 * 1024

MAX_AUDIO_BYTES = 20 * 1024 * 1024


def _auth():
    """Return (user, token) or (None, None)."""

    user = get_user()

    if not user:
        return None, None

    return user, get_token()


def _unauthorized():
    return jsonify({
        "success": False,
        "error": "You must be logged in.",
    }), 401


# =========================================================
# MODELS / STATUS
# =========================================================

@tools_bp.route("/api/models", methods=["GET"])
def models():

    return jsonify({
        "success": True,
        "models": public_model_list(),
        "providers": {
            "groq": provider_available("groq"),
            "openrouter": provider_available("openrouter"),
        },
        "tools": {
            "images": True,
            "vision": provider_available("groq")
            or provider_available("openrouter"),
            "transcription": provider_available("groq"),
        },
    })


@tools_bp.route("/api/status", methods=["GET"])
def status():

    return jsonify({
        "success": True,
        "name": "JeffAI",
        "creator": "Amedu Vincent Onjefu (Jeff Bhexus)",
        "version": "2.0.0",
        "providers": {
            "groq": provider_available("groq"),
            "openrouter": provider_available("openrouter"),
        },
        "storage": bool(supabase_url() and supabase_key()),
    })


# =========================================================
# IMAGE GENERATION
# =========================================================

@tools_bp.route("/api/images/generate", methods=["POST"])
def images_generate():

    user, token = _auth()

    if not user:
        return _unauthorized()

    data = request.get_json(silent=True) or {}

    prompt = (data.get("prompt") or "").strip()

    if not prompt:
        return jsonify({
            "success": False,
            "error": "Please describe the image you want to create.",
        }), 400

    if len(prompt) > 2000:
        prompt = prompt[:2000]

    style = data.get("style") or "auto"
    aspect = data.get("aspect") or "square"

    try:

        image_bytes, mime, meta = generate_image(
            prompt,
            style=style,
            aspect=aspect,
        )

    except AIUnavailable as error:

        return jsonify({
            "success": False,
            "error": str(error),
        }), 503

    except ValueError as error:

        return jsonify({
            "success": False,
            "error": str(error),
        }), 400

    except Exception as error:

        print("[JeffAI] image generation error:", error)

        return jsonify({
            "success": False,
            "error": "Image generation failed. Please try again.",
        }), 500

    extension = "png" if "png" in mime else "jpg"

    record = save_image(
        token,
        user["id"],
        image_bytes,
        extension=extension,
        prompt=prompt,
    )

    payload = {
        "success": True,
        "image": {
            "prompt": prompt,
            "style": style,
            "aspect": aspect,
            "data_url": data_url(image_bytes, mime),
            "provider": meta.get("provider"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "saved_id": record.get("id") if record else None,
            "saved_url": (
                signed_storage_url(record["file_path"])
                if record and record.get("file_path")
                else None
            ),
        },
    }

    return jsonify(payload)


@tools_bp.route("/api/images", methods=["GET"])
def images_list():

    user, token = _auth()

    if not user:
        return _unauthorized()

    try:

        response = requests.get(
            rest("images"),
            headers=supabase_headers(token),
            params={
                "user_id": f"eq.{user['id']}",
                "select": "id,prompt,file_path,file_type,created_at",
                "order": "created_at.desc",
                "limit": "60",
            },
            timeout=20,
        )

        if response.status_code >= 400:
            # The images table is optional; empty gallery beats an error.
            return jsonify({"success": True, "images": []})

        images = []

        for row in response.json():

            images.append({
                "id": row["id"],
                "prompt": row.get("prompt", ""),
                "created_at": row.get("created_at"),
                "url": signed_storage_url(row.get("file_path")),
            })

        return jsonify({"success": True, "images": images})

    except Exception as error:

        print("[JeffAI] image list error:", error)

        return jsonify({"success": True, "images": []})


@tools_bp.route("/api/images/<image_id>", methods=["DELETE"])
def images_delete(image_id):

    user, token = _auth()

    if not user:
        return _unauthorized()

    try:

        lookup = requests.get(
            rest("images"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{image_id}",
                "user_id": f"eq.{user['id']}",
                "select": "id,file_path",
                "limit": "1",
            },
            timeout=20,
        )

        rows = lookup.json() if lookup.status_code == 200 else []

        if not rows:
            return jsonify({
                "success": False,
                "error": "Image not found.",
            }), 404

        path = rows[0].get("file_path")

        if path:

            requests.delete(
                f"{supabase_url()}/storage/v1/object/documents/{path}",
                headers={
                    "apikey": supabase_key(),
                    "Authorization": f"Bearer {token}",
                },
                timeout=30,
            )

        requests.delete(
            rest("images"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{image_id}",
                "user_id": f"eq.{user['id']}",
            },
            timeout=20,
        )

        return jsonify({"success": True})

    except Exception as error:

        print("[JeffAI] image delete error:", error)

        return jsonify({
            "success": False,
            "error": "Could not delete this image.",
        }), 500


# =========================================================
# IMAGE UNDERSTANDING
# =========================================================

@tools_bp.route("/api/vision", methods=["POST"])
def vision():

    user, _ = _auth()

    if not user:
        return _unauthorized()

    question = ""

    if request.files and "image" in request.files:

        file = request.files["image"]

        if not file.filename:
            return jsonify({
                "success": False,
                "error": "No image selected.",
            }), 400

        file_bytes = file.read()

        if len(file_bytes) > MAX_IMAGE_BYTES:
            return jsonify({
                "success": False,
                "error": "Image is too large. Maximum size is 8 MB.",
            }), 400

        mimetype = file.mimetype or "image/png"

        if not mimetype.startswith("image/"):
            return jsonify({
                "success": False,
                "error": "Please upload an image file.",
            }), 400

        encoded = base64.b64encode(file_bytes).decode("ascii")

        image_data_url = f"data:{mimetype};base64,{encoded}"

        question = (request.form.get("question") or "").strip()

    else:

        data = request.get_json(silent=True) or {}

        image_data_url = (data.get("image") or "").strip()

        question = (data.get("question") or "").strip()

        if not image_data_url.startswith("data:image/"):
            return jsonify({
                "success": False,
                "error": "Please provide an image.",
            }), 400

    try:

        answer = jeffai.vision(image_data_url, question)

    except AIUnavailable as error:

        return jsonify({
            "success": False,
            "error": str(error),
        }), 503

    except Exception as error:

        print("[JeffAI] vision error:", error)

        return jsonify({
            "success": False,
            "error": "I could not read that image. Please try again.",
        }), 500

    return jsonify({"success": True, "answer": answer})


# =========================================================
# VOICE TRANSCRIPTION
# =========================================================

@tools_bp.route("/api/transcribe", methods=["POST"])
def transcribe():

    user, _ = _auth()

    if not user:
        return _unauthorized()

    if "audio" not in request.files:
        return jsonify({
            "success": False,
            "error": "No audio received.",
        }), 400

    file = request.files["audio"]

    audio_bytes = file.read()

    if not audio_bytes:
        return jsonify({
            "success": False,
            "error": "The recording was empty.",
        }), 400

    if len(audio_bytes) > MAX_AUDIO_BYTES:
        return jsonify({
            "success": False,
            "error": "Recording is too long. Please keep it under 2 minutes.",
        }), 400

    filename = file.filename or "recording.webm"

    mimetype = file.mimetype or "audio/webm"

    try:

        text = jeffai.transcribe(audio_bytes, filename, mimetype)

    except AIUnavailable as error:

        return jsonify({
            "success": False,
            "error": str(error),
        }), 503

    except Exception as error:

        print("[JeffAI] transcription error:", error)

        return jsonify({
            "success": False,
            "error": "I could not transcribe that recording.",
        }), 500

    return jsonify({"success": True, "text": text})


# =========================================================
# SAVED FILES
# =========================================================

@tools_bp.route("/api/files", methods=["GET"])
def files():

    user, token = _auth()

    if not user:
        return _unauthorized()

    documents = []
    images = []

    try:

        response = requests.get(
            rest("documents"),
            headers=supabase_headers(token),
            params={
                "user_id": f"eq.{user['id']}",
                "select": "id,filename,file_type,created_at,file_path",
                "order": "created_at.desc",
                "limit": "100",
            },
            timeout=20,
        )

        if response.status_code == 200:
            documents = response.json()

    except Exception:

        documents = []

    try:

        response = requests.get(
            rest("images"),
            headers=supabase_headers(token),
            params={
                "user_id": f"eq.{user['id']}",
                "select": "id,prompt,file_path,created_at",
                "order": "created_at.desc",
                "limit": "40",
            },
            timeout=20,
        )

        if response.status_code == 200:
            images = response.json()

    except Exception:

        images = []

    return jsonify({
        "success": True,
        "documents": documents,
        "images": [
            {
                "id": row["id"],
                "prompt": row.get("prompt", ""),
                "created_at": row.get("created_at"),
                "url": signed_storage_url(row.get("file_path")),
            }
            for row in images
        ],
    })


@tools_bp.route("/api/documents/<document_id>", methods=["DELETE"])
def delete_document(document_id):

    user, token = _auth()

    if not user:
        return _unauthorized()

    try:

        lookup = requests.get(
            rest("documents"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{document_id}",
                "user_id": f"eq.{user['id']}",
                "select": "id,file_path",
                "limit": "1",
            },
            timeout=20,
        )

        rows = lookup.json() if lookup.status_code == 200 else []

        if not rows:
            return jsonify({
                "success": False,
                "error": "Document not found.",
            }), 404

        path = rows[0].get("file_path")

        if path:

            requests.delete(
                f"{supabase_url()}/storage/v1/object/documents/{path}",
                headers={
                    "apikey": supabase_key(),
                    "Authorization": f"Bearer {token}",
                },
                timeout=30,
            )

        requests.delete(
            rest("documents"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{document_id}",
                "user_id": f"eq.{user['id']}",
            },
            timeout=20,
        )

        return jsonify({"success": True})

    except Exception as error:

        print("[JeffAI] document delete error:", error)

        return jsonify({
            "success": False,
            "error": "Could not delete that document.",
        }), 500


# =========================================================
# DOCUMENT ANALYSIS
# =========================================================

@tools_bp.route("/api/documents/<document_id>/analyze", methods=["POST"])
def analyze_document(document_id):

    user, token = _auth()

    if not user:
        return _unauthorized()

    data = request.get_json(silent=True) or {}

    task = (data.get("task") or "summary").strip()

    instructions = {
        "summary": "Summarise this document in clear, useful paragraphs.",
        "keypoints": "List the key points of this document as a short bulleted list.",
        "action": "Extract every action item, task and deadline you can find.",
        "explain": "Explain this document in simple language a beginner can follow.",
        "questions": "Write 8 study questions with short answers based on this document.",
    }

    instruction = instructions.get(
        task,
        "Analyse this document and explain what matters.",
    )

    try:

        response = requests.get(
            rest("documents"),
            headers=supabase_headers(token),
            params={
                "id": f"eq.{document_id}",
                "user_id": f"eq.{user['id']}",
                "select": "filename,extracted_text",
                "limit": "1",
            },
            timeout=20,
        )

        rows = response.json() if response.status_code == 200 else []

        if not rows:
            return jsonify({
                "success": False,
                "error": "Document not found.",
            }), 404

        text = (rows[0].get("extracted_text") or "")[:60000]

        prompt = (
            f"DOCUMENT: {rows[0].get('filename')}\n\n{text}\n\n"
            f"TASK: {instruction}"
        )

        answer = jeffai.respond(prompt)

        return jsonify({
            "success": True,
            "answer": answer,
            "filename": rows[0].get("filename"),
        })

    except AIUnavailable as error:

        return jsonify({
            "success": False,
            "error": str(error),
        }), 503

    except Exception as error:

        print("[JeffAI] document analyse error:", error)

        return jsonify({
            "success": False,
            "error": "Could not analyse that document.",
        }), 500
