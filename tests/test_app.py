"""
JeffAI end-to-end route tests.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Runs the real Flask app against an in-memory stand-in for Supabase and a
fake AI engine, so every route can be exercised without network access,
API keys or a live database.

Usage:  python tests/test_app.py
"""

import io
import itertools
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter")


# =========================================================
# IN-MEMORY SUPABASE
# =========================================================

CLOCK = itertools.count(1)
BASE_TIME = datetime(2026, 1, 1, 9, 0, 0)


def now():
    return (BASE_TIME + timedelta(seconds=next(CLOCK))).isoformat()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.content = content or json.dumps(self._payload).encode()
        self.headers = headers or {"content-type": "application/json"}
        self.text = self.content.decode("utf-8", "ignore")

    def json(self):
        return self._payload


class FakeSupabase:
    """Tiny PostgREST + storage implementation."""

    def __init__(self):
        self.tables = {
            "conversations": [],
            "messages": [],
            "memories": [],
            "documents": [],
            "images": [],
        }
        self.storage = {}
        self.auth_health_status = 200

    # ---------------- filters ----------------

    @staticmethod
    def _match(row, params):
        reserved = {"select", "order", "limit", "offset"}

        for key, value in (params or {}).items():
            if key in reserved:
                continue

            if not isinstance(value, str) or value.startswith("select"):
                continue

            if value.startswith("eq."):
                if str(row.get(key)) != value[3:]:
                    return False
            elif value.startswith("gte."):
                if str(row.get(key) or "") < value[4:]:
                    return False
            elif value.startswith("lte."):
                if str(row.get(key) or "") > value[4:]:
                    return False

        return True

    @staticmethod
    def _sort(rows, params):
        order = (params or {}).get("order")

        if not order:
            return rows

        field = order.split(".")[0]
        descending = "desc" in order

        return sorted(
            rows,
            key=lambda row: str(row.get(field) or ""),
            reverse=descending,
        )

    def _table(self, url):
        for name in self.tables:
            if url.endswith(f"/rest/v1/{name}") or f"/rest/v1/{name}?" in url:
                return name
        return None

    # ---------------- HTTP verbs ----------------

    def get(self, url, headers=None, params=None, timeout=None, **kwargs):
        if "/auth/v1/health" in url:
            if self.auth_health_status != 200:
                return FakeResponse(self.auth_health_status, {"message": "service unavailable"})
            return FakeResponse(200, {"name": "GoTrue", "version": "v2.test"})

        if "/auth/v1/user" in url:
            return FakeResponse(200, {"id": "user-1", "email": "jeff@example.com"})

        if "/storage/v1/object/sign/" in url:
            return FakeResponse(200, {"signedURL": "/object/sign/test?token=abc"})

        table = self._table(url)

        if not table:
            return FakeResponse(404, {"message": "not found"})

        rows = [row for row in self.tables[table] if self._match(row, params)]
        rows = self._sort(rows, params)

        limit = (params or {}).get("limit")
        if limit:
            rows = rows[: int(limit)]

        return FakeResponse(200, [dict(row) for row in rows])

    def post(self, url, headers=None, params=None, json=None, data=None, timeout=None, **kwargs):
        if "/storage/v1/object/sign/" in url:
            path = url.split("/storage/v1/object/sign/", 1)[1]
            return FakeResponse(200, {"signedURL": f"/object/sign/{path}?token=abc"})

        if "/storage/v1/object/" in url:
            path = url.split("/storage/v1/object/", 1)[1]
            self.storage[path] = data if isinstance(data, bytes) else b""
            return FakeResponse(200, {"Key": path})

        table = self._table(url)

        if not table:
            return FakeResponse(404, {"message": "not found"})

        row = dict(json or {})
        row.setdefault("id", str(uuid.uuid4()))
        row.setdefault("created_at", now())
        row.setdefault("updated_at", row["created_at"])
        row.setdefault("user_id", "user-1")

        self.tables[table].append(row)

        return FakeResponse(201, [dict(row)])

    def patch(self, url, headers=None, params=None, json=None, timeout=None, **kwargs):
        table = self._table(url)

        if not table:
            return FakeResponse(404, {"message": "not found"})

        updated = []

        for row in self.tables[table]:
            if self._match(row, params):
                row.update(json or {})
                row["updated_at"] = now()
                updated.append(dict(row))

        return FakeResponse(200, updated)

    def delete(self, url, headers=None, params=None, timeout=None, **kwargs):
        if "/storage/v1/object/" in url:
            path = url.split("/storage/v1/object/", 1)[1]
            self.storage.pop(path, None)
            return FakeResponse(200, {})

        table = self._table(url)

        if not table:
            return FakeResponse(404, {"message": "not found"})

        keep = [row for row in self.tables[table] if not self._match(row, params)]
        removed = len(self.tables[table]) - len(keep)
        self.tables[table] = keep

        return FakeResponse(200, [{}] * removed)


