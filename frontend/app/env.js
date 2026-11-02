/* =========================================================
   JeffAI environment resolution
   Created by Amedu Vincent Onjefu (Jeff Bhexus)

   One place that answers two questions:
     1. Where is the Flask API?
     2. Which Supabase project should the browser talk to?

   The backend is authoritative for the Supabase project so the
   frontend and the server can never drift apart again: if the
   project is migrated, changing the Render environment variables is
   enough and the browser picks it up on the next load. The bundled
   frontend/config.js is only a fallback for the Android shell or
   when the API is unreachable.
   ========================================================= */

const REMOTE_API = "https://jeffai-pwit.onrender.com";

const NATIVE_SHELL =
    window.location.protocol === "capacitor:" ||
    window.location.protocol === "file:" ||
    (window.location.hostname === "localhost" && !window.location.port);

export const API_BASE =
    window.JEFFAI_API_BASE ?? (NATIVE_SHELL ? REMOTE_API : "");

export class ConfigError extends Error {}

let resolved = null;

export function hostOf(url) {
    try {
        return new URL(url).host;
    } catch (error) {
        return String(url || "unknown");
    }
}

function bundledConfig() {
    const url = (window.SUPABASE_URL || "").trim();
    const key = (window.SUPABASE_ANON_KEY || "").trim();

    if (!url || !key) return null;

    return { url, key, source: "bundled" };
}

async function fetchServerConfig() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);

    try {
        const response = await fetch(`${API_BASE}/api/config`, {
            signal: controller.signal,
            headers: { Accept: "application/json" },
        });

        if (!response.ok) return null;

        const data = await response.json();

        if (!data?.supabase_url || !data?.supabase_anon_key) return null;

        return {
            url: String(data.supabase_url).replace(/\/+$/, ""),
            key: String(data.supabase_anon_key),
            source: "server",
        };
    } catch (error) {
        return null;
    } finally {
        clearTimeout(timer);
    }
}

export async function resolveSupabaseConfig({ force = false } = {}) {
    if (resolved && !force) return resolved;

    const server = await fetchServerConfig();
    const bundled = bundledConfig();

    const chosen = server || bundled;

    if (!chosen) {
        throw new ConfigError(
            "JeffAI has no Supabase configuration. Set SUPABASE_URL and SUPABASE_KEY on the server, or fill in config.js."
        );
    }

    if (server && bundled && hostOf(server.url) !== hostOf(bundled.url)) {
        console.warn(
            `[JeffAI] Server Supabase project (${hostOf(server.url)}) differs from the bundled config (${hostOf(bundled.url)}). Using the server.`
        );
    }

    resolved = chosen;

    return chosen;
}

/**
 * Ask the Supabase auth service whether it exists and answers.
 * A dead or deleted project shows up as a DNS failure here, which is
 * what produced the unhelpful "Failed to fetch" report.
 */
export async function checkAuthService(url, key, timeout = 8000) {
    const host = hostOf(url);

    if (!url) return { reachable: false, host, detail: "No Supabase URL configured" };

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    try {
        const response = await fetch(`${url}/auth/v1/health`, {
            signal: controller.signal,
            headers: key ? { apikey: key } : {},
        });

        clearTimeout(timer);

        return {
            reachable: response.status < 500,
            host,
            status: response.status,
            detail: `HTTP ${response.status}`,
        };
    } catch (error) {
        clearTimeout(timer);

        return {
            reachable: false,
            host,
            detail: error?.name === "AbortError" ? "Request timed out" : String(error?.message || error),
        };
    }
}

export function isNetworkAuthError(error) {
    const text = String(error?.message || error || "").toLowerCase();

    return (
        text.includes("failed to fetch") ||
        text.includes("networkerror") ||
        text.includes("load failed") ||
        text.includes("fetch failed") ||
        text.includes("network request failed")
    );
}
