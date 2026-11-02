# JeffAI

A personal AI assistant for learning, coding, writing, research, documents,
images and voice — with a premium dark/light interface and a resilient
multi-provider AI backend.

**Created by Amedu Vincent Onjefu, popularly known as Jeff Bhexus.**

---

## What JeffAI does

| Capability | Where |
| --- | --- |
| Streaming chat with formatted Markdown, syntax-highlighted code and one-click copy | Chat |
| Model selection with automatic provider failover (Groq → OpenRouter) | Chat header |
| Answer modes: Auto, Concise, Tutor, Code, Writer, Research | Composer → sliders |
| Conversation history with search, rename and delete | Sidebar |
| Image generation with styles and aspect ratios | Image Studio |
| Image understanding (screenshots, charts, notes, photos) | Image Understanding |
| PDF / DOCX / TXT upload, summary, key points, action items, study questions | Document Tools |
| Text → PDF export | Document Tools |
| Voice input with server-side transcription, spoken replies, voice picker | Voice Assistant |
| Long-term memory that the model can use, with manual add/remove | Settings |
| Saved documents and generated images in one library | Saved Files |

Everything is available on mobile, tablet and desktop, and inside the Android
app built with Capacitor.

---

## Architecture

```
frontend/
  index.html          App shell: sidebar, views, composer, modals
  app/styles.css      Design tokens (dark + light), layout, components
  app/main.js         State, routing, chat streaming, all views
  app/markdown.js     Markdown → safe HTML with highlight.js code cards
  app/auth.css        Shared styling for the auth pages
  login.html          Sign in
  signup.html         Create account
  vendor/             Local copies of supabase-js, marked, DOMPurify,
                      highlight.js (no CDN dependency, Capacitor-safe)
  config.js           Supabase project URL + anon key

backend/
  app.py              Flask app factory, static serving, health, errors
  routes/chat.py      Auth-scoped conversations, messages, memories,
                      documents, PDF export, chat + chat streaming
  routes/tools.py     Models, image studio, vision, transcription, files
  supabase_client.py  Shared Supabase auth + REST helpers
  ai/engine.py        Model router: failover, streaming, vision, audio
  ai/models.py        Model catalogue and vision/transcription fallbacks
  ai/prompts.py       Identity, creator credit, answer modes, prompt build
  ai/context.py       Memory / history / document context assembly
  ai/images.py        Image generation and storage

supabase/schema.sql   Optional `images` table for the generated-image gallery
tests/test_app.py     End-to-end route tests with a stubbed Supabase + AI
tests/test_ui.py      Headless-browser test of the real UI
```

**Request flow:** the browser holds the Supabase session and sends
`Authorization: Bearer <token>` to Flask. Flask re-uses that token for
PostgREST and Storage calls, so row level security always applies to the
signed-in user. The AI engine tries the chosen model first, then the default
Groq model, then OpenRouter; a failed provider never breaks the app.

---

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in the keys below
python main.py              # http://localhost:5000
```

Open `http://localhost:5000`. The frontend is served by Flask, so the API is
same-origin — no CORS or base-URL juggling.

### Environment variables

| Name | Required | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | yes | Supabase project URL |
| `SUPABASE_KEY` | yes | Supabase anon key (used with the user's token) |
| `GROQ_API_KEY` | yes | Chat, vision and Whisper transcription |
| `OPENROUTER_API_KEY` | recommended | Failover chat provider |
| `APP_URL` | optional | Sent to OpenRouter as the referring site |
| `PORT` | optional | Port for `main.py` (Render sets this) |

Image generation uses a keyless diffusion endpoint, so it works out of the
box without another paid account or API key.

### Database

Run `supabase/schema.sql` in the Supabase SQL editor once. It creates the
optional `images` table used by the gallery; every other table the app uses
already exists in the project. If the table is missing, the app still works —
images simply are not kept in Saved files.

---

## Deploying

**Render** — the repo includes `render.yaml` and a `Procfile`:

```
gunicorn main:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 180
```

Set the environment variables in the Render dashboard and deploy. Streaming
responses are plain SSE, so no extra configuration is needed.

**Android (Capacitor)** — `capacitor.config.json` uses `frontend/` as the web
directory, so the app shell ships inside the APK and calls the deployed backend:

```bash
npm install
npx cap sync android
cd android && ./gradlew assembleRelease
```

Because `frontend/vendor/` holds local copies of every library, the app has no
runtime CDN dependency. The bundled UI only needs a connection for AI replies.

---

## Testing

```bash
python tests/test_app.py     # 92 checks: every route, error path and the router
pip install -r requirements-dev.txt
python -m playwright install chromium
python tests/test_ui.py      # 45 checks in a real browser + screenshots
```

The route suite runs the real Flask app against an in-memory Supabase and a
fake AI engine, so it needs no keys and no network. It covers chat, streaming,
regenerate, edit, memories, images, vision, transcription, documents, PDF
export, auth enforcement and provider failover.

The browser suite drives the real frontend: boot, streaming answer with code
cards, message actions, search, model selector, every view, image generation,
vision, document upload and analysis, saved files, settings, light/dark
themes, the mobile drawer and the auth pages.

---

## API

All `/api/*` routes except `/api/health`, `/api/status` and `/api/models`
require `Authorization: Bearer <supabase access token>`.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health`, `/api/status` | Deployment and provider status |
| GET | `/api/models` | Model catalogue + tool availability |
| POST | `/api/chat` | Blocking answer (`message`, `conversation_id`, `model`, `mode`, `regenerate`, `edit_message_id`, `use_memory`) |
| POST | `/api/chat/stream` | Same input, Server-Sent Events: `meta`, `delta`, `done`, `error` |
| GET/POST | `/api/conversations` | List / create |
| GET | `/api/conversations/<id>/messages` | Conversation messages |
| PATCH/DELETE | `/api/conversations/<id>` | Rename / delete |
| GET/POST | `/api/memories`, DELETE `/api/memories/<id>` | Long-term memory |
| POST/GET | `/api/documents`, DELETE `/api/documents/<id>` | Upload / list / delete documents |
| POST | `/api/documents/<id>/analyze` | Summary, key points, actions, questions |
| POST | `/api/convert/text-to-pdf` | Download a PDF |
| POST | `/api/images/generate`, GET `/api/images`, DELETE `/api/images/<id>` | Image studio |
| POST | `/api/vision` | Image understanding (multipart or data URL) |
| POST | `/api/transcribe` | Voice note → text (Groq Whisper) |
| GET | `/api/files` | Saved documents and images |

---

## Notes on safety

- Model output is rendered as Markdown and sanitised with DOMPurify, so a
  reply cannot inject scripts into the page.
- Every database and storage call is made with the user's own token and is
  covered by row level security; the backend never uses a service-role key.
- Uploads are limited by type and size (10 MB documents, 8 MB images,
  20 MB audio) and validated on both sides.
- API keys live only in the server environment; the browser only ever holds
  the public anon key and the signed-in user's session.

---

## Credit

JeffAI was created and developed by **Amedu Vincent Onjefu**, popularly known
as **Jeff Bhexus**. Groq and OpenRouter provide the AI infrastructure; they did
not create JeffAI.