FAKE_DB = FakeSupabase()


# =========================================================
# PATCH THE APP DEPENDENCIES
# =========================================================

import backend.supabase_client as supabase_client
import backend.ai.context as ai_context
import backend.ai.images as ai_images
import backend.routes.chat as chat_routes
import backend.routes.tools as tool_routes
import backend.ai.engine as engine

for module in (supabase_client, ai_context, ai_images, chat_routes, tool_routes):
    if hasattr(module, "requests"):
        module.requests = FAKE_DB


def fake_user():
    return {"id": "user-1", "email": "jeff@example.com"}


def no_user():
    return None


def install_auth(user_callable):
    for module in (chat_routes, tool_routes):
        module.get_user = user_callable
        module.get_token = lambda: "test-token"


install_auth(fake_user)


# ---------------- AI ----------------

ENGINE_STATE = {"mode": "normal"}


def fake_respond(prompt, model=None, mode="chat", temperature=0.7):
    if ENGINE_STATE["mode"] == "rate_limit":
        raise engine.AIUnavailable("Error code: 429 rate_limit_exceeded")
    if ENGINE_STATE["mode"] == "down":
        raise engine.AIUnavailable("connection reset")
    return "## Answer\n\nThis is a **test** reply.\n\n```python\nprint('hi')\n```"


def fake_stream(messages, model=None, mode="chat", temperature=0.7):
    if ENGINE_STATE["mode"] == "rate_limit":
        raise engine.AIUnavailable("429 too many requests")
    if ENGINE_STATE["mode"] == "down":
        raise engine.AIUnavailable("provider offline")

    for piece in ["Hello", ", ", "this ", "is ", "streamed."]:
        yield piece


def fake_vision(image_data_url, question, model=None):
    if not image_data_url.startswith("data:image/"):
        raise RuntimeError("bad image")
    return "The image shows a whiteboard with three bullet points."


def fake_transcribe(file_bytes, filename="audio.webm", mimetype=None):
    if not file_bytes:
        raise engine.AIUnavailable("no audio")
    return "This is a transcribed sentence."


engine.jeffai.respond = fake_respond
engine.jeffai.stream = fake_stream
engine.jeffai.vision = fake_vision
engine.jeffai.transcribe = fake_transcribe

chat_routes.jeffai = engine.jeffai
tool_routes.jeffai = engine.jeffai


# ---------------- images ----------------

def sample_png(size=256):
    """A real PNG so the UI test renders an actual image."""

    from PIL import Image

    image = Image.new("RGB", (size, size))
    pixels = image.load()

    for x in range(size):
        for y in range(size):
            pixels[x, y] = (
                int(120 + (x / size) * 115),
                int(70 + (y / size) * 80),
                int(200 - (x / size) * 90),
            )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    return buffer.getvalue()


tool_routes.generate_image = lambda prompt, style="auto", aspect="square": (
    sample_png(),
    "image/png",
    {"provider": "test", "width": 1024, "height": 1024},
)


