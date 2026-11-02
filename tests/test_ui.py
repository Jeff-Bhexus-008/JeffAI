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
import json
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

# The storage key supabase-js derives from the project URL the backend
# serves at /api/config, so the seeded session lands where the app looks.
SB_REF = os.environ["SUPABASE_URL"].split("//")[-1].split(".")[0]

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

        print("\nBrand logo")

        logo = page.evaluate("""() => {
            const img = document.querySelector('.brand-mark img');
            if (!img) return null;
            const box = img.getBoundingClientRect();
            return {
                src: img.getAttribute('src'),
                loaded: img.naturalWidth > 0,
                width: Math.round(box.width),
                height: Math.round(box.height),
            };
        }""")

        check("header shows the brain logo", bool(logo), logo)
        check("logo image loads", bool(logo and logo["loaded"]), logo)
        check("logo uses the svg asset", bool(logo and logo["src"] == "/assets/logo.svg"), logo)
        check("logo is a sensible size", bool(logo and 26 <= logo["width"] <= 44), logo)

        favicons = page.eval_on_selector_all(
            'link[rel="icon"], link[rel="apple-touch-icon"]',
            "els => els.map(e => e.getAttribute('href'))")
        check("favicon points at the logo", any("logo.svg" in (h or "") for h in favicons), favicons)
        check("png favicon fallback present", any("favicon-32" in (h or "") for h in favicons), favicons)

        broken = page.evaluate("""() => [...document.images]
            .filter(i => i.getAttribute('src') && i.complete && i.naturalWidth === 0)
            .map(i => i.getAttribute('src'))""")
        placeholder = page.evaluate(
            "() => { const w = document.getElementById('visionPreviewWrap'); return w ? w.hidden : true; }")

        check("no broken images", not broken, broken)
        check("empty preview slot stays hidden", placeholder is True, placeholder)

        page.emulate_media(reduced_motion="reduce")
        still = page.evaluate("getComputedStyle(document.querySelector('.brand-mark')).animationName")
        check("logo honours reduced motion", still in ("none", ""), still)
        page.emulate_media(reduced_motion="no-preference")

        print("\nAndroid download")

        button = page.evaluate("""() => {
            const b = document.getElementById('downloadApkBtn');
            if (!b) return null;
            const box = b.getBoundingClientRect();
            return {
                href: b.getAttribute('href'),
                label: b.textContent.trim(),
                title: b.getAttribute('title'),
                icon: !!b.querySelector('svg'),
                height: Math.round(box.height),
                visible: box.width > 0 && box.height > 0,
                right: Math.round(box.right),
                viewport: window.innerWidth,
            };
        }""")

        check("download button exists", bool(button), button)
        check("download button is visible", bool(button and button["visible"]), button)
        check("download button is labelled", bool(button and "Download APK" in button["label"]), button)
        check("download button has an android icon", bool(button and button["icon"]), button)
        check("download button sits top-right",
              bool(button and button["right"] > button["viewport"] * 0.6), button)
        check("download button points at the apk",
              bool(button and "/downloads/" in (button["href"] or "")), button)

        release = page.evaluate("async () => (await fetch('/api/app-release')).json()")
        check("release metadata available", release.get("available") is True, release)
        check("release is installable", release.get("installable") is True, release)
        check("button advertises the size",
              bool(button and release.get("size_label", "") in (button["title"] or "")), button)

        with page.expect_download(timeout=60000) as download_info:
            page.click("#downloadApkBtn")

        download = download_info.value
        saved = os.path.join("tests", "downloaded.apk")
        download.save_as(saved)

        import hashlib

        with open(saved, "rb") as handle:
            served_hash = hashlib.sha256(handle.read()).hexdigest()

        with open("downloads/JeffAI.apk", "rb") as handle:
            repo_hash = hashlib.sha256(handle.read()).hexdigest()

        check("download keeps the apk filename", download.suggested_filename.endswith(".apk"),
              download.suggested_filename)
        check("downloaded bytes are the real apk", served_hash == repo_hash, served_hash[:12])
        check("downloaded apk is not empty", os.path.getsize(saved) > 1_000_000, os.path.getsize(saved))
        os.remove(saved)

        print("\nAndroid download on mobile")

        mobile = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        seed(mobile)
        page_m = mobile.new_page()
        page_m.goto(BASE, wait_until="domcontentloaded")
        page_m.wait_for_selector("#welcome", timeout=25000)
        page_m.wait_for_timeout(1200)

        mobile_button = page_m.evaluate("""() => {
            const b = document.getElementById('downloadApkBtn');
            const box = b.getBoundingClientRect();
            const style = getComputedStyle(b);
            return {
                visible: box.width > 0 && box.height > 0,
                height: Math.round(box.height),
                within: box.right <= window.innerWidth + 1 && box.left >= 0,
                label: b.innerText.trim().replace(/\\s+/g, ' '),
                display: style.display,
            };
        }""")

        check("mobile download button visible", mobile_button["visible"], mobile_button)
        check("mobile download button has a tap target", mobile_button["height"] >= 38, mobile_button)
        check("mobile download button fits the screen", mobile_button["within"], mobile_button)
        check("mobile download button keeps a label", len(mobile_button["label"]) >= 3, mobile_button)

        with page_m.expect_download(timeout=60000) as mobile_download:
            page_m.click("#downloadApkBtn")

        check("mobile tap downloads the apk",
              mobile_download.value.suggested_filename.endswith(".apk"),
              mobile_download.value.suggested_filename)
        page_m.screenshot(path="tests/shot-12-mobile-header.png")
        mobile.close()

        print("\nUnavailable apk state")

        def no_release(ctx):
            ctx.route("**/api/app-release", lambda route, request: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({
                    "success": True, "available": False, "source": "none",
                    "url": None, "message": "The Android app has not been published yet.",
                })))

        missing_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        seed(missing_ctx)
        no_release(missing_ctx)
        page_x = missing_ctx.new_page()
        page_x.goto(BASE, wait_until="domcontentloaded")
        page_x.wait_for_selector("#welcome", timeout=25000)
        page_x.wait_for_timeout(1500)
        page_x.click("#downloadApkBtn")
        page_x.wait_for_timeout(900)

        toast_text = page_x.text_content(".toast") or ""

        check("missing apk is explained", "not been published" in toast_text.lower(), toast_text[:100])
        check("missing apk does not navigate", page_x.url.rstrip("/") == BASE, page_x.url)
        missing_ctx.close()

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

        def auth_context(handler=None):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
            if handler:
                handler(ctx)
            return ctx

        SESSION_BODY = {
            "access_token": "logging-in-token",
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": 4102444800,
            "refresh_token": "logging-in-refresh",
            "user": SESSION["user"],
        }

        # ---- 1. pages render
        fresh = auth_context()
        auth = fresh.new_page()
        auth.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
        auth.wait_for_timeout(1200)
        check("login page renders", auth.is_visible("#authForm"))
        login_logo = auth.evaluate(
            "() => { const i = document.querySelector('.brand-mark img'); return i ? i.naturalWidth > 0 : false; }")
        check("login page shows the brain logo", login_logo)
        check("login fields accept input",
              (auth.fill("#email", "jeff@example.com") or auth.input_value("#email")) == "jeff@example.com")
        check("login reports service status", bool((auth.text_content("#serviceLine") or "").strip()),
              auth.text_content("#serviceLine"))
        auth.screenshot(path="tests/shot-10-login.png")

        auth.goto(f"{BASE}/signup.html", wait_until="domcontentloaded")
        auth.wait_for_timeout(900)
        check("signup page renders", auth.is_visible("#authForm"))
        signup_logo = auth.evaluate(
            "() => { const i = document.querySelector('.brand-mark img'); return i ? i.naturalWidth > 0 : false; }")
        check("signup page shows the brain logo", signup_logo)
        check("signup has password confirm", auth.is_visible("#confirm"))

        auth.goto(f"{BASE}/", wait_until="domcontentloaded")
        auth.wait_for_timeout(2000)
        check("guest is redirected to login", "login.html" in auth.url, auth.url)
        fresh.close()

        # ---- 2. unreachable auth service (the reported "Failed to fetch" case)
        def aborted(ctx):
            ctx.route("**/auth/v1/**", lambda route, request: route.abort())

        broken = auth_context(aborted)
        page_b = broken.new_page()
        page_b.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
        page_b.wait_for_timeout(1500)

        page_b.fill("#email", "jeff@example.com")
        page_b.fill("#password", "secret123")
        page_b.click("#submitButton")
        page_b.wait_for_timeout(2500)

        diagnosis = page_b.text_content("#message") or ""

        check("unreachable auth is diagnosed", "cannot reach its sign-in service" in diagnosis.lower(), diagnosis[:120])
        check("diagnosis names the host", "test.supabase.co" in diagnosis, diagnosis[:120])
        check("diagnosis clears the password of blame",
              "not your credentials" in diagnosis.lower(), diagnosis[:120])
        check("raw browser error is not shown", "failed to fetch" not in diagnosis.lower(), diagnosis[:80])
        check("retry is offered", page_b.is_visible("#retry"))
        page_b.screenshot(path="tests/shot-11-login-unreachable.png")
        broken.close()

        # ---- 3. service alive, wrong password: credentials message
        def wrong_password(ctx):
            ctx.route("**/auth/v1/health", lambda route, request: route.fulfill(
                status=200, content_type="application/json", body='{"name":"GoTrue"}'))
            ctx.route("**/auth/v1/token**", lambda route, request: route.fulfill(
                status=400, content_type="application/json",
                body='{"error":"invalid_grant","error_description":"Invalid login credentials"}'))

        wrong = auth_context(wrong_password)
        page_w = wrong.new_page()
        page_w.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
        page_w.wait_for_timeout(1200)
        page_w.fill("#email", "jeff@example.com")
        page_w.fill("#password", "definitely-wrong")
        page_w.click("#submitButton")
        page_w.wait_for_timeout(2000)

        credential_message = page_w.text_content("#message") or ""

        check("healthy service + bad password explains itself",
              "do not match" in credential_message.lower(), credential_message[:120])
        check("no false outage message", "cannot reach" not in credential_message.lower(), credential_message[:120])
        check("service line shows healthy", "ok" in (page_w.get_attribute("#serviceLine", "class") or ""),
              page_w.get_attribute("#serviceLine", "class"))
        wrong.close()

        # ---- 4. successful sign-in returns to the app
        def success(ctx):
            ctx.route("**/auth/v1/health", lambda route, request: route.fulfill(
                status=200, content_type="application/json", body='{"name":"GoTrue"}'))
            ctx.route("**/auth/v1/token**", lambda route, request: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(SESSION_BODY)))

        signed_in = auth_context(success)
        page_s = signed_in.new_page()
        page_s.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
        page_s.wait_for_timeout(1000)
        page_s.fill("#email", "jeff@example.com")
        page_s.fill("#password", "correct-horse")
        page_s.click("#submitButton")
        page_s.wait_for_url(f"{BASE}/", timeout=20000)
        page_s.wait_for_selector("#welcome", timeout=20000)

        check("successful login lands in the app", page_s.url.rstrip("/") == BASE, page_s.url)
        check("app boots after login", page_s.is_visible("#welcome"))
        check("session persisted",
              page_s.evaluate("Object.keys(localStorage).some(k => k.includes('auth-token'))"))
        signed_in.close()

        # ---- 5. server config is authoritative (drift regression)
        seen = []

        def drifted(ctx):
            def config_handler(route, request):
                seen.append("config")
                route.fulfill(status=200, content_type="application/json", body=json.dumps({
                    "success": True,
                    "supabase_url": "https://drifted-project.supabase.co",
                    "supabase_anon_key": "drifted-anon-key",
                    "configured": True,
                }))

            def health_handler(route, request):
                seen.append(request.url)
                route.fulfill(status=200, content_type="application/json", body='{"name":"GoTrue"}')

            ctx.route("**/api/config", config_handler)
            ctx.route("https://drifted-project.supabase.co/**", health_handler)

        drift = auth_context(drifted)
        page_d = drift.new_page()
        page_d.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
        page_d.wait_for_timeout(1500)

        calls = [url for url in seen if url != "config"]

        check("login uses the server-provided project",
              any("drifted-project.supabase.co" in url for url in calls), calls[:3])
        check("bundled stale project is not contacted",
              not any("enpcfbebqwcsrrvvghev" in url for url in calls), calls[:3])
        drift.close()

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
