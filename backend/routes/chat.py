import os
import requests

from flask import Blueprint, request, jsonify

from backend.ai.engine import jeffai


chat_bp = Blueprint("chat", __name__)


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def get_user():

    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "", 1).strip()

    if not token:
        return None

    try:

        response = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {token}"
            },
            timeout=15
        )

        if response.status_code != 200:
            return None

        return response.json()

    except Exception:
        return None


def supabase_headers(token):

    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


@chat_bp.route("/api/conversations", methods=["GET"])
def conversations():

    user = get_user()

    if not user:
        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = request.headers.get("Authorization").replace(
        "Bearer ", "", 1
    )

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


@chat_bp.route("/api/conversations", methods=["POST"])
def create_conversation():

    user = get_user()

    if not user:
        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = request.headers.get("Authorization").replace(
        "Bearer ", "", 1
    )

    data = request.get_json(silent=True) or {}

    title = data.get("title", "New conversation")

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

        conversation = response.json()[0]

        return jsonify({
            "success": True,
            "conversation": conversation
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500


@chat_bp.route("/api/chat", methods=["POST"])
def chat():

    user = get_user()

    if not user:
        return jsonify({
            "success": False,
            "error": "You must be logged in."
        }), 401

    token = request.headers.get("Authorization").replace(
        "Bearer ", "", 1
    )

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "error": "Invalid request."
        }), 400

    message = data.get("message", "").strip()

    conversation_id = data.get("conversation_id")

    if not message:
        return jsonify({
            "success": False,
            "error": "Message cannot be empty."
        }), 400

    if not conversation_id:

        create_response = requests.post(
            f"{SUPABASE_URL}/rest/v1/conversations",
            headers=supabase_headers(token),
            json={
                "user_id": user["id"],
                "title": message[:60]
            },
            timeout=15
        )

        if create_response.status_code >= 400:
            return jsonify({
                "success": False,
                "error": create_response.text
            }), create_response.status_code

        conversation_id = create_response.json()[0]["id"]

    try:

        user_message_response = requests.post(
            f"{SUPABASE_URL}/rest/v1/messages",
            headers=supabase_headers(token),
            json={
                "conversation_id": conversation_id,
                "user_id": user["id"],
                "role": "user",
                "content": message
            },
            timeout=15
        )

        if user_message_response.status_code >= 400:
            return jsonify({
                "success": False,
                "error": user_message_response.text
            }), user_message_response.status_code

        ai_response = jeffai.respond(message)

        assistant_response = requests.post(
            f"{SUPABASE_URL}/rest/v1/messages",
            headers=supabase_headers(token),
            json={
                "conversation_id": conversation_id,
                "user_id": user["id"],
                "role": "assistant",
                "content": ai_response
            },
            timeout=15
        )

        if assistant_response.status_code >= 400:
            return jsonify({
                "success": False,
                "error": assistant_response.text
            }), assistant_response.status_code

        return jsonify({
            "success": True,
            "conversation_id": conversation_id,
            "message": ai_response
        })

    except Exception as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 500