# =========================================================
# TEST RUNNER
# =========================================================

from backend.app import app

client = app.test_client()

PASSED = []
FAILED = []


def check(name, condition, detail=""):
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append((name, detail))
        print(f"  FAIL  {name}  {detail}")


def body(response):
    try:
        return response.get_json()
    except Exception:
        return {}


def test_health_and_models():
    print("\nHealth and model catalogue")

    health = client.get("/api/health")
    payload = body(health)
    check("health returns 200", health.status_code == 200, health.status_code)
    check("health names JeffAI", payload.get("name") == "JeffAI", payload)
    check("health credits the creator", "Jeff Bhexus" in payload.get("creator", ""), payload.get("creator"))

    models = client.get("/api/models")
    catalogue = body(models)
    check("models returns 200", models.status_code == 200)
    check("models list is populated", len(catalogue.get("models", [])) >= 4, catalogue)
    check("default model exists", catalogue["models"][0]["key"] == "jeff-balanced", catalogue["models"][:1])

    status = client.get("/api/status")
    check("status reports version", body(status).get("version") == "2.0.0")


def test_client_config():
    print("\nClient configuration")

    response = client.get("/api/config")
    payload = body(response)

    check("config returns 200", response.status_code == 200, response.status_code)
    check("config carries the supabase url", payload.get("supabase_url", "").startswith("https://"), payload)
    check("config carries the anon key", bool(payload.get("supabase_anon_key")), payload)
    check("config never exposes a service key",
          "service_role" not in json.dumps(payload).lower(), payload)
    check("config is not cached",
          "no-store" in response.headers.get("Cache-Control", ""),
          response.headers.get("Cache-Control"))

    health = body(client.get("/api/health"))

    check("health reports auth service block", isinstance(health.get("auth_service"), dict), health.get("auth_service"))
    check("health reports a healthy auth service",
          health.get("auth_service_reachable") is True, health.get("auth_service"))

    from backend.supabase_client import auth_service_health

    FAKE_DB.auth_health_status = 503
    down = auth_service_health(force=True)

    check("degraded auth service detected", down["reachable"] is False, down)
    check("degraded detail is explicit", "503" in down["detail"], down)

    FAKE_DB.auth_health_status = 200
    back = auth_service_health(force=True)
    check("recovered auth service detected", back["reachable"] is True, back)
    check("health still reports configuration",
          health.get("database_configured") is True, health.get("database"))

    status = body(client.get("/api/status"))
    check("status still responds", status.get("success") is True, status)


def test_static_pages():
    print("\nFrontend delivery")

    root = client.get("/")
    html = root.get_data(as_text=True)
    check("index served", root.status_code == 200)
    check("index has app shell", 'id="app"' in html)
    check("index loads module", '/app/main.js' in html)
    check("index credits Jeff Bhexus", "Jeff Bhexus" in html)

    login_html = client.get("/login.html").get_data(as_text=True)
    check("login uses the shared auth controller", "/app/auth.js" in login_html)
    check("login exposes service status", 'id="serviceLine"' in login_html)

    for asset in ["/app/styles.css", "/app/main.js", "/app/markdown.js",
                  "/app/env.js", "/app/auth.js",
                  "/app/auth.css", "/vendor/marked.min.js", "/vendor/supabase.js",
                  "/config.js", "/login.html", "/signup.html"]:
        response = client.get(asset)
        check(f"served {asset}", response.status_code == 200, response.status_code)

    missing = client.get("/app/does-not-exist.js")
    check("missing asset is a real 404", missing.status_code == 404, missing.status_code)


