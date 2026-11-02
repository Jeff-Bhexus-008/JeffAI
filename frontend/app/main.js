/* =========================================================
   JeffAI frontend
   Created by Amedu Vincent Onjefu (Jeff Bhexus)
   ========================================================= */

import { renderMarkdown, copyText, escapeHtml, plainText } from "./markdown.js";
import { API_BASE, ConfigError, resolveSupabaseConfig } from "./env.js";

/* ---------------------------------------------------------
   ENVIRONMENT
   --------------------------------------------------------- */

/* API base and Supabase project resolution live in ./env.js */

const STORAGE = {
    theme: "jeffai:theme",
    collapsed: "jeffai:sidebar-collapsed",
    model: "jeffai:model",
    mode: "jeffai:mode",
    enter: "jeffai:enter-to-send",
    streaming: "jeffai:streaming",
    memory: "jeffai:memory",
    autoSpeak: "jeffai:auto-speak",
    voice: "jeffai:voice",
    rate: "jeffai:rate",
    imageStyle: "jeffai:image-style",
    imageAspect: "jeffai:image-aspect",
};

const MODE_OPTIONS = [
    { key: "chat", label: "Auto", description: "Balanced, natural answers." },
    { key: "concise", label: "Concise", description: "Short and to the point." },
    { key: "tutor", label: "Tutor", description: "Teach it step by step." },
    { key: "code", label: "Code", description: "Debug and explain code." },
    { key: "writer", label: "Writer", description: "Draft and polish text." },
    { key: "research", label: "Research", description: "Weigh evidence carefully." },
];

const IMAGE_STYLES = [
    { key: "auto", label: "Auto" },
    { key: "photo", label: "Photo" },
    { key: "cinematic", label: "Cinematic" },
    { key: "digital", label: "Digital art" },
    { key: "3d", label: "3D render" },
    { key: "anime", label: "Anime" },
    { key: "product", label: "Product" },
    { key: "minimal", label: "Minimal" },
];

const IMAGE_ASPECTS = [
    { key: "square", label: "Square", ratio: "1 / 1" },
    { key: "portrait", label: "Portrait", ratio: "3 / 4" },
    { key: "landscape", label: "Landscape", ratio: "4 / 3" },
    { key: "wide", label: "Wide", ratio: "16 / 9" },
];

const VISION_PRESETS = [
    "Describe this image",
    "Read all the text",
    "Explain this chart",
    "What is wrong here?",
    "Turn this into code",
];

const ROUTE_META = {
    chat: { title: "Chat", subtitle: "Your personal AI assistant" },
    images: { title: "Image Studio", subtitle: "Generate images from a description" },
    vision: { title: "Image Understanding", subtitle: "Ask questions about any picture" },
    documents: { title: "Document Tools", subtitle: "Summarise, explain and convert files" },
    voice: { title: "Voice Assistant", subtitle: "Speak with JeffAI" },
    files: { title: "Saved Files", subtitle: "Documents and images" },
};

const WELCOME_PROMPTS = [
    {
        icon: "sparkles",
        title: "Ask anything",
        text: "Explain a hard idea in plain language.",
        action: { type: "prompt", value: "Explain how neural networks learn, in plain language with a simple example." },
    },
    {
        icon: "code",
        title: "Fix my code",
        text: "Paste an error and get a real explanation.",
        action: { type: "prompt", value: "My Python code throws an error. Help me debug it. Here is the code:\n\n```python\n\n```" },
    },
    {
        icon: "pen",
        title: "Write with me",
        text: "Emails, captions, essays, product copy.",
        action: { type: "prompt", value: "Write a short, warm follow-up email to a client who has not replied in a week." },
    },
    {
        icon: "book",
        title: "Study a document",
        text: "Upload a PDF and ask questions.",
        action: { type: "route", value: "documents" },
    },
    {
        icon: "image",
        title: "Create an image",
        text: "Describe a scene and JeffAI renders it.",
        action: { type: "route", value: "images" },
    },
    {
        icon: "eye",
        title: "Understand a photo",
        text: "Read text, charts and screenshots.",
        action: { type: "route", value: "vision" },
    },
];

/* ---------------------------------------------------------
   SMALL HELPERS
   --------------------------------------------------------- */

const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function store(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
        /* storage may be unavailable in private mode */
    }
}

function read(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
    } catch (error) {
        return fallback;
    }
}

function icon(name, size = 18) {
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

function relativeGroup(value) {
    const date = value ? new Date(value) : new Date();
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const days = Math.round((startOfToday - startOfDate) / 86400000);

    if (days <= 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return "Previous 7 days";
    if (days < 30) return "Previous 30 days";
    return "Older";
}

function initialsFrom(email) {
    if (!email) return "J";
    const clean = String(email).split("@")[0].replace(/[^a-zA-Z0-9]/g, " ").trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (!parts.length) return "J";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
}

function debounce(fn, wait = 250) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), wait);
    };
}

function normalizeError(error) {
    if (!error) return "Something went wrong.";
    if (typeof error === "string") return error;
    return error.message || "Something went wrong.";
}

class ApiError extends Error {
    constructor(message, status, payload) {
        super(message);
        this.status = status;
        this.payload = payload || {};
    }
}

/* ---------------------------------------------------------
   STATE
   --------------------------------------------------------- */

const state = {
    session: null,
    user: null,
    conversations: [],
    conversationsLoaded: false,
    currentConversationId: null,
    currentMessages: [],
    models: [],
    model: read(STORAGE.model, "jeff-balanced"),
    mode: read(STORAGE.mode, "chat"),
    route: "chat",
    streaming: false,
    abort: null,
    attachedDocument: null,
    attachedImage: null,
    imageStyle: read(STORAGE.imageStyle, "auto"),
    imageAspect: read(STORAGE.imageAspect, "square"),
    lastGenerated: [],
    visionFile: null,
    visionAnswer: "",
    filesTab: "documents",
    memories: [],
    speechVoices: [],
    settings: {
        enter: read(STORAGE.enter, true),
        streaming: read(STORAGE.streaming, true),
        memory: read(STORAGE.memory, true),
        autoSpeak: read(STORAGE.autoSpeak, false),
        voice: read(STORAGE.voice, ""),
        rate: Number(read(STORAGE.rate, 1)) || 1,
    },
};

let supabase = null;
let recognition = null;
let recorder = null;
let recorderStream = null;
let recorderChunks = [];
let recorderTimer = null;

/* ---------------------------------------------------------
   TOASTS
   --------------------------------------------------------- */

const TOAST_ICONS = { error: "alert", success: "check", info: "sparkles" };

function toast(message, type = "info", timeout = 4200) {
    const stack = $("#toastStack");
    if (!stack) return;

    const node = document.createElement("div");
    node.className = `toast is-${type}`;
    node.innerHTML = `
        ${icon(TOAST_ICONS[type] || "sparkles", 16)}
        <div>${escapeHtml(message)}</div>
    `;

    stack.appendChild(node);

    setTimeout(() => {
        node.classList.add("leaving");
        setTimeout(() => node.remove(), 260);
    }, timeout);
}

/* ---------------------------------------------------------
   THEME
   --------------------------------------------------------- */

function applyTheme(theme, persist = true) {
    const next = theme === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);

    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", next === "light" ? "#f5f6fc" : "#06060b");

    $$("#themeBtn svg use, #themeBtnTop svg use").forEach((use) => {
        use.setAttribute("href", next === "light" ? "#i-moon" : "#i-sun");
    });

    $$("#themeCards [data-theme-choice]").forEach((card) => {
        card.classList.toggle("is-active", card.dataset.themeChoice === next);
    });

    if (persist) store(STORAGE.theme, next);
}

function currentTheme() {
    return document.documentElement.getAttribute("data-theme") || "dark";
}

function toggleTheme() {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
}

/* ---------------------------------------------------------
   AUTH + API
   --------------------------------------------------------- */

async function ensureLibs() {
    const deadline = Date.now() + 6000;
    while (Date.now() < deadline) {
        if (window.supabase && window.marked) return true;
        await sleep(60);
    }
    return Boolean(window.supabase);
}

async function initSupabase() {
    const config = await resolveSupabaseConfig();
    supabase = window.supabase.createClient(config.url, config.key);
    return config;
}

function renderConfigError(message) {
    $("#messages").innerHTML = `
        <div class="empty">
            <span class="empty-icon">${icon("alert", 21)}</span>
            <strong>JeffAI is not configured</strong>
            <span>${escapeHtml(message)}</span>
            <span style="margin-top:6px">
                Check <a href="/api/config" target="_blank" rel="noopener">/api/config</a>
                and <a href="/api/health" target="_blank" rel="noopener">/api/health</a>.
            </span>
        </div>`;
}

async function ensureSession(force = false) {
    if (!state.session || force) {
        const { data } = await supabase.auth.getSession();
        state.session = data.session || null;
    }
    if (!state.session) return null;
    return state.session;
}

async function authHeaders(json = true) {
    const session = await ensureSession();
    const headers = {};
    if (session?.access_token) headers.Authorization = `Bearer ${session.access_token}`;
    if (json) headers["Content-Type"] = "application/json";
    return headers;
}

async function api(path, options = {}) {
    const isForm = options.body instanceof FormData;
    const headers = Object.assign({}, options.headers || {}, await authHeaders(!isForm));

    let response;

    try {
        response = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } catch (error) {
        throw new ApiError("Network problem. Check your connection and try again.", 0);
    }

    if (response.status === 401) {
        const refreshed = await ensureSession(true);

        if (!refreshed) {
            window.location.href = "/login.html";
            throw new ApiError("Your session expired. Please sign in again.", 401);
        }

        const retryHeaders = Object.assign({}, options.headers || {}, await authHeaders(!isForm));

        try {
            response = await fetch(`${API_BASE}${path}`, { ...options, headers: retryHeaders });
        } catch (error) {
            throw new ApiError("Network problem. Check your connection and try again.", 0);
        }
    }

    let payload = {};
    try {
        payload = await response.json();
    } catch (error) {
        payload = {};
    }

    if (!response.ok || payload.success === false) {
        throw new ApiError(
            payload.error || `Request failed (${response.status})`,
            response.status,
            payload
        );
    }

    return payload;
}

/* ---------------------------------------------------------
   MODALS
   --------------------------------------------------------- */

function openOverlay(id) {
    const overlay = $(`#${id}`);
    if (!overlay) return;
    overlay.classList.add("is-open");
    document.body.style.overflow = "hidden";
}

function closeOverlay(id) {
    const overlay = $(`#${id}`);
    if (!overlay) return;
    overlay.classList.remove("is-open");
    if (!$(".overlay.is-open")) document.body.style.overflow = "";
}

