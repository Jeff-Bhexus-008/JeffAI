"""
Shared Supabase helpers for JeffAI.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Auth is delegated to Supabase: the frontend holds the user session and
the backend forwards the bearer token, so every REST call below runs
under the user's own row level security.
"""

import os

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
