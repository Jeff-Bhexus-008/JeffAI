/* =========================================================
   JeffAI markdown renderer
   Created by Amedu Vincent Onjefu (Jeff Bhexus)

   Wraps marked + highlight.js + DOMPurify so every assistant
   answer is safe, formatted, syntax highlighted, and copyable.
   ========================================================= */

const LANGUAGE_LABELS = {
    py: "Python",
    js: "JavaScript",
    ts: "TypeScript",
    jsx: "React",
    tsx: "React",
    html: "HTML",
    css: "CSS",
    json: "JSON",
    bash: "Shell",
    sh: "Shell",
    sql: "SQL",
    java: "Java",
    kotlin: "Kotlin",
    swift: "Swift",
    go: "Go",
    rust: "Rust",
    c: "C",
    cpp: "C++",
    csharp: "C#",
    php: "PHP",
    rb: "Ruby",
    yaml: "YAML",
    md: "Markdown",
    txt: "Text",
};

let configured = false;

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function configure() {
    if (configured || !window.marked) return;

    const renderer = new window.marked.Renderer();

    renderer.code = function (code, language) {
        const raw = typeof code === "string" ? code : code?.text || "";
        const lang = (language || "").trim().split(/\s+/)[0].toLowerCase();
        let highlighted = escapeHtml(raw);
        let resolvedlang = lang;

        if (window.hljs) {
            try {
                if (lang && window.hljs.getLanguage(lang)) {
                    highlighted = window.hljs.highlight(raw, {
                        language: lang,
                        ignoreIllegals: true,
                    }).value;
                } else {
                    const auto = window.hljs.highlightAuto(raw);
                    highlighted = auto.value;
                    resolvedlang = auto.language || "";
                }
            } catch (error) {
                highlighted = escapeHtml(raw);
            }
        }

        const label =
            LANGUAGE_LABELS[resolvedlang] ||
            (resolvedlang ? resolvedlang.toUpperCase() : "Code");

        return `
<div class="code-card">
    <div class="code-head">
        <span class="code-lang">${escapeHtml(label)}</span>
        <button class="code-copy" type="button" data-copy-code aria-label="Copy code">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 4h9a2 2 0 0 1 2 2v9"/><rect x="5" y="8" width="11" height="12" rx="2"/></svg>
            <span>Copy</span>
        </button>
    </div>
    <pre class="code-body"><code class="hljs">${highlighted}</code></pre>
</div>`;
    };

    renderer.codespan = function (code) {
        const text = typeof code === "string" ? code : code?.text || "";
        return `<code class="inline-code">${escapeHtml(text)}</code>`;
    };

    renderer.link = function (href, title, text) {
        const url = typeof href === "string" ? href : href?.href || "#";
        const safe = /^(https?:|mailto:)/i.test(url) ? url : "#";
        const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
        return `<a href="${escapeHtml(safe)}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`;
    };

    renderer.table = function (header, body) {
        return `<div class="table-scroll"><table><thead>${header}</thead><tbody>${body}</tbody></table></div>`;
    };

    window.marked.setOptions({
        renderer,
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
    });

    configured = true;
}

export function renderMarkdown(text) {
    configure();

    const source = String(text ?? "");

    if (!window.marked) {
        return `<p>${escapeHtml(source).replace(/\n/g, "<br>")}</p>`;
    }

    let html = window.marked.parse(source);

    if (window.DOMPurify) {
        html = window.DOMPurify.sanitize(html, {
            ADD_ATTR: ["target", "rel", "data-copy-code"],
            ADD_TAGS: ["svg", "path", "rect", "span"],
        });
    }

    return html;
}

export function plainText(text) {
    configure();

    if (!window.marked) return String(text ?? "");

    const html = window.marked.parse(String(text ?? ""));

    const holder = document.createElement("div");
    holder.innerHTML = window.DOMPurify
        ? window.DOMPurify.sanitize(html)
        : html;

    return (holder.textContent || "").trim();
}

/* One delegated listener handles every copy button in the app. */
document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-code]");

    if (!button) return;

    const card = button.closest(".code-card");
    const code = card?.querySelector("code");
    const text = code ? code.innerText : "";

    try {
        await navigator.clipboard.writeText(text);
        const label = button.querySelector("span");
        const previous = label ? label.textContent : "";
        button.classList.add("copied");
        if (label) label.textContent = "Copied";
        setTimeout(() => {
            button.classList.remove("copied");
            if (label) label.textContent = previous || "Copy";
        }, 1600);
    } catch (error) {
        console.warn("Copy failed", error);
    }
});

export async function copyText(text) {
    try {
        await navigator.clipboard.writeText(String(text ?? ""));
        return true;
    } catch (error) {
        return false;
    }
}

export { escapeHtml };