function closeAllOverlays() {
    $$(".overlay.is-open").forEach((overlay) => overlay.classList.remove("is-open"));
    document.body.style.overflow = "";
}

function confirmAction({ title, text, okLabel = "Delete", danger = true }) {
    return new Promise((resolve) => {
        $("#confirmTitle").textContent = title || "Are you sure?";
        $("#confirmText").textContent = text || "This cannot be undone.";

        const ok = $("#confirmOk");
        ok.textContent = okLabel;
        ok.className = `btn btn-sm ${danger ? "btn-danger" : "btn-primary"}`;

        openOverlay("confirmOverlay");

        const finish = (result) => {
            closeOverlay("confirmOverlay");
            ok.removeEventListener("click", onOk);
            $("#confirmCancel").removeEventListener("click", onCancel);
            resolve(result);
        };

        const onOk = () => finish(true);
        const onCancel = () => finish(false);

        ok.addEventListener("click", onOk);
        $("#confirmCancel").addEventListener("click", onCancel);
    });
}

function promptRename(currentTitle) {
    return new Promise((resolve) => {
        const input = $("#renameInput");
        input.value = currentTitle || "";
        openOverlay("renameOverlay");
        setTimeout(() => {
            input.focus();
            input.select();
        }, 80);

        const finish = (result) => {
            closeOverlay("renameOverlay");
            $("#renameSave").removeEventListener("click", onSave);
            $("#renameCancel").removeEventListener("click", onCancel);
            $("#renameClose").removeEventListener("click", onCancel);
            input.removeEventListener("keydown", onKey);
            resolve(result);
        };

        const onSave = () => finish(input.value.trim());
        const onCancel = () => finish(null);
        const onKey = (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                onSave();
            }
        };

        $("#renameSave").addEventListener("click", onSave);
        $("#renameCancel").addEventListener("click", onCancel);
        $("#renameClose").addEventListener("click", onCancel);
        input.addEventListener("keydown", onKey);
    });
}

/* ---------------------------------------------------------
   ROUTER
   --------------------------------------------------------- */

function setRoute(route, options = {}) {
    const next = ROUTE_META[route] ? route : "chat";

    state.route = next;

    $$(".view").forEach((view) => {
        view.classList.toggle("is-active", view.dataset.view === next);
    });

    $$(".nav-item[data-route]").forEach((item) => {
        item.classList.toggle("is-active", item.dataset.route === next);
    });

    const meta = ROUTE_META[next];
    $("#topTitle").textContent = meta.title;
    $("#topSubtitle").textContent = meta.subtitle;

    $("#modelSelectWrap").hidden = next !== "chat";

    document.body.classList.remove("is-drawer-open");

    if (next === "chat") {
        scrollToBottom();
    }

    if (next === "images") loadImageHistory();
    if (next === "documents") loadDocuments();
    if (next === "files") loadFiles();
    if (next === "voice") populateVoiceSelects();

    if (!options.silent) {
        const hash = `#/${next}`;
        if (window.location.hash !== hash) {
            history.replaceState(null, "", hash);
        }
    }
}

/* ---------------------------------------------------------
   SIDEBAR
   --------------------------------------------------------- */

function setCollapsed(collapsed) {
    $("#app").classList.toggle("is-collapsed", collapsed);
    store(STORAGE.collapsed, collapsed);

    const button = $("#collapseBtn");
    if (button) {
        button.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
        button.querySelector("use").setAttribute(
            "href",
            collapsed ? "#i-chevron-right" : "#i-chevron-left"
        );
    }
}

async function loadConversations() {
    const list = $("#conversationList");

    if (!state.conversationsLoaded && list) {
        list.innerHTML = Array.from({ length: 4 })
            .map(() => '<div class="skeleton" style="height:34px;margin:2px 4px"></div>')
            .join("");
    }

    try {
        const data = await api("/api/conversations");
        state.conversations = data.conversations || [];
        state.conversationsLoaded = true;
        renderConversations();
    } catch (error) {
        if (list) {
            list.innerHTML = `
                <div class="side-empty">
                    Could not load conversations.<br>${escapeHtml(normalizeError(error))}
                </div>`;
        }
    }
}

function renderConversations() {
    const list = $("#conversationList");
    if (!list) return;

    const query = ($("#conversationSearch")?.value || "").trim().toLowerCase();

    const filtered = state.conversations.filter((conversation) =>
        !query || (conversation.title || "").toLowerCase().includes(query)
    );

    $("#conversationCount").textContent = state.conversations.length
        ? String(state.conversations.length)
        : "";

    if (!filtered.length) {
        list.innerHTML = `
            <div class="side-empty">
                ${query
                    ? "No conversations match that search."
                    : "No conversations yet. Start a new chat and it will appear here."}
            </div>`;
        return;
    }

    let lastGroup = null;
    const html = [];

    filtered.forEach((conversation) => {
        const group = relativeGroup(conversation.updated_at || conversation.created_at);

        if (group !== lastGroup) {
            html.push(`<div class="conversation-group-label">${escapeHtml(group)}</div>`);
            lastGroup = group;
        }

        const active = conversation.id === state.currentConversationId ? " is-active" : "";

        html.push(`
            <div class="conversation${active}" role="listitem" data-conversation="${escapeHtml(conversation.id)}">
                <button class="conversation-title" type="button" data-open="${escapeHtml(conversation.id)}" title="${escapeHtml(conversation.title || "Conversation")}">
                    ${escapeHtml(conversation.title || "Conversation")}
                </button>
                <span class="conversation-actions">
                    <button class="mini-btn" type="button" data-rename="${escapeHtml(conversation.id)}" title="Rename" aria-label="Rename conversation">
                        ${icon("edit", 14)}
                    </button>
                    <button class="mini-btn danger" type="button" data-delete="${escapeHtml(conversation.id)}" title="Delete" aria-label="Delete conversation">
                        ${icon("trash", 14)}
                    </button>
                </span>
            </div>
        `);
    });

    list.innerHTML = html.join("");

    list.querySelectorAll("[data-open]").forEach((button) => {
        button.addEventListener("click", () => openConversation(button.dataset.open));
    });

    list.querySelectorAll("[data-rename]").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            renameConversation(button.dataset.rename);
        });
    });

    list.querySelectorAll("[data-delete]").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            deleteConversation(button.dataset.delete);
        });
    });
}

async function renameConversation(id) {
    const conversation = state.conversations.find((item) => item.id === id);

    const title = await promptRename(conversation?.title || "");

    if (title === null) return;

    if (!title) {
        toast("A conversation needs a name.", "error");
        return;
    }

    try {
        await api(`/api/conversations/${id}`, {
            method: "PATCH",
            body: JSON.stringify({ title }),
        });

        if (conversation) conversation.title = title;

        renderConversations();

        if (id === state.currentConversationId) {
            $("#topTitle").textContent = "Chat";
        }

        toast("Conversation renamed.", "success", 2200);
    } catch (error) {
        toast(normalizeError(error), "error");
    }
}

async function deleteConversation(id) {
    const confirmed = await confirmAction({
        title: "Delete this conversation?",
        text: "The chat and its messages will be removed from your account.",
        okLabel: "Delete chat",
    });

    if (!confirmed) return;

    try {
        await api(`/api/conversations/${id}`, { method: "DELETE" });

        state.conversations = state.conversations.filter((item) => item.id !== id);

        if (id === state.currentConversationId) {
            newChat();
        }

        renderConversations();
        toast("Conversation deleted.", "success", 2400);
    } catch (error) {
        toast(normalizeError(error), "error");
    }
}

/* ---------------------------------------------------------
   CHAT RENDERING
   --------------------------------------------------------- */

function showWelcome() {
    const messages = $("#messages");

    messages.innerHTML = `
        <div class="welcome" id="welcome">
            <div class="welcome-orb">J</div>
            <h1>How can I help you today?</h1>
            <p>I'm JeffAI — ask me anything, build something, study a document, create an image, or just talk. Created by Jeff Bhexus.</p>

            <div class="prompt-grid">
                ${WELCOME_PROMPTS.map((prompt, index) => `
                    <button class="prompt-card" type="button" data-prompt="${index}">
                        <span class="prompt-icon">${icon(prompt.icon, 16)}</span>
                        <span class="prompt-title">${escapeHtml(prompt.title)}</span>
                        <span class="prompt-text">${escapeHtml(prompt.text)}</span>
                    </button>
                `).join("")}
            </div>

            <div class="welcome-shortcuts">
                <button class="shortcut-chip" type="button" data-jump="images">${icon("image", 14)} Generate an image</button>
                <button class="shortcut-chip" type="button" data-jump="documents">${icon("file", 14)} Upload a document</button>
                <button class="shortcut-chip" type="button" data-jump="voice">${icon("mic", 14)} Voice mode</button>
                <button class="shortcut-chip" type="button" data-jump="files">${icon("folder", 14)} Saved files</button>
            </div>
        </div>
    `;

    messages.querySelectorAll("[data-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            const prompt = WELCOME_PROMPTS[Number(button.dataset.prompt)];
            if (!prompt) return;

            if (prompt.action.type === "route") {
                setRoute(prompt.action.value);
                return;
            }

            $("#messageInput").value = prompt.action.value;
            autoResize();
            updateComposerState();
            $("#messageInput").focus();
        });
    });

    messages.querySelectorAll("[data-jump]").forEach((button) => {
        button.addEventListener("click", () => setRoute(button.dataset.jump));
    });
}

