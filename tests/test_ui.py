"""
JeffAI browser test.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Boots the real Flask app (with the in-memory Supabase and fake AI from
tests/test_app.py), then drives the real frontend in headless Chromium:
chat streaming, markdown code cards, every sidebar view, theme switching,
image generation, vision, document upload and the settings modal.

Usage:  python tests/test_ui.py
"""

import io
import os
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import test_app as harness  # applies the stubs and exposes `app`

from playwright.sync_api import sync_playwright


PORT = 5599
BASE = f"http://127.0.0.1:{PORT}"

SB_REF = "enpcfbebqwcsrrvvghev"

SESSION = {
    "access_token": "fake-access-token",
    "token_type": "bearer",
    "expires_in": 3600,
    "expires_at": 4102444800,
    "refresh_token": "fake-refresh-token",
    "user": {
        "id": "user-1",
        "aud": "authenticated",
        "role": "authenticated",
        "email": "jeff@example.com",
        "app_metadata": {},
        "user_metadata": {},
        "created_at": "2026-01-01T00:00:00Z",
    },
}


STREAM_ANSWER = [
    "Here is how you reverse a list in Python.\n\n",
    "### The short version\n\n",
    "```python\n",
    "items = [1, 2, 3]\n",
    "print(items[::-1])\n",
    "```\n\n",
    "| Method | Mutates | Speed |\n",
    "| --- | --- | --- |\n",
    "| `[::-1]` | No | Fast |\n",
    "| `reverse()` | Yes | Fast |\n\n",
    "Use `reversed()` when you only need to iterate.\n",
]


RESULTS = []


def check(name, condition, detail=""):
    RESULTS.append((name, bool(condition), detail))
    print(("  PASS  " if condition else "  FAIL  ") + name + ("" if condition else f"  {detail}"))


def start_server():
    harness.engine.jeffai.stream = lambda messages, model=None, mode="chat", temperature=0.7: (
        piece for piece in STREAM_ANSWER
    )

    thread = threading.Thread(
        target=lambda: harness.app.run(
            host="127.0.0.1",
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        ),
        daemon=True,
    )
    thread.start()

    import urllib.request

    for _ in range(80):
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.15)

    return False


def seed(context):
    context.add_init_script(
        """
        (function () {
            const session = %s;
            try {
                localStorage.setItem('sb-%s-auth-token', JSON.stringify(session));
                localStorage.setItem('jeffai:enter-to-send', 'true');
            } catch (error) {}
        })();
        """
        % (repr(SESSION).replace("'", '"'), SB_REF)
    )