def test_chat_flow():
    print("\nChat flow")

    ENGINE_STATE["mode"] = "normal"

    response = client.post("/api/chat", json={"message": "Hello JeffAI"})
    payload = body(response)

    check("chat returns 200", response.status_code == 200, payload)
    check("chat returns a reply", "Answer" in payload.get("response", ""), payload)
    check("chat creates a conversation", bool(payload.get("conversation_id")), payload)

    conversation_id = payload["conversation_id"]

    stored = client.get(f"/api/conversations/{conversation_id}/messages")
    messages = body(stored).get("messages", [])

    check("messages stored", len(messages) >= 2, len(messages))
    check("user message stored", messages[0]["role"] == "user", messages[:1])
    check("assistant message stored", messages[-1]["role"] == "assistant", messages[-1:])

    conversations = body(client.get("/api/conversations")).get("conversations", [])
    check("conversation listed", any(item["id"] == conversation_id for item in conversations))

    renamed = client.patch(f"/api/conversations/{conversation_id}", json={"title": "Renamed chat"})
    check("rename works", body(renamed).get("success") is True, body(renamed))

    second = body(client.post("/api/chat", json={"message": "Second question", "conversation_id": conversation_id}))
    check("follow-up reuses conversation", second.get("conversation_id") == conversation_id)

    before = len(body(client.get(f"/api/conversations/{conversation_id}/messages")).get("messages", []))

    regenerated = body(client.post("/api/chat", json={"conversation_id": conversation_id, "regenerate": True}))
    after = body(client.get(f"/api/conversations/{conversation_id}/messages")).get("messages", [])

    check("regenerate answers", bool(regenerated.get("response")), regenerated)
    check("regenerate replaces the last reply", len(after) == before, f"{before} -> {len(after)}")

    all_messages = body(client.get(f"/api/conversations/{conversation_id}/messages")).get("messages", [])
    first_user = next(item for item in all_messages if item["role"] == "user")

    edited = body(client.post("/api/chat", json={
        "message": "Edited question",
        "conversation_id": conversation_id,
        "edit_message_id": first_user["id"],
    }))

    check("edit answers", bool(edited.get("response")), edited)

    trimmed = body(client.get(f"/api/conversations/{conversation_id}/messages")).get("messages", [])
    check("edit truncates later messages", len(trimmed) <= 2, len(trimmed))
    check("edited text kept", any("Edited question" in item["content"] for item in trimmed), trimmed)

    empty = client.post("/api/chat", json={"message": "   "})
    check("empty message rejected", empty.status_code == 400, empty.status_code)


def test_streaming():
    print("\nStreaming")

    ENGINE_STATE["mode"] = "normal"

    response = client.post("/api/chat/stream", json={"message": "Stream please"})
    raw = response.get_data(as_text=True)

    check("stream returns 200", response.status_code == 200, response.status_code)
    check("stream content type", "text/event-stream" in response.headers.get("Content-Type", ""), response.headers.get("Content-Type"))
    check("stream sends meta", "event: meta" in raw, raw[:120])
    check("stream sends deltas", raw.count("event: delta") >= 4, raw.count("event: delta"))
    check("stream completes", "event: done" in raw, raw[-160:])

    conversation = None
    for line in raw.splitlines():
        if line.startswith("data:") and "conversation_id" in line:
            try:
                conversation = json.loads(line[5:].strip()).get("conversation_id")
            except Exception:
                pass
            if conversation:
                break

    check("stream returns conversation id", bool(conversation), conversation)

    if conversation:
        messages = body(client.get(f"/api/conversations/{conversation}/messages")).get("messages", [])
        check("streamed reply persisted", any("streamed" in item["content"] for item in messages), messages)

    ENGINE_STATE["mode"] = "rate_limit"
    limited = client.post("/api/chat/stream", json={"message": "Again"})
    limited_text = limited.get_data(as_text=True)
    check("stream rate limit reported", "rate_limit" in limited_text, limited_text[-160:])

    ENGINE_STATE["mode"] = "down"
    down = client.post("/api/chat/stream", json={"message": "Again"})
    check("stream failure reported", "event: error" in down.get_data(as_text=True))

    ENGINE_STATE["mode"] = "normal"


