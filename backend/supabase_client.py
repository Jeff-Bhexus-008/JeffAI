"""
Shared Supabase helpers for JeffAI.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Auth is delegated to Supabase: the frontend holds the user session and
the backend forwards the bearer token, so every REST call below runs
under the user's own row level security.
"""

import os
import time
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import request
import requests


load_dotenv()


TIMEOUT = 20


def supabase_url():
    return (os.getenv("SUPABASE_URL") or "").rstrip("/")


def supabase_key():
    return os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or ""


def supabase_ready():
    return bool(supabase_url() and supabase_key())


def supabase_host():
    """Hostname only - safe to show in health output and logs."""
    try:
        return urlparse(supabase_url()).hostname or ""
    except Exception:
        return ""


_AUTH_HEALTH = {"at": 0.0, "value": None}


def auth_service_health(force=False, ttl=60):
    """
    Is the configured Supabase auth host actually alive?

    Configured credentials are not the same thing as a working project:
    a deleted or paused project keeps its URL in config and then fails
    every browser request with "Failed to fetch". This probe makes that
    visible without exposing any secret.
    """

    now = time.time()

    if not force and _AUTH_HEALTH["value"] and (now - _AUTH_HEALTH["at"]) < ttl:
        return dict(_AUTH_HEALTH["value"])

    result = {
        "reachable": False,
        "configured": supabase_ready(),
        "host": supabase_host(),
        "detail": "",
    }

    if not supabase_ready():
        result["detail"] = "SUPABASE_URL or SUPABASE_KEY is not set"
    else:
        try:
            response = requests.get(
                f"{supabase_url()}/auth/v1/health",
                headers={"apikey": supabase_key()},
                timeout=6,
            )

            # Supabase's GoTrue health endpoint is public and answers 200
            # with {"name": "GoTrue"}. Anything else means the project is
            # paused, moved, or not an auth service we can sign in to.
            healthy = response.status_code == 200

            if healthy:
                try:
                    healthy = str(response.json().get("name", "")).lower() == "gotrue"
                except Exception:
                    healthy = True

            result["reachable"] = healthy
            result["status"] = response.status_code
            result["detail"] = f"HTTP {response.status_code}"

        except Exception as error:
            result["detail"] = f"{type(error).__name__}: {str(error)[:140]}"

    _AUTH_HEALTH["at"] = now
    _AUTH_HEALTH["value"] = dict(result)

    return result


def public_client_config():
    """
    The Supabase project the browser must use.

    The URL and the anon key are public by design (they ship in the
    served frontend and are protected by row level security), but the
    service-role key never leaves the server.
    """

    return {
        "supabase_url": supabase_url(),
        "supabase_anon_key": supabase_key(),
        "configured": supabase_ready(),
    }


def rest(table):
    return f"{supabase_url()}/rest/v1/{table}"


# =========================================================
# AUTH
# =========================================================

def get_token():

    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.replace("Bearer ", "", 1).strip()

    return token or None


def get_user():

    token = get_token()

    if not token or not supabase_ready():
        return None

    try:

        response = requests.get(
            f"{supabase_url()}/auth/v1/user",
            headers={
                "apikey": supabase_key(),
                "Authorization": f"Bearer {token}",
            },
            timeout=TIMEOUT,
        )

        if response.status_code != 200:
            return None

        data = response.json()

        return data if data.get("id") else None

    except Exception as error:

        print("[JeffAI] auth check failed:", error)

        return None


def supabase_headers(token, prefer=None):

    headers = {
        "apikey": supabase_key(),
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": prefer or "return=representation",
    }

    return headers


def signed_storage_url(path, expires=3600):

    if not path:
        return None

    try:

        response = requests.post(
            f"{supabase_url()}/storage/v1/object/sign/documents/{path}",
            headers={
                "apikey": supabase_key(),
                "Authorization": f"Bearer {supabase_key()}",
                "Content-Type": "application/json",
            },
            json={"expiresIn": expires},
            timeout=TIMEOUT,
        )

        if response.status_code >= 400:
            return None

        signed = response.json().get("signedURL")

        if not signed:
            return None

        if signed.startswith("http"):
            return signed

        return f"{supabase_url()}/storage/v1{signed}"

    except Exception:

        return None