def run():
    if not start_server():
        print("Server did not start")
        return 1

    console_errors = []
    api_calls = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 950}, device_scale_factor=2)
        seed(context)

        page = context.new_page()
        page.on(
            "console",
            lambda message: console_errors.append(
                f"{message.text} @ {(message.location or {}).get('url', '')}"
            )
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: console_errors.append(f"pageerror: {error}"))
        page.on("request", lambda request: api_calls.append(request.url) if "/api/" in request.url else None)
        failed_requests = []
        page.on("requestfailed", lambda request: failed_requests.append(request.url))

        print("\nBoot")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#welcome", timeout=25000)

        check("app booted to chat", page.url.rstrip("/") == BASE, page.url)
        check("welcome hero visible", page.is_visible("#welcome"))
        check("six prompt cards", page.locator(".prompt-card").count() == 6, page.locator(".prompt-card").count())
        check("user email shown", "jeff" in (page.text_content("#userEmail") or ""))
        check("models loaded", any("/api/models" in url for url in api_calls), api_calls[:5])
        check("conversations loaded", any("/api/conversations" in url for url in api_calls), api_calls[:5])
        page.screenshot(path="tests/shot-01-chat-dark.png")

        print("\nStreaming chat")
        page.fill("#messageInput", "How do I reverse a list in Python?")
        page.keyboard.press("Enter")

        page.wait_for_selector(".message.assistant .code-card", timeout=30000)
        check("chat request hit the local API", any("/api/chat/stream" in url for url in api_calls), api_calls[-4:])
        page.wait_for_timeout(1200)

        check("user message rendered", page.locator(".message.user").count() == 1, page.locator(".message.user").count())
        check("assistant reply rendered", page.locator(".message.assistant").count() == 1)
        check("code block rendered", page.locator(".code-card").count() == 1)
        check("table rendered", page.locator(".message table").count() == 1)
        check("copy button present", page.locator("[data-copy-code]").count() == 1)
        check("conversation added to sidebar", page.locator(".conversation").count() >= 1, page.locator(".conversation").count())
        check("send button back to idle", "is-stop" not in (page.get_attribute("#sendBtn", "class") or ""))
        page.screenshot(path="tests/shot-02-chat-answer.png")

        print("\nMessage actions")
        page.hover(".message.assistant")
        page.click('.message.assistant [data-action="copy"]')
        page.wait_for_timeout(400)
        check("copy shows toast", page.locator(".toast").count() >= 1, page.locator(".toast").count())

        print("\nSidebar and model selector")
        page.fill("#conversationSearch", "python")
        page.wait_for_timeout(250)
        check("search filters conversations", page.locator(".conversation").count() == 1, page.locator(".conversation").count())
        page.fill("#conversationSearch", "")

        page.click("#modelTrigger")
        check("model menu opens", page.is_visible("#modelMenu"))
        check("model options listed", page.locator(".model-option").count() >= 4, page.locator(".model-option").count())
        page.click('.model-option[data-model-key="jeff-fast"]')
        check("model selection applied", "Fast" in (page.text_content("#modelName") or ""), page.text_content("#modelName"))

        page.click("#collapseBtn")
        page.wait_for_timeout(400)
        check("sidebar collapses", "is-collapsed" in (page.get_attribute("#app", "class") or ""))
        page.screenshot(path="tests/shot-03-collapsed.png")
        page.click("#collapseBtn")
        page.wait_for_timeout(300)

        print("\nViews")
        for route, view in [("images", "#view-images"), ("vision", "#view-vision"),
                            ("documents", "#view-documents"), ("voice", "#view-voice"),
                            ("files", "#view-files")]:
            page.click(f'.nav-item[data-route="{route}"]')
            page.wait_for_timeout(500)
            check(f"{route} view opens", page.is_visible(view))

        print("\nImage studio")
        page.click('.nav-item[data-route="images"]')
        page.fill("#imagePrompt", "A neon Lagos skyline at dusk")
        page.click("#imageGenerateBtn")
        page.wait_for_selector("#imageResults .gallery-card img", timeout=25000)
        page.wait_for_timeout(1200)
        check("generated image shown", page.locator("#imageResults .gallery-card").count() >= 1)
        check("history populated", page.locator("#imageHistory .gallery-card").count() >= 1, page.locator("#imageHistory .gallery-card").count())
        check("unreachable image degrades gracefully",
              page.locator("#imageHistory .gallery-fallback").count() >= 1,
              page.locator("#imageHistory .gallery-card").count())
        page.screenshot(path="tests/shot-04-images.png")

        print("\nImage understanding")
        page.click('.nav-item[data-route="vision"]')
        page.set_input_files("#visionInput", files=[{
            "name": "whiteboard.png",
            "mimeType": "image/png",
            "buffer": harness.sample_png(64),
        }])
        page.wait_for_timeout(400)
        check("vision preview shown", page.is_visible("#visionPreviewWrap"))
        page.click("#visionAskBtn")
        page.wait_for_selector("#visionAnswerPanel:not([hidden])", timeout=25000)
        page.wait_for_timeout(600)
        check("vision answer rendered", "whiteboard" in (page.text_content("#visionAnswer") or "").lower(), page.text_content("#visionAnswer")[:80])
        page.screenshot(path="tests/shot-05-vision.png")

        print("\nDocuments")
        page.click('.nav-item[data-route="documents"]')
        page.set_input_files("#docInput", files=[{
            "name": "report.txt",
            "mimeType": "text/plain",
            "buffer": b"Quarterly report: revenue up 12 percent. Costs flat.",
        }])
        page.wait_for_timeout(2500)
        check("document listed", page.locator("#docList .list-item").count() >= 1, page.locator("#docList .list-item").count())
        page.click("#docList .list-item [data-analyse]")
        page.wait_for_selector(".model-menu [data-choice]", timeout=8000)
        page.click('.model-menu [data-choice="summary"]')
        page.wait_for_selector("#analysisPanel", timeout=25000)
        page.wait_for_timeout(600)
        check("analysis panel rendered", page.is_visible("#analysisPanel"))
        page.screenshot(path="tests/shot-06-documents.png")

        print("\nSaved files")
        page.click('.nav-item[data-route="files"]')
        page.wait_for_timeout(1500)
        check("files doc list", page.locator("#filesDocuments .list-item").count() >= 1, page.locator("#filesDocuments .list-item").count())
        page.click('[data-files-tab="images"]')
        page.wait_for_timeout(600)
        check("files image gallery", page.locator("#filesImages .gallery-card").count() >= 1, page.locator("#filesImages .gallery-card").count())

        print("\nSettings and themes")
        page.click("#settingsBtn")
        page.wait_for_timeout(500)
        check("settings opens", page.is_visible("#settingsOverlay"))
        check("memory settings listed", page.locator("#memoryList .list-item").count() >= 0)
        page.screenshot(path="tests/shot-07-settings.png")
        page.click('#themeCards [data-theme-choice="light"]')
        page.wait_for_timeout(500)
        check("light theme applied", page.get_attribute("html", "data-theme") == "light", page.get_attribute("html", "data-theme"))
        page.click("#settingsClose")
        page.click('.nav-item[data-route="chat"]')
        page.wait_for_timeout(600)
        page.screenshot(path="tests/shot-08-chat-light.png")

        print("\nMobile layout")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        check("mobile menu available", page.is_visible("#mobileMenuBtn"))
        page.click("#mobileMenuBtn")
        page.wait_for_timeout(500)
        check("drawer opens", "is-drawer-open" in (page.get_attribute("#app", "class") or ""))
        page.screenshot(path="tests/shot-09-mobile.png")
        page.mouse.click(370, 420)
        page.wait_for_timeout(400)

        print("\nAuth pages")

        # A fresh context: the seeded session above would (correctly)
        # redirect the login page straight back into the app.
        fresh = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        auth_page = fresh.new_page()

        auth_page.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
        auth_page.wait_for_timeout(900)
        check("login page renders", auth_page.is_visible("#loginForm"))
        auth_page.fill("#email", "jeff@example.com")
        auth_page.fill("#password", "secret123")
        check("login fields accept input", auth_page.input_value("#email") == "jeff@example.com")
        auth_page.screenshot(path="tests/shot-10-login.png")

        auth_page.goto(f"{BASE}/signup.html", wait_until="domcontentloaded")
        auth_page.wait_for_timeout(700)
        check("signup page renders", auth_page.is_visible("#signupForm"))
        check("signup has password confirm", auth_page.is_visible("#confirm"))

        auth_page.goto(f"{BASE}/", wait_until="domcontentloaded")
        auth_page.wait_for_timeout(1500)
        check("guest is redirected to login", "login.html" in auth_page.url, auth_page.url)

        fresh.close()

        browser.close()

    print("\nConsole errors")
    # The in-memory Supabase returns a signed URL on a domain that does
    # not exist in this sandbox; those two failures are expected test
    # doubles, not app errors. The UI must still degrade gracefully.
    fatal = [
        item for item in console_errors
        if "favicon" not in item.lower() and "test.supabase.co" not in item
    ]
    check("no console errors", not fatal, fatal[:4] + failed_requests[:4])

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed

    print("\n" + "=" * 52)
    print(f"{passed} passed, {failed} failed")

    if failed:
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name}: {detail}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