function messageElement({ role, content, created_at, id, imagePreview }) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role}`;
    if (id) wrapper.dataset.messageId = id;
    if (created_at) wrapper.dataset.createdAt = created_at;

    const isUser = role === "user";
    const author = isUser ? "You" : "JeffAI";
    const avatar = isUser ? (state.user?.initials || "YOU") : "J";

    wrapper.innerHTML = `
        <div class="message-avatar">${escapeHtml(avatar)}</div>
        <div class="message-main">
            <div class="message-top">
                <span class="message-author">${escapeHtml(author)}</span>
                <span class="message-time">${escapeHtml(formatTime(created_at))}</span>
                ${isUser ? "" : '<span class="message-badge">AI</span>'}
            </div>
            <div class="message-body"></div>
            <div class="message-actions">
                <button class="mini-btn" type="button" data-action="copy" title="Copy" aria-label="Copy message">${icon("copy", 15)}</button>
                ${isUser
                    ? `<button class="mini-btn" type="button" data-action="edit" title="Edit and resend" aria-label="Edit message">${icon("edit", 15)}</button>`
                    : `<button class="mini-btn" type="button" data-action="speak" title="Read aloud" aria-label="Read aloud">${icon("volume", 15)}</button>
                       <button class="mini-btn" type="button" data-action="regenerate" title="Regenerate" aria-label="Regenerate reply">${icon("refresh", 15)}</button>`}
            </div>
        </div>
    `;

    const body = wrapper.querySelector(".message-body");

    if (imagePreview) {
        const thumb = document.createElement("img");
        thumb.src = imagePreview;
        thumb.alt = "Attached image";
        thumb.className = "attached-thumb";
        body.appendChild(thumb);
    }

    if (isUser) {
        const text = document.createElement("span");
        text.textContent = content || "";
        body.appendChild(text);
    } else {
        body.innerHTML = renderMarkdown(content || "");
    }

    wrapper.querySelector('[data-action="copy"]')?.addEventListener("click", async () => {
        const ok = await copyText(content || "");
        toast(ok ? "Copied to clipboard." : "Could not copy.", ok ? "success" : "error", 1800);
    });

    wrapper.querySelector('[data-action="speak"]')?.addEventListener("click", (event) => {
        speakText(content || "", event.currentTarget);
    });

    wrapper.querySelector('[data-action="regenerate"]')?.addEventListener("click", () => {
        regenerateResponse(wrapper);
    });

    wrapper.querySelector('[data-action="edit"]')?.addEventListener("click", () => {
        editMessage(wrapper);
    });

    return wrapper;
}

function appendMessage(message, { scroll = true } = {}) {
    const welcome = $("#welcome");
    if (welcome) welcome.remove();

    const node = messageElement(message);
    $("#messages").appendChild(node);

    if (scroll) scrollToBottom();

    return node;
}

function setMessageBody(node, content, streaming = false) {
    const body = node.querySelector(".message-body");
    if (!body) return;

    if (streaming) {
        body.innerHTML = renderMarkdown(content);
    } else {
        body.innerHTML = renderMarkdown(content);
    }

    node.dataset.content = content;
}

function scrollToBottom(behavior = "smooth") {
    const scroller = $("#chatScroller");
    if (!scroller) return;
    scroller.scrollTo({ top: scroller.scrollHeight, behavior });
}

function showTyping(node) {
    const body = node.querySelector(".message-body");
    if (!body) return;
    body.innerHTML = `
        <div class="typing">
            <span></span><span></span><span></span>
            <span class="thinking-label">JeffAI is thinking…</span>
        </div>
    `;
}

/* ---------------------------------------------------------
   CHAT: CONVERSATION LOADING
   --------------------------------------------------------- */

async function openConversation(id) {
    if (!id) return;

    if (state.streaming) {
        toast("Wait for the current answer to finish first.", "info", 2200);
        return;
    }

    state.currentConversationId = id;
    state.currentMessages = [];
    setRouteRaw("chat");

    renderConversations();

    const messages = $("#messages");
    messages.innerHTML = `
        <div class="skeleton" style="height:60px;margin:10px 0"></div>
        <div class="skeleton" style="height:88px;margin:10px 0"></div>
        <div class="skeleton" style="height:60px;margin:10px 0"></div>
    `;

    const conversation = state.conversations.find((item) => item.id === id);
    $("#topTitle").textContent = conversation?.title || "Chat";

    try {
        const data = await api(`/api/conversations/${id}/messages`);
        const list = data.messages || [];

        state.currentMessages = list;

        messages.innerHTML = "";

        if (!list.length) {
            showWelcome();
            return;
        }

        list.forEach((message) => {
            appendMessage({
                id: message.id,
                role: message.role,
                content: message.content,
                created_at: message.created_at || message.createdAt,
            }, { scroll: false });
        });

        scrollToBottom("auto");
        markLastMessage();
    } catch (error) {
        messages.innerHTML = `
            <div class="empty">
                <span class="empty-icon">${icon("alert", 21)}</span>
                <strong>Could not open this conversation</strong>
                <span>${escapeHtml(normalizeError(error))}</span>
            </div>`;
    }
}

function setRouteRaw(route) {
    setRoute(route);
}

function markLastMessage() {
    const nodes = $$("#messages .message");
    nodes.forEach((node) => node.classList.remove("is-last"));
    nodes[nodes.length - 1]?.classList.add("is-last");
}

function newChat() {
    if (state.streaming) {
        toast("Finish or stop the current answer first.", "info", 2200);
        return;
    }

    state.currentConversationId = null;
    state.currentMessages = [];
    state.attachedDocument = null;
    state.attachedImage = null;
    renderAttachments();

    $("#messageInput").value = "";
    autoResize();
    updateComposerState();

    setRoute("chat");
    showWelcome();

    renderConversations();

    $("#topTitle").textContent = "Chat";
    $("#messageInput").focus();
}

/* ---------------------------------------------------------
   CHAT: STREAMING
   --------------------------------------------------------- */

function buildPayload(message, options = {}) {
    return {
        message,
        conversation_id: options.conversation_id || state.currentConversationId,
        model: state.model,
        mode: state.mode,
        regenerate: Boolean(options.regenerate),
        edit_message_id: options.edit_message_id || null,
        use_memory: state.settings.memory,
        attachments: [],
    };
}

async function streamChat(payload, handlers) {
    const controller = new AbortController();
    state.abort = controller;

    const headers = await authHeaders(true);

    const response = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal,
    });

    const contentType = response.headers.get("content-type") || "";

    if (!response.ok || !contentType.includes("text/event-stream")) {
        let payloadError = {};
        try {
            payloadError = await response.json();
        } catch (error) {
            payloadError = {};
        }
        throw new ApiError(
            payloadError.error || "JeffAI could not start the answer.",
            response.status,
            payloadError
        );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finished = false;

    while (!finished) {
        const { done, value } = await reader.read();

        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let boundary = buffer.indexOf("\n\n");

        while (boundary !== -1) {
            const raw = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);

            const lines = raw.split("\n");
            let eventName = "message";
            let dataLine = "";

            lines.forEach((line) => {
                if (line.startsWith("event:")) eventName = line.slice(6).trim();
                if (line.startsWith("data:")) dataLine += line.slice(5).trim();
            });

            if (dataLine) {
                let parsed = {};
                try {
                    parsed = JSON.parse(dataLine);
                } catch (error) {
                    parsed = {};
                }
                handlers.onEvent(eventName, parsed);
            }

            boundary = buffer.indexOf("\n\n");
        }
    }

    state.abort = null;
}

async function sendMessage(rawText, options = {}) {
    const text = (rawText ?? "").trim();

    if (!text && !options.regenerate) return;

    if (state.streaming) return;

    const imageFile = options.keepAttachment ? state.attachedImage : state.attachedImage;

    let outgoing = text;

    const messagesContainer = $("#messages");

    let assistantNode = options.assistantNode || null;

    /* ---------------- optimistic UI ---------------- */

    const welcome = $("#welcome");
    if (welcome) welcome.remove();

    if (!options.regenerate) {
        let preview = null;

        if (imageFile) {
            preview = await fileToDataUrl(imageFile);
        }

        const node = appendMessage({
            role: "user",
            content: text,
            created_at: new Date().toISOString(),
            imagePreview: preview,
        });

        if (options.editMessageElement) {
            options.editMessageElement.replaceWith(node);
            node.dataset.messageId = options.editMessageElement.dataset.messageId || "";
        }

        markLastMessage();
    }

    if (!assistantNode) {
        assistantNode = appendMessage({
            role: "assistant",
            content: "",
            created_at: new Date().toISOString(),
        });
        showTyping(assistantNode);
    }

    assistantNode.classList.add("is-streaming");

    markLastMessage();

    state.streaming = true;
    updateComposerState();

    const scrollDuringStream = debounce(() => scrollToBottom("auto"), 120);

    let collected = "";

    const setText = (value) => {
        collected = value;
        setMessageBody(assistantNode, collected, true);
        scrollDuringStream();
    };

    let settled = false;

    const finish = (finalText, meta = {}) => {
        if (settled) return;
        settled = true;

        state.streaming = false;
        state.abort = null;
        assistantNode.classList.remove("is-streaming");

        if (finalText) {
            setMessageBody(assistantNode, finalText);
        }

        if (meta.conversation_id) {
            state.currentConversationId = meta.conversation_id;
        }

        markLastMessage();
        updateComposerState();
        scrollToBottom();

        loadConversations();

        if (state.settings.autoSpeak && finalText) {
            speakText(finalText);
        }
    };

    /* image understanding first, so the model can "see" the picture */

    if (imageFile && !options.regenerate) {
        try {
            const form = new FormData();
            form.append("image", imageFile);
            form.append(
                "question",
                "Describe this image in full detail, including any text, numbers or code."
            );

            const vision = await api("/api/vision", { method: "POST", body: form });

            outgoing = `${text}\n\n[What the attached image shows: ${vision.answer}]`;
        } catch (error) {
            toast("Could not read the attached image. Sending your text only.", "error");
        }

        state.attachedImage = null;
        renderAttachments();
    }

    const payload = buildPayload(outgoing, options);

    /* ---------------- request ---------------- */

    try {
        if (state.settings.streaming) {
            await streamChat(payload, {
                onEvent(eventName, data) {
                    if (eventName === "meta") {
                        if (data.conversation_id) {
                            state.currentConversationId = data.conversation_id;
                        }
                        return;
                    }

                    if (eventName === "delta") {
                        if (assistantNode.querySelector(".typing")) {
                            assistantNode.querySelector(".message-body").innerHTML = "";
                        }
                        setText(collected + (data.text || ""));
                        return;
                    }

                    if (eventName === "error") {
                        const message = data.error || "JeffAI could not answer.";

                        if (data.error_type === "rate_limit") {
                            setMessageBody(assistantNode, message);
                            finish(message);
                            return;
                        }

                        throw new ApiError(message, 503, data);
                    }

                    if (eventName === "done") {
                        finish(data.response || collected, data);
                    }
                },
            });

            if (!collected) {
                setMessageBody(
                    assistantNode,
                    "I could not produce a reply that time. Try sending your message again."
                );
                finish(collected);
            } else {
                finish(collected);
            }
        } else {
            const data = await api("/api/chat", {
                method: "POST",
                body: JSON.stringify(payload),
            });

            finish(data.response || "", data);
        }
    } catch (error) {
        if (error.name === "AbortError") {
            finish(
                collected ||
                    "_Stopped before JeffAI answered. Send your message again whenever you're ready._"
            );
            toast("Generation stopped.", "info", 2000);
            return;
        }

        const message = normalizeError(error);

        assistantNode.classList.remove("is-streaming");

        setMessageBody(
            assistantNode,
            collected
                ? `${collected}\n\n---\n\n**Connection lost.** ${message}`
                : `**I couldn't answer that.** ${message}`
        );

        finish(collected);
        toast(message, "error");
    }
}

