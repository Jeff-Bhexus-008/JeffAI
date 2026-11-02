"""
JeffAI application entry point.

Created by Amedu Vincent Onjefu (Jeff Bhexus).
"""

import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv


load_dotenv()


FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
)


app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path="",
)


CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    supports_credentials=False,
)


from backend.routes.chat import chat_bp
from backend.routes.tools import tools_bp

app.register_blueprint(chat_bp)
app.register_blueprint(tools_bp)


# =========================================================
# PAGES
# =========================================================

def page(filename):

    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/")
def home():
    return page("index.html")


@app.route("/login.html")
def login():
    return page("login.html")


@app.route("/signup.html")
def signup():
    return page("signup.html")


@app.route("/config.js")
def config():
    return page("config.js")


@app.route("/downloads/<path:filename>")
def download_apk(filename):

    return send_from_directory(
        os.path.join(FRONTEND_DIR, "downloads"),
        filename,
        as_attachment=True,
    )


# =========================================================
# HEALTH
# =========================================================

@app.route("/api/health")
def health():

    from backend.ai.engine import provider_available
    from backend.supabase_client import supabase_ready

    return jsonify({
        "success": True,
        "name": "JeffAI",
        "creator": "Amedu Vincent Onjefu (Jeff Bhexus)",
        "status": "online",
        "version": "2.0.0",
        "providers": {
            "groq": provider_available("groq"),
            "openrouter": provider_available("openrouter"),
        },
        "database": supabase_ready(),
    })


# =========================================================
# CACHE HEADERS
# =========================================================

@app.after_request
def cache_headers(response):

    if response.mimetype == "text/event-stream":
        return response

    path = request_path()

    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"

    elif path.endswith((".js", ".css", ".png", ".jpg", ".svg", ".woff2")):
        response.headers["Cache-Control"] = "public, max-age=3600"

    elif path.endswith(".html") or path == "/":
        response.headers["Cache-Control"] = "no-cache"

    return response


def request_path():

    from flask import request as flask_request

    return flask_request.path


# =========================================================
# ERRORS
# =========================================================

@app.errorhandler(404)
def not_found(error):

    from flask import request as flask_request

    path = flask_request.path

    if path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "Not found.",
        }), 404

    # Unknown page routes fall through to the app shell; a missing
    # asset must stay a real 404 so broken files are obvious.
    if "." in path.rsplit("/", 1)[-1]:
        return jsonify({
            "success": False,
            "error": "File not found.",
        }), 404

    return page("index.html")


@app.errorhandler(500)
def server_error(error):

    print("Server error:", error)

    from flask import request as flask_request

    if flask_request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "Something went wrong. Please try again.",
        }), 500

    return page("index.html")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=True,
    )