def test_ai_errors():
    print("\nAI failure handling")

    ENGINE_STATE["mode"] = "rate_limit"
    limited = client.post("/api/chat", json={"message": "Hello"})
    payload = body(limited)

    check("rate limit returns 200", limited.status_code == 200, limited.status_code)
    check("rate limit flagged", payload.get("error_type") == "rate_limit", payload)
    check("rate limit is friendly", "taking a short break" in payload.get("response", ""), payload)

    ENGINE_STATE["mode"] = "down"
    down = client.post("/api/chat", json={"message": "Hello"})
    check("outage returns 503", down.status_code == 503, down.status_code)
    check("outage message clear", "temporarily unavailable" in body(down).get("error", ""), body(down))

    ENGINE_STATE["mode"] = "normal"


def test_memories():
    print("\nMemory")

    created = body(client.post("/api/memories", json={"memory": "Prefers short answers"}))
    check("memory created", created.get("success") is True, created)

    listed = body(client.get("/api/memories")).get("memories", [])
    check("memory listed", any("short answers" in item["memory"] for item in listed), listed)

    memory_id = next(item["id"] for item in listed if "short answers" in item["memory"])
    removed = client.delete(f"/api/memories/{memory_id}")
    check("memory deleted", body(removed).get("success") is True)

    after = body(client.get("/api/memories")).get("memories", [])
    check("memory really gone", all(item["id"] != memory_id for item in after), after)

    auto = client.post("/api/chat", json={"message": "Remember that my name is Jeff"})
    check("auto memory capture runs", auto.status_code == 200)
    stored = body(client.get("/api/memories")).get("memories", [])
    check("auto memory stored", any("my name is Jeff" in item["memory"] for item in stored), stored)


def test_images():
    print("\nImage studio")

    generated = client.post("/api/images/generate", json={
        "prompt": "A neon skyline",
        "style": "cinematic",
        "aspect": "wide",
    })
    payload = body(generated)

    check("image generated", generated.status_code == 200, payload)
    check("image returns data url", payload.get("image", {}).get("data_url", "").startswith("data:image/"), list(payload.get("image", {})))
    check("image saved to storage", bool(payload.get("image", {}).get("saved_id")), payload.get("image", {}))

    listing = body(client.get("/api/images")).get("images", [])
    check("image gallery lists it", len(listing) >= 1, listing)

    if listing:
        image_id = listing[0]["id"]
        deleted = client.delete(f"/api/images/{image_id}")
        check("image deleted", body(deleted).get("success") is True, body(deleted))

    empty = client.post("/api/images/generate", json={"prompt": "   "})
    check("empty prompt rejected", empty.status_code == 400, empty.status_code)


def test_vision_and_voice():
    print("\nImage understanding and voice")

    image_bytes = b"\x89PNG\r\n\x1a\n" + b"0" * 128
    vision = client.post(
        "/api/vision",
        data={
            "image": (io.BytesIO(image_bytes), "whiteboard.png"),
            "question": "What is on the board?",
        },
        content_type="multipart/form-data",
    )
    payload = body(vision)

    check("vision returns 200", vision.status_code == 200, payload)
    check("vision answers", "whiteboard" in payload.get("answer", ""), payload)

    no_image = client.post("/api/vision", data={}, content_type="multipart/form-data")
    check("vision needs an image", no_image.status_code == 400, no_image.status_code)

    audio = client.post(
        "/api/transcribe",
        data={"audio": (io.BytesIO(b"fake-audio-bytes"), "note.webm")},
        content_type="multipart/form-data",
    )
    check("transcribe returns 200", audio.status_code == 200, body(audio))
    check("transcribe returns text", "transcribed" in body(audio).get("text", ""), body(audio))

    no_audio = client.post("/api/transcribe", data={}, content_type="multipart/form-data")
    check("transcribe needs audio", no_audio.status_code == 400, no_audio.status_code)