function stopStreaming() {
    if (state.abort) {
        state.abort.abort();
    }
}

async function regenerateResponse(assistantNode) {
    if (state.streaming) return;

    if (!state.currentConversationId) {
        toast("Send a message first, then I can regenerate.", "info");
        return;
    }

    assistantNode.querySelector(".message-body").innerHTML = "";
    showTyping(assistantNode);
    assistantNode.classList.add("is-streaming");

    await sendMessage("", {
        regenerate: true,
        assistantNode,
        conversation_id: state.currentConversationId,
    });
}

async function editMessage(node) {
    if (state.streaming) return;

    const original = node.dataset.content || node.querySelector(".message-body span")?.textContent || "";

    const body = node.querySelector(".message-body");
    const actions = node.querySelector(".message-actions");

    body.innerHTML = "";
    actions.style.display = "none";

    const wrapper = document.createElement("div");
    wrapper.className = "edit-box";
    wrapper.innerHTML = `
        <textarea class="input" rows="3" style="min-height:80px"></textarea>
        <div class="foot-row" style="margin-top:8px;justify-content:flex-end">
            <button class="btn btn-sm btn-ghost" type="button" data-cancel>Cancel</button>
            <button class="btn btn-sm btn-primary" type="button" data-save>Save &amp; resend</button>
        </div>
    `;

    const textarea = wrapper.querySelector("textarea");
    textarea.value = original;

    body.appendChild(wrapper);
    textarea.focus();
    textarea.setSelectionRange(original.length, original.length);

    wrapper.querySelector("[data-cancel]").addEventListener("click", () => {
        body.innerHTML = "";
        const span = document.createElement("span");
        span.textContent = original;
        body.appendChild(span);
        actions.style.display = "";
    });

    wrapper.querySelector("[data-save]").addEventListener("click", async () => {
        const nextText = textarea.value.trim();

        if (!nextText) {
            toast("The message cannot be empty.", "error");
            return;
        }

        const messageId = node.dataset.messageId;

        /* remove everything after the edited message */
        let cursor = node.nextElementSibling;
        while (cursor) {
            const next = cursor.nextElementSibling;
            cursor.remove();
            cursor = next;
        }

        body.innerHTML = "";
        const span = document.createElement("span");
        span.textContent = nextText;
        body.appendChild(span);
        actions.style.display = "";

        await sendMessage(nextText, {
            edit_message_id: messageId,
            editMessageElement: node,
            conversation_id: state.currentConversationId,
        });
    });
}

/* ---------------------------------------------------------
   COMPOSER
   --------------------------------------------------------- */

