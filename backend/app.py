"""
JeffAI application entry point.

Created by Amedu Vincent Onjefu (Jeff Bhexus).
"""

import os
from datetime import datetime

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
        APK_DIR,
        filename,
        as_attachment=True,
        mimetype=APK_MIME,
    )


# =========================================================
# HEALTH
# =========================================================

@app.route("/api/config")
def client_config():
    """
    Single source of truth for the browser's Supabase project.

    Serving this from the backend means a project migration only needs
    new Render environment variables - the frontend cannot keep pointing
    at a retired project.
    """

    from backend.supabase_client import public_client_config

    response = jsonify({
        "success": True,
        "version": "2.0.0",
        **public_client_config(),
    })

    response.headers["Cache-Control"] = "no-store, max-age=0"

    return response


# =========================================================
# ANDROID RELEASE
# =========================================================

APK_DIR = os.path.join(os.path.dirname(FRONTEND_DIR), "downloads")

APK_MIME = "application/vnd.android.package-archive"

_RELEASE_CACHE = {"key": None, "value": None}


def _apk_facts(path):
    """
    Describe an APK honestly: is it a real package, and is it signed?

    An unsigned APK still downloads, but Android refuses to install it,
    so the UI must not promise a working install in that case.
    """

    stat = os.stat(path)
    key = (path, stat.st_size, int(stat.st_mtime))

    if _RELEASE_CACHE["key"] == key:
        return dict(_RELEASE_CACHE["value"])

    import hashlib
    import zipfile

    facts = {
        "filename": os.path.basename(path),
        "size": stat.st_size,
        "updated_at": datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
        "valid_package": False,
        "signed": False,
        "sha256": "",
    }

    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                has_dex = any(name.startswith("classes") and name.endswith(".dex") for name in names)
                has_sig = any(
                    name.startswith("META-INF/") and name.upper().endswith((".RSA", ".DSA", ".EC"))
                    for name in names
                )

            facts["valid_package"] = has_dex and "AndroidManifest.xml" in names
            facts["signed"] = has_sig
    except Exception as error:
        facts["error"] = str(error)[:120]

    digest = hashlib.sha256()

    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    facts["sha256"] = digest.hexdigest()

    # v2/v3 signing lives in a block before the central directory.
    if not facts["signed"]:
        try:
            with open(path, "rb") as handle:
                head = handle.read(4 * 1024 * 1024)
                tail = b""
                handle.seek(max(0, stat.st_size - 1024 * 1024))
                tail = handle.read()
            facts["signed"] = b"APK Sig Block 42" in head or b"APK Sig Block 42" in tail
        except Exception:
            pass

    _RELEASE_CACHE["key"] = key
    _RELEASE_CACHE["value"] = dict(facts)

    return facts


def _human_size(size):
    return f"{size / (1024 * 1024):.1f} MB"


@app.route("/api/app-release")
def app_release():
    """
    What the "Download APK" button should point at.

    Order: an explicit APK_DOWNLOAD_URL (GitHub release asset or other
    stable host), then the APK shipped in frontend/downloads. Changing
    the target needs no frontend change.
    """

    override = (os.getenv("APK_DOWNLOAD_URL") or "").strip()

    if override:
        available = override.lower().endswith(".apk")
        payload = {
            "success": True,
            "available": available,
            "source": "external",
            "url": override,
            "filename": override.split("/")[-1].split("?")[0] or "JeffAI.apk",
            "installable": None,
            "message": "" if available else "APK_DOWNLOAD_URL is not an .apk URL.",
        }
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    candidates = []

    if os.path.isdir(APK_DIR):
        candidates = [
            os.path.join(APK_DIR, name)
            for name in os.listdir(APK_DIR)
            if name.lower().endswith(".apk")
        ]

    if not candidates:
        response = jsonify({
            "success": True,
            "available": False,
            "source": "none",
            "url": None,
            "message": "No APK has been published yet. Build it with the Android workflow, then it appears here automatically.",
        })
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    path = max(candidates, key=os.path.getmtime)
    facts = _apk_facts(path)

    reason = ""

    if not facts["valid_package"]:
        reason = "The file is not a valid Android package."
    elif not facts["signed"]:
        reason = "The APK is not signed, so Android will refuse to install it. Sign it before publishing."

    payload = {
        "success": True,
        "available": True,
        "source": "server",
        "url": f"/downloads/{facts['filename']}",
        "filename": facts["filename"],
        "size": facts["size"],
        "size_label": _human_size(facts["size"]),
        "sha256": facts["sha256"],
        "updated_at": facts["updated_at"],
        "signed": facts["signed"],
        "valid_package": facts["valid_package"],
        "installable": facts["valid_package"] and facts["signed"],
        "message": reason,
    }

    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store, max-age=0"

    return response


@app.route("/api/health")
def health():

    from backend.ai.engine import provider_available
    from backend.supabase_client import auth_service_health, supabase_ready

    auth_service = auth_service_health()

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
        # `database` has always meant "credentials present"; keep it for
        # compatibility and report live reachability separately.
        "database": supabase_ready(),
        "database_configured": supabase_ready(),
        "auth_service": auth_service,
        "auth_service_reachable": auth_service["reachable"],
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
