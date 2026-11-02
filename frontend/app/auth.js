/* =========================================================
   JeffAI auth page controller
   Created by Amedu Vincent Onjefu (Jeff Bhexus)

   Shared by login.html and signup.html. Resolves the Supabase
   project (backend first, bundled config second), verifies the auth
   service is actually reachable, and turns network failures into a
   message that names the real problem instead of "Failed to fetch".
   ========================================================= */

import {
    ConfigError,
    API_BASE,
    checkAuthService,
    isNetworkAuthError,
    resolveSupabaseConfig,
} from "./env.js";

const ERRORS = {
    credentials: "That email and password do not match. Please try again.",
    exists: "An account already exists for that email. Try signing in instead.",
    rate: "Too many attempts. Wait a minute and try again.",
};

export function mountAuthPage({ mode = "login" } = {}) {
    const form = document.getElementById("authForm");
    const email = document.getElementById("email");
    const password = document.getElementById("password");
    const confirm = document.getElementById("confirm");
    const message = document.getElementById("message");
    const submit = document.getElementById("submitButton");
    const reveal = document.getElementById("revealPassword");
    const retry = document.getElementById("retry");
    const serviceLine = document.getElementById("serviceLine");

    if (!form) return;

    const isSignup = mode === "signup";
    const idleLabel = isSignup ? "Create account" : "Sign in";

    let client = null;
    let config = null;

    function setMessage(text, type = "") {
        if (!message) return;
        message.textContent = text || "";
        message.className = "message" + (type ? " " + type : "");
    }

    function setBusy(busy, label) {
        submit.disabled = busy;
        submit.innerHTML = busy
            ? `<span class="spinner"></span> ${label}`
            : idleLabel;
    }

    function showRetry(visible) {
        if (retry) retry.hidden = !visible;
    }

    function setServiceLine(text, state = "") {
        if (!serviceLine) return;
        serviceLine.textContent = text;
        serviceLine.className = "service-line" + (state ? " " + state : "");
    }

    async function connect({ force = false } = {}) {
        config = await resolveSupabaseConfig({ force });

        client = window.supabase.createClient(config.url, config.key);

        return config;
    }

    /**
     * Verify the auth host before blaming the user's password.
     */
    async function diagnose() {
        if (!config) return false;

        const health = await checkAuthService(config.url, config.key);

        if (health.reachable) {
            setServiceLine(`Sign-in service: ${health.host} · ${health.detail}`, "ok");
            return true;
        }

        setServiceLine(`Sign-in service unreachable: ${health.host} · ${health.detail}`, "bad");

        // Keep the raw browser wording in the console and the technical
        // line above; the sentence a person reads should be plain.
        const humanDetail = isNetworkAuthError(health.detail)
            ? "The address does not resolve, so the connection never reached a server"
            : health.detail;

        setMessage(
            `JeffAI cannot reach its sign-in service (${health.host}). ${humanDetail}. ` +
                "The configured Supabase project is wrong, paused or deleted, so no password can work until it is fixed. " +
                "This is a project configuration problem, not your credentials.",
            "error"
        );

        showRetry(true);

        console.error("[JeffAI] Supabase auth service unreachable", {
            host: health.host,
            detail: health.detail,
            source: config.source,
            api: `${API_BASE}/api/config`,
        });

        return false;
    }

    function friendly(error) {
        const text = String(error?.message || error || "");
        const code = String(error?.code || "").toLowerCase();

        if (isNetworkAuthError(text) || /429|50\d/.test(code)) {
            return null;
        }

        if (/invalid login credentials/i.test(text)) return ERRORS.credentials;
        if (/already registered|already exists|user already/i.test(text)) return ERRORS.exists;
        if (/email not confirmed/i.test(text)) {
            return "This account still needs email confirmation. Check your inbox, then sign in.";
        }
        if (/rate limit|too many/i.test(text)) return ERRORS.rate;

        return text || "Something went wrong. Please try again.";
    }

    reveal?.addEventListener("click", () => {
        const showing = password.type === "text";
        password.type = showing ? "password" : "text";
        reveal.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    });

    retry?.addEventListener("click", async () => {
        showRetry(false);
        setMessage("Checking the sign-in service again…");

        try {
            await connect({ force: true });
            if (await diagnose()) {
                setMessage("Sign-in service is reachable again. You can sign in now.", "success");
            }
        } catch (error) {
            setMessage(
                error instanceof ConfigError
                    ? error.message
                    : "Still cannot reach the sign-in service. Check SUPABASE_URL on the server.",
                "error"
            );
            showRetry(true);
        }
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const emailValue = email.value.trim();
        const passwordValue = password.value;

        if (!emailValue || !passwordValue) {
            setMessage("Enter your email and password to continue.", "error");
            return;
        }

        if (isSignup) {
            if (passwordValue.length < 6) {
                setMessage("Use at least 6 characters for your password.", "error");
                return;
            }

            if (confirm && passwordValue !== confirm.value) {
                setMessage("Those passwords do not match.", "error");
                return;
            }
        }

        setBusy(true, isSignup ? "Creating account" : "Signing in");
        setMessage("");

        try {
            await connect();

            if (!(await diagnose())) {
                setBusy(false);
                return;
            }

            if (isSignup) {
                const { data, error } = await client.auth.signUp({
                    email: emailValue,
                    password: passwordValue,
                });

                if (error) {
                    const text = friendly(error);

                    setBusy(false);

                    if (text === null) {
                        await diagnose();
                        return;
                    }

                    setMessage(text, "error");
                    return;
                }

                if (!data.session) {
                    setBusy(false);
                    setMessage(
                        "Account created. Check your email to confirm it, then sign in.",
                        "success"
                    );
                    return;
                }

                setMessage("Account created. Opening JeffAI…", "success");
                window.location.href = "/";
                return;
            }

            const { error } = await client.auth.signInWithPassword({
                email: emailValue,
                password: passwordValue,
            });

            if (error) {
                const text = friendly(error);

                setBusy(false);

                if (text === null) {
                    await diagnose();
                    return;
                }

                setMessage(text, "error");
                return;
            }

            setMessage("Signed in. Opening JeffAI…", "success");
            window.location.href = "/";
        } catch (error) {
            setBusy(false);

            if (error instanceof ConfigError) {
                setMessage(error.message, "error");
                showRetry(true);
                return;
            }

            if (isNetworkAuthError(error)) {
                await diagnose();
                return;
            }

            setMessage(String(error?.message || error), "error");
        }
    });

    /* Boot: resolve config, bounce signed-in users, report the host. */

    (async () => {
        try {
            await connect();

            const { data } = await client.auth.getSession();

            if (data?.session) {
                window.location.href = "/";
                return;
            }

            await diagnose();
        } catch (error) {
            setMessage(
                error instanceof ConfigError
                    ? error.message
                    : "JeffAI could not load its configuration. Check that the backend is running.",
                "error"
            );
            showRetry(true);
        }
    })();
}