function autoResize() {
    const input = $("#messageInput");
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, window.innerHeight * 0.44)}px`;
}

function updateComposerState() {
    const input = $("#messageInput");
    const send = $("#sendBtn");
    const count = $("#charCount");

    const length = input.value.length;

    count.textContent = length > 700 ? `${length}` : "";

    if (state.streaming) {
        send.classList.add("is-stop");
        send.disabled = false;
        send.title = "Stop generating";
        send.setAttribute("aria-label", "Stop generating");
        send.innerHTML = icon("stop", 18);
        return;
    }

    send.classList.remove("is-stop");
    send.title = "Send message";
    send.setAttribute("aria-label", "Send message");
    send.innerHTML = icon("send", 18);

    const hasContent = Boolean(input.value.trim() || state.attachedImage || state.attachedDocument);
    send.disabled = !hasContent;
}

function renderAttachments() {
    const row = $("#attachmentRow");
    if (!row) return;

    const chips = [];

    if (state.attachedDocument) {
        chips.push(`
            <span class="attachment-chip">
                ${icon("file", 14)}
                <span class="attachment-name">${escapeHtml(state.attachedDocument.filename)}</span>
                <button class="mini-btn" type="button" data-remove-doc aria-label="Remove document">${icon("close", 12)}</button>
            </span>
        `);
    }

    if (state.attachedImage) {
        chips.push(`
            <span class="attachment-chip">
                ${icon("image", 14)}
                <span class="attachment-name">${escapeHtml(state.attachedImage.name)}</span>
                <button class="mini-btn" type="button" data-remove-image aria-label="Remove image">${icon("close", 12)}</button>
            </span>
        `);
    }

    row.innerHTML = chips.join("");
    row.hidden = chips.length === 0;

    row.querySelector("[data-remove-doc]")?.addEventListener("click", () => {
        state.attachedDocument = null;
        renderAttachments();
        updateComposerState();
    });

    row.querySelector("[data-remove-image]")?.addEventListener("click", () => {
        state.attachedImage = null;
        renderAttachments();
        updateComposerState();
    });
}

function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function uploadDocument(file) {
    if (!file) return;

    const allowed = ["pdf", "docx", "txt"];
    const extension = (file.name.split(".").pop() || "").toLowerCase();

    if (!allowed.includes(extension)) {
        toast("Only PDF, DOCX and TXT files are supported.", "error");
        return;
    }

    toast(`Uploading ${file.name}…`, "info", 2200);

    const form = new FormData();
    form.append("file", file);

    try {
        const data = await api("/api/documents", { method: "POST", body: form });

        state.attachedDocument = data.document;

        renderAttachments();
        updateComposerState();

        toast("Document ready. Ask me anything about it.", "success");

        loadDocuments();
    } catch (error) {
        toast(normalizeError(error), "error");
    }
}

function setupComposer() {
    const input = $("#messageInput");
    const form = $("#composerForm");

    input.addEventListener("input", () => {
        autoResize();
        updateComposerState();
    });

    input.addEventListener("keydown", (event) => {
        const enterSends = state.settings.enter;

        if (event.key === "Enter" && !event.shiftKey && enterSends) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (state.streaming) {
            stopStreaming();
            return;
        }

        const text = input.value.trim();

        if (!text && !state.attachedImage) return;

        input.value = "";
        autoResize();
        updateComposerState();

        await sendMessage(text);
    });

    $("#attachBtn").addEventListener("click", () => $("#attachInput").click());

    $("#attachInput").addEventListener("change", async (event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) await uploadDocument(file);
    });

    $("#imageBtn").addEventListener("click", () => $("#imageInput").click());

    $("#imageInput").addEventListener("change", (event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (!file) return;

        if (!file.type.startsWith("image/")) {
            toast("Please choose an image file.", "error");
            return;
        }

        if (file.size > 8 * 1024 * 1024) {
            toast("That image is larger than 8 MB.", "error");
            return;
        }

        state.attachedImage = file;
        renderAttachments();
        updateComposerState();
        toast("Image attached. Ask me anything about it.", "success", 2400);
    });

    $("#micBtn").addEventListener("click", () => {
        setRoute("voice");
        setTimeout(() => $("#voiceOrb").focus(), 200);
    });

    /* drag & drop */

    const box = $("#composerBox");

    ["dragenter", "dragover"].forEach((type) => {
        box.addEventListener(type, (event) => {
            event.preventDefault();
            box.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach((type) => {
        box.addEventListener(type, (event) => {
            event.preventDefault();
            box.classList.remove("is-dragging");
        });
    });

    box.addEventListener("drop", async (event) => {
        const file = event.dataTransfer?.files?.[0];
        if (!file) return;

        if (file.type.startsWith("image/")) {
            state.attachedImage = file;
            renderAttachments();
            updateComposerState();
            return;
        }

        await uploadDocument(file);
    });

    /* paste an image */

    input.addEventListener("paste", (event) => {
        const item = Array.from(event.clipboardData?.items || []).find((entry) =>
            entry.type.startsWith("image/")
        );

        if (!item) return;

        const file = item.getAsFile();
        if (!file) return;

        event.preventDefault();
        state.attachedImage = file;
        renderAttachments();
        updateComposerState();
        toast("Image pasted. Add a question and send.", "success", 2400);
    });

    /* answer mode popover */

    const toolsBtn = $("#toolsBtn");
    const popover = $("#toolsPopover");

    toolsBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        renderModePopover();
        const isHidden = popover.hidden;
        popover.hidden = !isHidden;
        toolsBtn.setAttribute("aria-expanded", String(isHidden));
    });

    document.addEventListener("click", (event) => {
        if (!popover.hidden && !popover.contains(event.target) && event.target !== toolsBtn) {
            popover.hidden = true;
            toolsBtn.setAttribute("aria-expanded", "false");
        }
    });
}

function renderModePopover() {
    const popover = $("#toolsPopover");

    popover.innerHTML = `
        <div class="popover-label">Answer mode</div>
        ${MODE_OPTIONS.map((option) => `
            <button class="popover-item ${state.mode === option.key ? "is-current" : ""}" type="button" data-mode="${option.key}">
                ${icon("sparkles", 15)}
                <span>
                    ${escapeHtml(option.label)}
                    <small>${escapeHtml(option.description)}</small>
                </span>
            </button>
        `).join("")}
    `;

    popover.querySelectorAll("[data-mode]").forEach((button) => {
        button.addEventListener("click", () => {
            state.mode = button.dataset.mode;
            store(STORAGE.mode, state.mode);
            popover.hidden = true;
            $("#toolsBtn").setAttribute("aria-expanded", "false");

            const label = MODE_OPTIONS.find((option) => option.key === state.mode)?.label || "Auto";
            toast(`Answer mode: ${label}`, "success", 1800);
        });
    });
}

/* ---------------------------------------------------------
   MODELS
   --------------------------------------------------------- */

const FALLBACK_MODELS = [
    { key: "jeff-balanced", label: "JeffAI Balanced", description: "The default. Fast and careful.", badge: "Default" },
    { key: "jeff-fast", label: "JeffAI Fast", description: "Instant replies.", badge: "Fastest" },
    { key: "jeff-smart", label: "JeffAI Smart", description: "Deeper answers.", badge: "Deep" },
    { key: "jeff-coder", label: "JeffAI Coder", description: "Code and debugging.", badge: "Code" },
];

async function loadModels() {
    try {
        const data = await api("/api/models");
        state.models = data.models?.length ? data.models : FALLBACK_MODELS;
    } catch (error) {
        state.models = FALLBACK_MODELS;
    }

    if (!state.models.some((model) => model.key === state.model)) {
        state.model = state.models[0]?.key || "jeff-balanced";
    }

    renderModelMenu();
    updateModelName();
}

function updateModelName() {
    const model = state.models.find((item) => item.key === state.model);
    $("#modelName").textContent = model?.label || "JeffAI";
}

function renderModelMenu() {
    const menu = $("#modelMenu");

    menu.innerHTML = state.models
        .map((model) => `
            <button class="model-option ${model.key === state.model ? "is-current" : ""}" type="button" role="option" aria-selected="${model.key === state.model}" data-model-key="${escapeHtml(model.key)}">
                <span>
                    <span class="model-option-title">
                        ${escapeHtml(model.label)}
                        ${model.badge ? `<span class="pill">${escapeHtml(model.badge)}</span>` : ""}
                    </span>
                    <span class="model-option-desc">${escapeHtml(model.description || "")}</span>
                </span>
                <span class="model-option-check">${icon("check", 16)}</span>
            </button>
        `)
        .join("");

    menu.querySelectorAll("[data-model-key]").forEach((button) => {
        button.addEventListener("click", () => {
            state.model = button.dataset.modelKey;
            store(STORAGE.model, state.model);
            updateModelName();
            renderModelMenu();
            menu.hidden = true;
            $("#modelTrigger").setAttribute("aria-expanded", "false");
            toast(`Model: ${state.models.find((item) => item.key === state.model)?.label}`, "success", 1800);
        });
    });
}

function setupModelSelector() {
    const trigger = $("#modelTrigger");
    const menu = $("#modelMenu");

    trigger.addEventListener("click", (event) => {
        event.stopPropagation();
        const willOpen = menu.hidden;
        menu.hidden = !willOpen;
        trigger.setAttribute("aria-expanded", String(willOpen));
    });

    document.addEventListener("click", (event) => {
        if (!menu.hidden && !menu.contains(event.target) && !trigger.contains(event.target)) {
            menu.hidden = true;
            trigger.setAttribute("aria-expanded", "false");
        }
    });
}

/* ---------------------------------------------------------
   SPEECH
   --------------------------------------------------------- */

function loadVoices() {
    if (!("speechSynthesis" in window)) {
        state.speechVoices = [];
        return;
    }

    state.speechVoices = window.speechSynthesis.getVoices() || [];

    populateVoiceSelects();
}

function populateVoiceSelects() {
    const select = $("#voiceSelect");
    if (!select) return;

    if (!state.speechVoices.length && "speechSynthesis" in window) {
        state.speechVoices = window.speechSynthesis.getVoices() || [];
    }

    const preferred = state.settings.voice;

    select.innerHTML = state.speechVoices.length
        ? state.speechVoices
            .map((voice) => `
                <option value="${escapeHtml(voice.name)}" ${voice.name === preferred ? "selected" : ""}>
                    ${escapeHtml(voice.name)} · ${escapeHtml(voice.lang)}
                </option>
            `)
            .join("")
        : '<option value="">No system voices found</option>';
}

function speakText(text, button = null) {
    if (!("speechSynthesis" in window)) {
        toast("Your browser cannot speak text aloud.", "error");
        return;
    }

    const clean = plainText(text);

    if (!clean) return;

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(clean);

    const voices = state.speechVoices.length
        ? state.speechVoices
        : window.speechSynthesis.getVoices();

    const chosen = voices.find((voice) => voice.name === state.settings.voice);
    if (chosen) utterance.voice = chosen;

    utterance.rate = state.settings.rate;

    if (button) {
        button.classList.add("is-on");
        button.innerHTML = icon("volume", 15);
        utterance.onend = () => button.classList.remove("is-on");
        utterance.onerror = () => button.classList.remove("is-on");
    }

    window.speechSynthesis.speak(utterance);
}

/* ---------------------------------------------------------
   VOICE RECORDING
   --------------------------------------------------------- */

function pickMimeType() {
    if (!window.MediaRecorder) return "";
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
    return candidates.find((type) => window.MediaRecorder.isTypeSupported?.(type)) || "";
}

async function startRecording() {
    if (!navigator.mediaDevices?.getUserMedia) {
        return startSpeechRecognition();
    }

    try {
        recorderStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorderChunks = [];

        const mimeType = pickMimeType();
        recorder = mimeType ? new MediaRecorder(recorderStream, { mimeType }) : new MediaRecorder(recorderStream);

        recorder.addEventListener("dataavailable", (event) => {
            if (event.data.size > 0) recorderChunks.push(event.data);
        });

        recorder.addEventListener("stop", async () => {
            recorderStream.getTracks().forEach((track) => track.stop());
            const blob = new Blob(recorderChunks, { type: recorder.mimeType || "audio/webm" });
            await transcribeBlob(blob);
        });

        recorder.start();

        const orb = $("#voiceOrb");
        orb.classList.add("is-listening");
        $("#voiceStatus").textContent = "Listening… tap again to stop";

        recorderTimer = setTimeout(() => stopRecording(), 60000);
        return undefined;
    } catch (error) {
        console.warn("Recording unavailable:", error);
        toast("Microphone unavailable. Falling back to live speech.", "info", 2800);
        return startSpeechRecognition();
    }
}

function stopRecording() {
    clearTimeout(recorderTimer);

    $("#voiceOrb").classList.remove("is-listening");
    $("#voiceStatus").textContent = "Transcribing…";

    if (recorder && recorder.state !== "inactive") {
        recorder.stop();
    }
}

async function transcribeBlob(blob) {
    const status = $("#voiceStatus");

    try {
        const form = new FormData();
        const extension = (blob.type || "audio/webm").includes("mp4") ? "m4a" : "webm";
        form.append("audio", blob, `recording.${extension}`);

        const data = await api("/api/transcribe", { method: "POST", body: form });

        if (data.text) {
            appendTranscript(data.text);
            status.textContent = "Heard you. Edit the text or send it.";
        } else {
            status.textContent = "I could not hear anything. Try again.";
        }
    } catch (error) {
        status.textContent = "Transcription failed. Try again, or type instead.";
        toast(normalizeError(error), "error");
    }
}

function appendTranscript(text) {
    const box = $("#voiceTranscript");
    if (!box) return;
    box.textContent = text;
}

function startSpeechRecognition() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!Recognition) {
        toast("Voice input is not supported in this browser. Type instead.", "error");
        return undefined;
    }

    if (recognition) {
        try {
            recognition.stop();
        } catch (error) {
            /* ignore */
        }
        recognition = null;
        $("#voiceOrb").classList.remove("is-listening");
        $("#voiceStatus").textContent = "Tap to start listening";
        return undefined;
    }

    recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = true;
    recognition.continuous = false;

    let finalText = "";

    recognition.onstart = () => {
        $("#voiceOrb").classList.add("is-listening");
        $("#voiceStatus").textContent = "Listening… speak now";
    };

    recognition.onresult = (event) => {
        let interim = "";
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
            const result = event.results[index];
            if (result.isFinal) finalText += result[0].transcript;
            else interim += result[0].transcript;
        }
        $("#voiceTranscript").textContent = (finalText + interim).trim();
    };

    recognition.onerror = () => {
        $("#voiceStatus").textContent = "I could not hear that. Try again.";
        $("#voiceOrb").classList.remove("is-listening");
        recognition = null;
    };

    recognition.onend = () => {
        $("#voiceOrb").classList.remove("is-listening");
        $("#voiceStatus").textContent = "Heard you. Edit the text or send it.";
        recognition = null;
    };

    recognition.start();
    return undefined;
}

function setupVoice() {
    $("#voiceOrb").addEventListener("click", () => {
        const listening = $("#voiceOrb").classList.contains("is-listening");

        if (listening) {
            if (recorder && recorder.state === "recording") {
                stopRecording();
            } else if (recognition) {
                recognition.stop();
            }
            return;
        }

        startRecording();
    });

    $("#voiceSendBtn").addEventListener("click", () => {
        const text = $("#voiceTranscript").textContent.trim();

        if (!text) {
            toast("Say or type something first.", "error");
            return;
        }

        setRoute("chat");
        $("#messageInput").value = text;
        autoResize();
        updateComposerState();
        $("#messageInput").focus();
        toast("Transcript moved to the chat box.", "success", 2200);
    });

    $("#voiceSpeakBtn").addEventListener("click", () => {
        const text = $("#voiceTranscript").textContent.trim();

        if (!text) {
            toast("There is nothing to read yet.", "info");
            return;
        }

        speakText(text);
    });

    $("#voiceCopyBtn").addEventListener("click", async () => {
        const text = $("#voiceTranscript").textContent.trim();
        const ok = await copyText(text);
        toast(ok ? "Transcript copied." : "Could not copy.", ok ? "success" : "error", 1800);
    });

    $("#voiceClearBtn").addEventListener("click", () => {
        $("#voiceTranscript").textContent = "";
        $("#voiceStatus").textContent = "Tap to start listening";
    });

    const autoToggle = $("#voiceAutoToggle");
    autoToggle.classList.toggle("is-on", state.settings.autoSpeak);
    autoToggle.setAttribute("aria-checked", String(state.settings.autoSpeak));

    autoToggle.addEventListener("click", () => {
        state.settings.autoSpeak = !state.settings.autoSpeak;
        store(STORAGE.autoSpeak, state.settings.autoSpeak);
        autoToggle.classList.toggle("is-on", state.settings.autoSpeak);
        autoToggle.setAttribute("aria-checked", String(state.settings.autoSpeak));
    });

    $("#voiceSelect").addEventListener("change", (event) => {
        state.settings.voice = event.target.value;
        store(STORAGE.voice, state.settings.voice);
        const preview = $("#voiceTranscript").textContent.trim();
        speakText(preview || "This is how I sound.", null);
    });

    const rate = $("#voiceRate");
    rate.value = String(state.settings.rate);
    $("#voiceRateValue").textContent = `${Number(state.settings.rate).toFixed(1)}×`;

    rate.addEventListener("input", () => {
        state.settings.rate = Number(rate.value);
        $("#voiceRateValue").textContent = `${state.settings.rate.toFixed(1)}×`;
        store(STORAGE.rate, state.settings.rate);
    });
}

/* ---------------------------------------------------------
   IMAGE STUDIO
   --------------------------------------------------------- */

function renderImageChips() {
    $("#imageStyles").innerHTML = IMAGE_STYLES
        .map((style) => `
            <button class="chip ${state.imageStyle === style.key ? "is-active" : ""}" type="button" data-style="${style.key}">
                ${escapeHtml(style.label)}
            </button>
        `)
        .join("");

    $("#imageAspects").innerHTML = IMAGE_ASPECTS
        .map((aspect) => `
            <button class="chip ${state.imageAspect === aspect.key ? "is-active" : ""}" type="button" data-aspect="${aspect.key}">
                ${escapeHtml(aspect.label)}
            </button>
        `)
        .join("");

    $("#imageStyles").querySelectorAll("[data-style]").forEach((button) => {
        button.addEventListener("click", () => {
            state.imageStyle = button.dataset.style;
            store(STORAGE.imageStyle, state.imageStyle);
            renderImageChips();
        });
    });

    $("#imageAspects").querySelectorAll("[data-aspect]").forEach((button) => {
        button.addEventListener("click", () => {
            state.imageAspect = button.dataset.aspect;
            store(STORAGE.imageAspect, state.imageAspect);
            renderImageChips();
        });
    });
}

function imageCard({ src, prompt, ratio = "1 / 1", onDelete, downloadName }) {
    const card = document.createElement("div");
    card.className = "gallery-card";
    card.style.setProperty("--ratio", ratio);

    card.innerHTML = `
        <img alt="${escapeHtml(prompt || "Generated image")}" loading="lazy">
        <div class="gallery-overlay">
            <span class="gallery-prompt">${escapeHtml(prompt || "")}</span>
            <button class="mini-btn" type="button" data-download title="Download">${icon("download", 14)}</button>
            <button class="mini-btn" type="button" data-copy-prompt title="Copy prompt">${icon("copy", 14)}</button>
            ${onDelete ? `<button class="mini-btn" type="button" data-remove title="Delete">${icon("trash", 14)}</button>` : ""}
        </div>
    `;

    const img = card.querySelector("img");

    img.addEventListener("error", () => {
        card.classList.add("is-broken");

        if (card.querySelector(".gallery-fallback")) return;

        const fallback = document.createElement("div");
        fallback.className = "gallery-fallback";
        fallback.innerHTML = `
            ${icon("image", 22)}
            <span>${escapeHtml((prompt || "Image unavailable").slice(0, 70))}</span>
        `;
        card.prepend(fallback);
    });

    img.src = src;

    card.querySelector("[data-download]").addEventListener("click", async () => {
        try {
            const response = await fetch(src);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = downloadName || `jeffai-${Date.now()}.png`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 4000);
            toast("Image downloaded.", "success", 2000);
        } catch (error) {
            window.open(src, "_blank");
        }
    });

    card.querySelector("[data-copy-prompt]").addEventListener("click", async () => {
        const ok = await copyText(prompt || "");
        toast(ok ? "Prompt copied." : "Could not copy.", ok ? "success" : "error", 1800);
    });

    if (onDelete) {
        card.querySelector("[data-remove]").addEventListener("click", () => onDelete(card));
    }

    return card;
}

function addGeneratedImage(image) {
    state.lastGenerated.unshift(image);

    $("#imageResultsPanel").hidden = false;

    const gallery = $("#imageResults");
    const ratio = IMAGE_ASPECTS.find((aspect) => aspect.key === image.aspect)?.ratio || "1 / 1";

    const card = imageCard({
        src: image.data_url || image.url,
        prompt: image.prompt,
        ratio,
        downloadName: `jeffai-${Date.now()}.png`,
        onDelete: async (node) => {
            node.remove();
            if (!gallery.children.length) $("#imageResultsPanel").hidden = true;
            if (image.saved_id) {
                try {
                    await api(`/api/images/${image.saved_id}`, { method: "DELETE" });
                    loadImageHistory();
                } catch (error) {
                    toast(normalizeError(error), "error");
                }
            }
        },
    });

    gallery.prepend(card);
}

async function generateImage() {
    const prompt = $("#imagePrompt").value.trim();

    if (!prompt) {
        toast("Describe the image you want first.", "error");
        $("#imagePrompt").focus();
        return;
    }

    const button = $("#imageGenerateBtn");
    const status = $("#imageStatus");

    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Generating…`;
    status.textContent = "Painting your idea… this can take a few seconds.";

    try {
        const data = await api("/api/images/generate", {
            method: "POST",
            body: JSON.stringify({
                prompt,
                style: state.imageStyle,
                aspect: state.imageAspect,
            }),
        });

        addGeneratedImage({
            ...data.image,
            aspect: state.imageAspect,
            saved_id: data.image.saved_id,
        });

        status.textContent = data.image.saved_id
            ? "Saved to your gallery."
            : "Generated. Save it by downloading if you want to keep it.";

        if (data.image.saved_id) loadImageHistory();

        toast("Image ready.", "success", 2200);
    } catch (error) {
        status.textContent = "Generation failed.";
        toast(normalizeError(error), "error", 6000);
    } finally {
        button.disabled = false;
        button.innerHTML = `${icon("wand", 16)} Generate image`;
    }
}