def test_documents():
    print("\nDocuments")

    upload = client.post(
        "/api/documents",
        data={"file": (io.BytesIO(b"Quarterly report: revenue up 12 percent."), "report.txt")},
        content_type="multipart/form-data",
    )
    payload = body(upload)

    check("document uploaded", upload.status_code == 200, payload)
    check("document returns record", bool(payload.get("document", {}).get("id")), payload)

    document_id = payload.get("document", {}).get("id")

    listing = body(client.get("/api/documents")).get("documents", [])
    check("documents listed", any(item["id"] == document_id for item in listing), listing)

    analysis = body(client.post(f"/api/documents/{document_id}/analyze", json={"task": "summary"}))
    check("document analysed", analysis.get("success") is True, analysis)
    check("analysis has content", bool(analysis.get("answer")), analysis)

    files = body(client.get("/api/files"))
    check("files bundles documents", any(item["id"] == document_id for item in files.get("documents", [])), files.keys())
    check("files bundles images", isinstance(files.get("images"), list))

    pdf = client.post("/api/convert/text-to-pdf", json={"text": "Hello PDF", "title": "Notes"})
    check("pdf produced", pdf.status_code == 200, pdf.status_code)
    check("pdf mimetype", pdf.headers.get("Content-Type", "").startswith("application/pdf"), pdf.headers.get("Content-Type"))

    deleted = client.delete(f"/api/documents/{document_id}")
    check("document deleted", body(deleted).get("success") is True, body(deleted))

    bad = client.post(
        "/api/documents",
        data={"file": (io.BytesIO(b"nope"), "virus.exe")},
        content_type="multipart/form-data",
    )
    check("unsupported file rejected", bad.status_code == 400, bad.status_code)


def test_auth_required():
    print("\nAuthentication")

    install_auth(no_user)

    protected = [
        ("/api/conversations", "get"),
        ("/api/chat", "post"),
        ("/api/chat/stream", "post"),
        ("/api/memories", "get"),
        ("/api/documents", "get"),
        ("/api/files", "get"),
        ("/api/images", "get"),
    ]

    for path, method in protected:
        response = getattr(client, method)(path, json={"message": "hi"})
        check(f"{method.upper()} {path} needs auth", response.status_code == 401, response.status_code)

    install_auth(fake_user)

    public = client.get("/api/health")
    check("health stays public", public.status_code == 200)


def test_engine_router():
    print("\nProvider router")

    router = engine.JeffAI()

    chain = router.candidates("jeff-fast")
    check("requested model comes first", chain[0][1] == engine.MODELS["jeff-fast"]["id"], chain)
    check("failover includes openrouter", any(provider == "openrouter" for provider, _ in chain), chain)

    unknown = router.candidates("does-not-exist")
    check("unknown model falls back", unknown[0][1] == engine.MODELS[engine.DEFAULT_MODEL]["id"], unknown)

    saved = {key: os.environ.get(key) for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY")}

    for key in saved:
        os.environ.pop(key, None)

    empty_router = engine.JeffAI()
    check("no keys means no candidates", empty_router.candidates() == [], empty_router.candidates())

    try:
        empty_router.respond("hello")
        ok = False
    except engine.AIUnavailable:
        ok = True

    check("no keys raises politely", ok)

    for key, value in saved.items():
        if value:
            os.environ[key] = value


def main():
    print("JeffAI end-to-end checks")
    print("=" * 52)

    test_health_and_models()
    test_client_config()
    test_static_pages()
    test_chat_flow()
    test_streaming()
    test_ai_errors()
    test_memories()
    test_images()
    test_vision_and_voice()
    test_documents()
    test_auth_required()
    test_engine_router()

    print("\n" + "=" * 52)
    print(f"{len(PASSED)} passed, {len(FAILED)} failed")

    if FAILED:
        for name, detail in FAILED:
            print(f"  - {name}: {detail}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
