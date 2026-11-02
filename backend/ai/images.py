"""
JeffAI image studio backend.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Image generation runs through a keyless diffusion endpoint so the
feature works without buying a new API key, and generated images are
copied into Supabase storage when that is available so they can appear
under Saved files.
"""

import base64
import urllib.parse
import uuid

import requests

from backend.ai.engine import AIUnavailable


POLLINATIONS_ENDPOINT = "https://image.pollinations.ai/prompt"

POLLINATIONS_MODELS = ["flux", "turbo"]


ASPECTS = {
    "square": (1024, 1024),
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "wide": (1536, 864),
}


STYLE_HINTS = {
    "auto": "",
    "cinematic": (
        "cinematic photography, dramatic lighting, shallow depth of "
        "field, film grain, high detail"
    ),
    "digital": (
        "polished digital illustration, clean shapes, rich gradients, "
        "soft rim light"
    ),
    "photo": (
        "photorealistic, natural lighting, 50mm lens, sharp focus, "
        "realistic materials"
    ),
    "3d": (
        "modern 3D render, soft studio lighting, subtle reflections, "
        "octane style"
    ),
    "anime": (
        "anime key visual, clean line art, vivid colours, detailed "
        "background"
    ),
    "minimal": (
        "minimalist design, flat shapes, generous negative space, "
        "limited palette"
    ),
    "product": (
        "premium product shot, seamless backdrop, softbox lighting, "
        "commercial advertising quality"
    ),
}


NEGATIVE_HINT = (
    "no watermark, no text overlay, no logo, no signature, no deformed "
    "anatomy, no extra limbs"
)


def build_image_prompt(prompt, style="auto", quality=True):

    prompt = (prompt or "").strip()

    if not prompt:
        raise ValueError("Please describe the image you want.")

    parts = [prompt]

    hint = STYLE_HINTS.get(style or "auto", "")

    if hint:
        parts.append(hint)

    if quality:
        parts.append(
            "high detail, professional composition, beautiful lighting"
        )

    parts.append(NEGATIVE_HINT)

    return ", ".join(parts)


def generate_image(prompt, style="auto", aspect="square", seed=None):
    """Return (image_bytes, mime, meta)."""

    width, height = ASPECTS.get(aspect, ASPECTS["square"])

    final_prompt = build_image_prompt(prompt, style)

    encoded = urllib.parse.quote(final_prompt, safe="")

    last_error = None

    for model in POLLINATIONS_MODELS:

        params = {
            "width": width,
            "height": height,
            "model": model,
            "nologo": "true",
            "enhance": "true",
        }

        if seed is not None:
            params["seed"] = seed

        url = f"{POLLINATIONS_ENDPOINT}/{encoded}"

        try:

            response = requests.get(
                url,
                params=params,
                timeout=120,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"provider returned {response.status_code}"
                )

            content_type = response.headers.get("content-type", "")

            if not content_type.startswith("image/"):
                raise RuntimeError(
                    f"unexpected content type: {content_type}"
                )

            if len(response.content) < 1024:
                raise RuntimeError("image payload too small")

            return response.content, content_type, {
                "provider": f"pollinations:{model}",
                "width": width,
                "height": height,
                "prompt": final_prompt,
            }

        except Exception as error:

            last_error = error

            print(f"[JeffAI] image generation ({model}) failed: {error}")

    raise AIUnavailable(
        "Image generation is unavailable right now. "
        f"({last_error})"
    )


def data_url(image_bytes, mime="image/png"):

    encoded = base64.b64encode(image_bytes).decode("ascii")

    return f"data:{mime};base64,{encoded}"


def save_image(token, user_id, image_bytes, extension="png", prompt=""):

    """Store the image in Supabase storage and return its record."""

    from backend.supabase_client import supabase_key, supabase_url

    if not supabase_url() or not supabase_key():
        return None

    path = f"images/{user_id}/{uuid.uuid4().hex}.{extension}"

    try:

        upload = requests.post(
            f"{supabase_url()}/storage/v1/object/documents/{path}",
            headers={
                "apikey": supabase_key(),
                "Authorization": f"Bearer {token}",
                "Content-Type": f"image/{extension}",
                "x-upsert": "true",
            },
            data=image_bytes,
            timeout=60,
        )

        if upload.status_code >= 400:
            print("[JeffAI] image upload failed:", upload.text[:200])
            return None

        record = requests.post(
            f"{supabase_url()}/rest/v1/images",
            headers={
                "apikey": supabase_key(),
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json={
                "user_id": user_id,
                "prompt": prompt,
                "file_path": path,
                "file_type": extension,
            },
            timeout=20,
        )

        if record.status_code >= 400:
            print("[JeffAI] image record failed:", record.text[:200])
            return None

        rows = record.json()

        return rows[0] if rows else None

    except Exception as error:

        print("[JeffAI] image save error:", error)

        return None