async function loadImageHistory() {
    const gallery = $("#imageHistory");
    const empty = $("#imageHistoryEmpty");

    try {
        const data = await api("/api/images");
        const images = data.images || [];

        gallery.innerHTML = "";

        if (!images.length) {
            empty.hidden = false;
            return;
        }

        empty.hidden = true;

        images.forEach((image) => {
            if (!image.url) return;

            gallery.appendChild(
                imageCard({
                    src: image.url,
                    prompt: image.prompt,
                    downloadName: `jeffai-${image.id}.png`,
                    onDelete: async (node) => {
                        node.remove();
                        try {
                            await api(`/api/images/${image.id}`, { method: "DELETE" });
                            toast("Image deleted.", "success", 1800);
                            if (!gallery.children.length) empty.hidden = false;
                        } catch (error) {
                            toast(normalizeError(error), "error");
                        }
                    },
                })
            );
        });
    } catch (error) {
        empty.hidden = false;
    }
}

/* ---------------------------------------------------------
   VISION
   --------------------------------------------------------- */

function setupVision() {
    const drop = $("#visionDrop");
    const input = $("#visionInput");

    const presets = $("#visionPresets");
    presets.innerHTML = VISION_PRESETS
        .map((preset) => `<button class="chip" type="button" data-preset="${escapeHtml(preset)}">${escapeHtml(preset)}</button>`)
        .join("");

    presets.querySelectorAll("[data-preset]").forEach((button) => {
        button.addEventListener("click", () => {
            $("#visionQuestion").value = button.dataset.preset;
        });
    });

    const choose = () => input.click();

    drop.addEventListener("click", choose);
    drop.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            choose();
        }
    });

    ["dragenter", "dragover"].forEach((type) => {
        drop.addEventListener(type, (event) => {
            event.preventDefault();
            drop.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach((type) => {
        drop.addEventListener(type, (event) => {
            event.preventDefault();
            drop.classList.remove("is-dragging");
        });
    });

    drop.addEventListener("drop", (event) => {
        const file = event.dataTransfer?.files?.[0];
        if (file) setVisionFile(file);
    });

    input.addEventListener("change", (event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) setVisionFile(file);
    });

    document.addEventListener("paste", (event) => {
        if (state.route !== "vision") return;
        const item = Array.from(event.clipboardData?.items || []).find((entry) =>
            entry.type.startsWith("image/")
        );
        const file = item?.getAsFile();
        if (file) setVisionFile(file);
    });

    $("#visionClear").addEventListener("click", () => {
        state.visionFile = null;
        $("#visionPreviewWrap").hidden = true;
        $("#visionStatus").textContent = "No image selected.";
        $("#visionQuestion").value = "";
        $("#visionAnswerPanel").hidden = true;
    });

    $("#visionAskBtn").addEventListener("click", askAboutImage);

    $("#visionCopy").addEventListener("click", async () => {
        const ok = await copyText(plainText(state.visionAnswer));
        toast(ok ? "Answer copied." : "Could not copy.", ok ? "success" : "error", 1800);
    });

    $("#visionContinue").addEventListener("click", () => {
        if (!state.visionAnswer) return;

        setRoute("chat");

        $("#messageInput").value =
            `About the image I showed you: ${plainText(state.visionAnswer).slice(0, 700)}\n\n` +
            "Now answer my question: ";
        autoResize();
        updateComposerState();
        $("#messageInput").focus();
    });
}

function setVisionFile(file) {
    if (!file.type.startsWith("image/")) {
        toast("Please choose an image file.", "error");
        return;
    }

    if (file.size > 8 * 1024 * 1024) {
        toast("That image is larger than 8 MB.", "error");
        return;
    }

    state.visionFile = file;

    const preview = $("#visionPreview");
    preview.src = URL.createObjectURL(file);
    $("#visionPreviewWrap").hidden = false;
    $("#visionFileName").textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
    $("#visionStatus").textContent = "Image ready.";
}

async function askAboutImage() {
    if (!state.visionFile) {
        toast("Choose an image first.", "error");
        return;
    }

    const button = $("#visionAskBtn");
    const status = $("#visionStatus");
    const question = $("#visionQuestion").value.trim();

    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Looking…`;
    status.textContent = "JeffAI is looking at your image…";

    try {
        const form = new FormData();
        form.append("image", state.visionFile);
        form.append("question", question);

        const data = await api("/api/vision", { method: "POST", body: form });

        state.visionAnswer = data.answer || "";

        $("#visionAnswerPanel").hidden = false;
        $("#visionAnswer").innerHTML = renderMarkdown(state.visionAnswer);

        status.textContent = "Done. Ask a follow-up or continue in chat.";

        if (state.settings.autoSpeak) speakText(state.visionAnswer);
    } catch (error) {
        status.textContent = "Could not read that image.";
        toast(normalizeError(error), "error", 6000);
    } finally {
        button.disabled = false;
        button.innerHTML = `${icon("sparkles", 16)} Understand image`;
    }
}

/* ---------------------------------------------------------
   DOCUMENTS
   --------------------------------------------------------- */

function documentIcon(type) {
    return (type || "file").toUpperCase().slice(0, 4);
}

function documentItem(doc, { onAnalyse } = {}) {
    const row = document.createElement("div");
    row.className = "list-item";

    row.innerHTML = `
        <span class="list-icon">${escapeHtml(documentIcon(doc.file_type || "file"))}</span>
        <span class="list-main">
            <span class="list-title">${escapeHtml(doc.filename || "Document")}</span>
            <span class="list-sub">${escapeHtml(formatDate(doc.created_at))}</span>
        </span>
        <span class="list-actions">
            ${onAnalyse ? `<button class="mini-btn" type="button" data-analyse title="Analyse" aria-label="Analyse document">${icon("sparkles", 14)}</button>` : ""}
            <button class="mini-btn" type="button" data-chat title="Ask about this document" aria-label="Ask about this document">${icon("chat", 14)}</button>
            <button class="mini-btn danger" type="button" data-remove title="Delete" aria-label="Delete document">${icon("trash", 14)}</button>
        </span>
    `;

    row.querySelector("[data-chat]").addEventListener("click", () => {
        setRoute("chat");
        $("#messageInput").value = `Summarise the document "${doc.filename}" and tell me what matters most.`;
        autoResize();
        updateComposerState();
        $("#messageInput").focus();
    });

    row.querySelector("[data-analyse]")?.addEventListener("click", () => {
        onAnalyse(row, doc);
    });

    row.querySelector("[data-remove]").addEventListener("click", async () => {
        const confirmed = await confirmAction({
            title: "Delete this document?",
            text: `"${doc.filename}" will be removed from your saved files.`,
            okLabel: "Delete file",
        });

        if (!confirmed) return;

        try {
            await api(`/api/documents/${doc.id}`, { method: "DELETE" });
            row.remove();
            toast("Document deleted.", "success", 2000);
            loadFiles();
        } catch (error) {
            toast(normalizeError(error), "error");
        }
    });

    return row;
}

async function analyseDocument(row, doc) {
    const choice = await promptAnalyseChoice(row);

    if (!choice) return;

    const sub = row.querySelector(".list-sub");
    const original = sub.textContent;

    sub.innerHTML = '<span class="spinner" style="display:inline-block;vertical-align:-2px"></span> Analysing…';

    try {
        const data = await api(`/api/documents/${doc.id}/analyze`, {
            method: "POST",
            body: JSON.stringify({ task: choice }),
        });

        sub.textContent = original;

        showAnalysisPanel(doc, choice, data.answer || "");

        toast("Analysis ready above.", "success", 2200);
    } catch (error) {
        sub.textContent = original;
        toast(normalizeError(error), "error", 6000);
    }
}

function showAnalysisPanel(doc, task, answer) {
    const container = $("#view-documents .view-inner");

    let panel = $("#analysisPanel");

    if (!panel) {
        panel = document.createElement("div");
        panel.className = "panel";
        panel.id = "analysisPanel";
        container.insertBefore(panel, container.querySelector(".panel"));
    }

    panel.innerHTML = `
        <div class="panel-head">
            <h3 class="panel-title">${icon("brain", 17)} ${escapeHtml(labelForTask(task))} · ${escapeHtml(doc.filename || "Document")}</h3>
            <div class="foot-row">
                <button class="btn btn-sm btn-ghost" type="button" data-copy>${icon("copy", 15)} Copy</button>
                <button class="btn btn-sm btn-ghost" type="button" data-close aria-label="Close">${icon("close", 15)}</button>
            </div>
        </div>
        <div class="message-body" id="analysisBody"></div>
    `;

    $("#analysisBody").innerHTML = renderMarkdown(answer);

    panel.querySelector("[data-copy]").addEventListener("click", async () => {
        const ok = await copyText(plainText(answer));
        toast(ok ? "Analysis copied." : "Could not copy.", ok ? "success" : "error", 1800);
    });

    panel.querySelector("[data-close]").addEventListener("click", () => panel.remove());

    panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function labelForTask(task) {
    return {
        summary: "Summary",
        keypoints: "Key points",
        action: "Action items",
        explain: "Plain explanation",
        questions: "Study questions",
    }[task] || "Analysis";
}

function promptAnalyseChoice(anchor) {
    return new Promise((resolve) => {
        const popover = document.createElement("div");
        popover.className = "model-menu";
        popover.style.position = "fixed";
        popover.style.width = "220px";

        const choices = [
            { key: "summary", label: "Summarise" },
            { key: "keypoints", label: "Key points" },
            { key: "action", label: "Action items" },
            { key: "explain", label: "Explain simply" },
            { key: "questions", label: "Study questions" },
        ];

        popover.innerHTML = `<div class="popover-label">Analyse with JeffAI</div>` +
            choices
                .map((choice) => `<button class="popover-item" type="button" data-choice="${choice.key}">${escapeHtml(choice.label)}</button>`)
                .join("");

        document.body.appendChild(popover);

        const rect = anchor?.getBoundingClientRect();

        if (rect) {
            popover.style.left = `${Math.min(window.innerWidth - 236, Math.max(12, rect.left))}px`;
            popover.style.top = `${Math.min(window.innerHeight - 250, rect.bottom + 8)}px`;
        } else {
            popover.style.left = "50%";
            popover.style.top = "30%";
        }

        const cleanup = (value) => {
            popover.remove();
            document.removeEventListener("click", outside);
            resolve(value);
        };

        const outside = (event) => {
            if (!popover.contains(event.target)) cleanup(null);
        };

        setTimeout(() => document.addEventListener("click", outside), 10);

        popover.querySelectorAll("[data-choice]").forEach((button) => {
            button.addEventListener("click", () => cleanup(button.dataset.choice));
        });
    });
}

async function loadDocuments() {
    const list = $("#docList");
    const empty = $("#docEmpty");

    try {
        const data = await api("/api/documents");
        const documents = data.documents || [];

        list.innerHTML = "";
        $("#docCount").textContent = documents.length ? `${documents.length} file${documents.length === 1 ? "" : "s"}` : "";

        if (!documents.length) {
            empty.hidden = false;
            return;
        }

        empty.hidden = true;

        documents.forEach((doc) => {
            list.appendChild(documentItem(doc, { onAnalyse: analyseDocument }));
        });
    } catch (error) {
        empty.hidden = false;
        $("#docCount").textContent = "";
    }
}

function setupDocuments() {
    const drop = $("#docDrop");
    const input = $("#docInput");

    const choose = () => input.click();

    drop.addEventListener("click", choose);
    drop.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            choose();
        }
    });

    ["dragenter", "dragover"].forEach((type) => {
        drop.addEventListener(type, (event) => {
            event.preventDefault();
            drop.classList.add("is-dragging");
        });
    });

    ["dragleave", "drop"].forEach((type) => {
        drop.addEventListener(type, (event) => {
            event.preventDefault();
            drop.classList.remove("is-dragging");
        });
    });

    drop.addEventListener("drop", async (event) => {
        const file = event.dataTransfer?.files?.[0];
        if (file) await handleDocumentUpload(file);
    });

    input.addEventListener("change", async (event) => {
        const file = event.target.files?.[0];
        event.target.value = "";
        if (file) await handleDocumentUpload(file);
    });

    $("#docRefresh").addEventListener("click", loadDocuments);

    $("#pdfMakeBtn").addEventListener("click", createPdf);
}

async function handleDocumentUpload(file) {
    const status = $("#docStatus");
    status.textContent = `Uploading ${file.name}…`;

    try {
        const data = await api("/api/documents", {
            method: "POST",
            body: (() => {
                const form = new FormData();
                form.append("file", file);
                return form;
            })(),
        });

        status.textContent = `"${file.name}" is ready. Ask about it in chat or analyse it below.`;

        await loadDocuments();

        const row = documentItem(data.document, { onAnalyse: analyseDocument });
        $("#docList").prepend(row);
        $("#docEmpty").hidden = true;

        toast("Document uploaded.", "success");
    } catch (error) {
        status.textContent = "Upload failed.";
        toast(normalizeError(error), "error");
    }
}

async function createPdf() {
    const text = $("#pdfText").value.trim();
    const title = $("#pdfTitle").value.trim() || "JeffAI Document";

    if (!text) {
        toast("Add some text to convert.", "error");
        return;
    }

    const button = $("#pdfMakeBtn");
    const status = $("#pdfStatus");

    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> Creating…`;
    status.textContent = "Building your PDF…";

    try {
        const headers = await authHeaders(true);

        const response = await fetch(`${API_BASE}/api/convert/text-to-pdf`, {
            method: "POST",
            headers,
            body: JSON.stringify({ text, title }),
        });

        if (!response.ok) {
            let message = "Could not create the PDF.";
            try {
                const payload = await response.json();
                message = payload.error || message;
            } catch (error) {
                /* ignore */
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${title.replace(/[^\w\s-]/g, "").trim() || "JeffAI-Document"}.pdf`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);

        status.textContent = "PDF downloaded.";
        toast("PDF ready.", "success", 2200);
    } catch (error) {
        status.textContent = "Could not create the PDF.";
        toast(normalizeError(error), "error");
    } finally {
        button.disabled = false;
        button.innerHTML = `${icon("download", 16)} Create PDF`;
    }
}

/* ---------------------------------------------------------
   FILES
   --------------------------------------------------------- */

function setupFiles() {
    $$("[data-files-tab]").forEach((button) => {
        button.addEventListener("click", () => {
            state.filesTab = button.dataset.filesTab;

            $$("[data-files-tab]").forEach((chip) => {
                chip.classList.toggle("is-active", chip === button);
            });

            $("#filesDocumentsPanel").hidden = state.filesTab !== "documents";
            $("#filesImagesPanel").hidden = state.filesTab !== "images";
        });
    });

    $("#filesRefresh").addEventListener("click", loadFiles);
}

async function loadFiles() {
    try {
        const data = await api("/api/files");

        const documents = data.documents || [];
        const images = data.images || [];

        const docList = $("#filesDocuments");
        docList.innerHTML = "";
        $("#filesDocumentsEmpty").hidden = documents.length > 0;

        documents.forEach((doc) => {
            docList.appendChild(documentItem(doc, { onAnalyse: analyseDocument }));
        });

        const imageGallery = $("#filesImages");
        imageGallery.innerHTML = "";
        $("#filesImagesEmpty").hidden = images.length > 0;

        images.forEach((image) => {
            if (!image.url) return;

            imageGallery.appendChild(
                imageCard({
                    src: image.url,
                    prompt: image.prompt,
                    downloadName: `jeffai-${image.id}.png`,
                    onDelete: async (node) => {
                        node.remove();
                        try {
                            await api(`/api/images/${image.id}`, { method: "DELETE" });
                            toast("Image deleted.", "success", 1800);
                            if (!imageGallery.children.length) $("#filesImagesEmpty").hidden = false;
                        } catch (error) {
                            toast(normalizeError(error), "error");
                        }
                    },
                })
            );
        });
    } catch (error) {
        $("#filesDocumentsEmpty").hidden = false;
        $("#filesImagesEmpty").hidden = false;
    }
}

/* ---------------------------------------------------------
   SETTINGS
   --------------------------------------------------------- */

function bindToggle(id, key, onChange) {
    const button = $(`#${id}`);
    if (!button) return;

    const sync = () => {
        button.classList.toggle("is-on", Boolean(state.settings[key]));
        button.setAttribute("aria-checked", String(Boolean(state.settings[key])));
    };

    sync();

    button.addEventListener("click", () => {
        state.settings[key] = !state.settings[key];
        store(STORAGE[key], state.settings[key]);
        sync();
        if (onChange) onChange(state.settings[key]);
    });
}

function setupSettings() {
    const openSettings = () => {
        openOverlay("settingsOverlay");
        loadMemories();
        populateVoiceSelects();
        applyTheme(currentTheme(), false);
        $("#aboutVersion").textContent = "v2.0";
        $("#accountEmail").textContent = state.user?.email || "Signed in";
    };

    ["#settingsBtn", "#settingsBtnTop", "#userChip"].forEach((selector) => {
        $(selector)?.addEventListener("click", openSettings);
    });

    $("#settingsClose").addEventListener("click", () => closeOverlay("settingsOverlay"));

    $("#settingsOverlay").addEventListener("click", (event) => {
        if (event.target.id === "settingsOverlay") closeOverlay("settingsOverlay");
    });

    $$("#themeCards [data-theme-choice]").forEach((card) => {
        card.addEventListener("click", () => applyTheme(card.dataset.themeChoice));
    });

    bindToggle("settingEnter", "enter");
    bindToggle("settingStreaming", "streaming");

    bindToggle("settingMemory", "memory", (enabled) => {
        $("#memoryList").style.opacity = enabled ? "1" : ".5";
    });

    $("#memoryAdd").addEventListener("click", addMemory);

    $("#memoryInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            addMemory();
        }
    });

    $("#signOutBtn").addEventListener("click", signOut);
}

async function loadMemories() {
    const list = $("#memoryList");
    const empty = $("#memoryEmpty");

    try {
        const data = await api("/api/memories");
        state.memories = data.memories || [];

        list.innerHTML = "";

        if (!state.memories.length) {
            empty.hidden = false;
            return;
        }

        empty.hidden = true;

        state.memories.forEach((memory) => {
            const row = document.createElement("div");
            row.className = "list-item";
            row.innerHTML = `
                <span class="list-icon">${icon("brain", 16)}</span>
                <span class="list-main">
                    <span class="list-title" style="white-space:normal">${escapeHtml(memory.memory)}</span>
                    <span class="list-sub">${escapeHtml(formatDate(memory.created_at))}</span>
                </span>
                <span class="list-actions">
                    <button class="mini-btn danger" type="button" title="Forget" aria-label="Forget this memory">${icon("trash", 14)}</button>
                </span>
            `;

            row.querySelector("button").addEventListener("click", async () => {
                try {
                    await api(`/api/memories/${memory.id}`, { method: "DELETE" });
                    row.remove();
                    toast("Memory removed.", "success", 1800);
                } catch (error) {
                    toast(normalizeError(error), "error");
                }
            });

            list.appendChild(row);
        });
    } catch (error) {
        empty.hidden = false;
    }
}

async function addMemory() {
    const input = $("#memoryInput");
    const value = input.value.trim();

    if (!value) return;

    try {
        await api("/api/memories", {
            method: "POST",
            body: JSON.stringify({ memory: value }),
        });

        input.value = "";
        toast("JeffAI will remember that.", "success", 2000);
        loadMemories();
    } catch (error) {
        toast(normalizeError(error), "error");
    }
}

async function signOut() {
    const confirmed = await confirmAction({
        title: "Sign out of JeffAI?",
        text: "Your chats stay saved on your account. You can sign back in any time.",
        okLabel: "Sign out",
        danger: false,
    });

    if (!confirmed) return;

    await supabase.auth.signOut();
    window.location.href = "/login.html";
}

/* ---------------------------------------------------------
   BOOT
   --------------------------------------------------------- */

function setupSidebar() {
    $("#newChatBtn").addEventListener("click", newChat);
    $("#brandButton").addEventListener("click", newChat);

    $("#collapseBtn").addEventListener("click", () => {
        const isMobile = window.matchMedia("(max-width: 900px)").matches;

        if (isMobile) {
            $("#app").classList.remove("is-drawer-open");
            return;
        }

        setCollapsed(!$("#app").classList.contains("is-collapsed"));
    });

    $("#mobileMenuBtn").addEventListener("click", () => {
        $("#app").classList.add("is-drawer-open");
    });

    $("#drawerScrim").addEventListener("click", () => {
        $("#app").classList.remove("is-drawer-open");
    });

    $("#conversationSearch").addEventListener("input", debounce(renderConversations, 120));

    $$(".nav-item[data-route]").forEach((item) => {
        item.addEventListener("click", () => setRoute(item.dataset.route));
    });
}

function setupKeyboard() {
    document.addEventListener("keydown", (event) => {
        const meta = event.metaKey || event.ctrlKey;

        if (event.key === "Escape") {
            closeAllOverlays();
            $("#app").classList.remove("is-drawer-open");
            $("#modelMenu").hidden = true;
            $("#toolsPopover").hidden = true;
            return;
        }

        if (meta && event.key.toLowerCase() === "k") {
            event.preventDefault();
            $("#app").classList.remove("is-collapsed");
            $("#conversationSearch").focus();
            return;
        }

        if (meta && event.key.toLowerCase() === "j") {
            event.preventDefault();
            newChat();
            return;
        }

        if (meta && event.key.toLowerCase() === "b") {
            event.preventDefault();
            setCollapsed(!$("#app").classList.contains("is-collapsed"));
        }
    });
}

function setupUserChrome() {
    const email = state.user?.email || "";
    $("#userEmail").textContent = email;

    const name = email.split("@")[0] || "Your account";
    $("#userName").textContent = name;
    $("#userAvatar").textContent = initialsFrom(email);
    $("#accountEmail").textContent = email || "Signed in";
}

/* =========================================================
   ANDROID DOWNLOAD
   ========================================================= */

const releaseState = { ready: false, data: null };

async function initAppRelease() {
    const button = $("#downloadApkBtn");

    if (!button) return;

    button.classList.add("is-pending");

    try {
        const response = await fetch(`${API_BASE}/api/app-release`, {
            headers: { Accept: "application/json" },
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const release = await response.json();

        releaseState.ready = true;
        releaseState.data = release;

        if (!release.available || !release.url) {
            button.classList.add("is-unavailable");
            button.dataset.unavailable = release.message || "The Android app is not published yet.";
            button.title = button.dataset.unavailable;
            button.setAttribute("aria-label", `Download APK. ${button.dataset.unavailable}`);
            return;
        }

        const url = release.source === "external" ? release.url : `${API_BASE}${release.url}`;
        const details = [release.filename, release.size_label].filter(Boolean).join(" · ");

        button.classList.remove("is-unavailable");
        button.setAttribute("aria-label", "Download the JeffAI Android app");
        button.href = url;
        button.setAttribute("download", release.filename || "JeffAI.apk");
        button.title = release.installable === false
            ? `Download ${details} (this build is not signed and will not install)`
            : `Download ${details}`;

        if (release.source === "external") {
            button.removeAttribute("download");
            button.target = "_blank";
            button.rel = "noopener";
        }
    } catch (error) {
        console.warn("[JeffAI] release lookup failed", error);
        button.classList.remove("is-pending");
        return;
    } finally {
        button.classList.remove("is-pending");
    }
}

function handleAppReleaseClick(event) {
    const button = event.currentTarget;
    const release = releaseState.data;

    if (!releaseState.ready) return;              // let the plain link work
    if (!release?.available) {
        event.preventDefault();
        toast(button.dataset.unavailable || "The Android app is not published yet.", "error", 9000);
        return;
    }

    const details = [release.filename, release.size_label].filter(Boolean).join(" · ");

    if (release.installable === false) {
        toast(
            `Downloading ${details}. Note: this build is not signed, so Android will refuse to install it.`,
            "error",
            9000
        );
        return;
    }

    toast(`Downloading ${details}…`, "success", 3200);
}

async function init() {
    applyTheme(read(STORAGE.theme, "dark"), false);

    const apkButton = $("#downloadApkBtn");

    apkButton?.addEventListener("click", handleAppReleaseClick);

    initAppRelease();

    const libsReady = await ensureLibs();

    if (!libsReady) {
        document.body.innerHTML = `
            <div style="display:grid;place-items:center;height:100dvh;font-family:system-ui;padding:24px;text-align:center">
                <div>
                    <h1 style="font-size:20px;margin-bottom:8px">JeffAI could not load</h1>
                    <p style="color:#8b93a7;max-width:34ch;margin:0 auto 16px">A required script failed to load. Check your connection and refresh.</p>
                    <button onclick="location.reload()" style="padding:10px 16px;border-radius:10px;border:0;background:#6366f1;color:#fff;font-weight:600">Reload</button>
                </div>
            </div>`;
        return;
    }

    try {
        await initSupabase();
    } catch (error) {
        console.error("[JeffAI] configuration problem", error);
        renderConfigError(normalizeError(error));
        toast("JeffAI is not configured. See the message in the chat area.", "error", 8000);
        return;
    }

    const session = await ensureSession(true);

    if (!session) {
        window.location.href = "/login.html";
        return;
    }

    state.user = {
        id: session.user.id,
        email: session.user.email,
        initials: initialsFrom(session.user.email),
    };

    setupUserChrome();

    setCollapsed(read(STORAGE.collapsed, false));

    setupSidebar();
    setupComposer();
    setupModelSelector();
    setupSettings();
    setupVoice();
    setupVision();
    setupDocuments();
    setupFiles();
    setupKeyboard();

    renderImageChips();

    $("#themeBtn").addEventListener("click", toggleTheme);
    $("#themeBtnTop").addEventListener("click", toggleTheme);
    $("#logoutBtn").addEventListener("click", signOut);

    $("#imageGenerateBtn").addEventListener("click", generateImage);
    $("#imageResultClear").addEventListener("click", () => {
        $("#imageResults").innerHTML = "";
        $("#imageResultsPanel").hidden = true;
    });
    $("#imageHistoryRefresh").addEventListener("click", loadImageHistory);

    /* collapse the drawer once a view is chosen on mobile */
    $$(".view").forEach((view) => {
        view.addEventListener("click", () => {
            if (window.matchMedia("(max-width: 900px)").matches) {
                $("#app").classList.remove("is-drawer-open");
            }
        });
    });

    loadVoices();
    if ("speechSynthesis" in window) {
        window.speechSynthesis.onvoiceschanged = loadVoices;
    }

    supabase.auth.onAuthStateChange((event) => {
        if (event === "SIGNED_OUT") window.location.href = "/login.html";
    });

    const startRoute = (window.location.hash || "").replace(/^#\/?/, "") || "chat";
    setRoute(ROUTE_META[startRoute] ? startRoute : "chat", { silent: true });

    showWelcome();
    updateComposerState();
    autoResize();

    await Promise.all([loadModels(), loadConversations()]);

    if (startRoute === "images") loadImageHistory();
    if (startRoute === "files") loadFiles();

    $("#messageInput").focus();
}

window.addEventListener("DOMContentLoaded", () => {
    init().catch((error) => {
        console.error("JeffAI init failed:", error);
        toast(normalizeError(error), "error", 8000);
    });
});

window.addEventListener("offline", () => toast("You are offline. JeffAI needs a connection.", "error", 5000));
window.addEventListener("online", () => toast("Back online.", "success", 2200));
