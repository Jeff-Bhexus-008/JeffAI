#!/usr/bin/env python3
"""
Generate every JeffAI raster asset from frontend/assets/logo.svg.

Created by Amedu Vincent Onjefu (Jeff Bhexus).

Run after editing the logo:

    python tools/make-icons.py

Outputs
  frontend/assets/*.png            favicon, apple touch icon, PWA icons
  android/.../mipmap-*/ic_launcher*.png
  android/.../drawable-*/splash.png

Requires: cairosvg, pillow (both in requirements.txt / requirements-dev.txt).
"""

import io
import pathlib
import sys

import cairosvg
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGO = ROOT / "frontend" / "assets" / "logo.svg"
WEB_ASSETS = ROOT / "frontend" / "assets"
RES = ROOT / "android" / "app" / "src" / "main" / "res"

BRAND_DARK = (6, 6, 11, 255)
BRAND_GLOW = (139, 92, 246)


def render_logo(size):
    png = cairosvg.svg2png(bytestring=LOGO.read_bytes(), output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def background(size, radius=0):
    """Brand background with a soft top-left violet glow."""
    canvas = Image.new("RGBA", (size, size), BRAND_DARK)
    glow = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(glow)
    draw.ellipse(
        [-size * 0.35, -size * 0.45, size * 0.85, size * 0.75],
        fill=90,
    )
    glow = glow.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(size / 6))
    tint = Image.new("RGBA", (size, size), BRAND_GLOW + (255,))
    canvas = Image.composite(tint, canvas, glow.point(lambda v: int(v * 0.45)))

    if radius:
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
        canvas.putalpha(mask)

    return canvas


def circular(image):
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, image.size[0] - 1, image.size[1] - 1], fill=255)
    out = image.copy()
    out.putalpha(mask)
    return out


def compose_tile(size, logo_fraction, radius_ratio=0.22, round_icon=False):
    tile = background(size, radius=0 if round_icon else int(size * radius_ratio))
    logo = render_logo(max(8, int(size * logo_fraction)))
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2
    tile.alpha_composite(logo, (x, y))
    return circular(tile) if round_icon else tile


def foreground(size):
    """Adaptive-icon foreground: transparent, brain inside the safe zone."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    logo = render_logo(int(size * 0.62))
    layer.alpha_composite(logo, ((size - logo.width) // 2, (size - logo.height) // 2))
    return layer


def splash(width, height):
    canvas = Image.new("RGBA", (width, height), BRAND_DARK)
    glow = Image.new("L", (width, height), 0)
    ImageDraw.Draw(glow).ellipse(
        [width * 0.5 - height * 0.5, height * 0.1, width * 0.5 + height * 0.5, height * 0.95],
        fill=255,
    )
    from PIL import ImageFilter

    glow = glow.filter(ImageFilter.GaussianBlur(max(12, height / 12)))
    tint = Image.new("RGBA", (width, height), BRAND_GLOW + (255,))
    canvas = Image.composite(tint, canvas, glow.point(lambda v: int(v * 0.22)))

    mark = render_logo(int(min(width, height) * 0.34))
    canvas.alpha_composite(mark, ((width - mark.width) // 2, (height - mark.height) // 2 - int(height * 0.02)))

    return canvas.convert("RGB")


DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}

SPLASHES = {
    "drawable-port-mdpi": (320, 480),
    "drawable-port-hdpi": (480, 800),
    "drawable-port-xhdpi": (720, 1280),
    "drawable-port-xxhdpi": (960, 1600),
    "drawable-port-xxxhdpi": (1280, 1920),
    "drawable-land-mdpi": (480, 320),
    "drawable-land-hdpi": (800, 480),
    "drawable-land-xhdpi": (1280, 720),
    "drawable-land-xxhdpi": (1600, 960),
    "drawable-land-xxxhdpi": (1920, 1280),
}

written = []


def save(image, path, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = image.convert(mode) if mode else image
    out.save(path)
    written.append((path.relative_to(ROOT), path.stat().st_size))


def main():
    if not LOGO.exists():
        sys.exit(f"missing {LOGO}")

    save(render_logo(512), WEB_ASSETS / "logo.png")
    save(compose_tile(32, 0.78, 0.24), WEB_ASSETS / "favicon-32.png")
    save(compose_tile(48, 0.78, 0.24), WEB_ASSETS / "favicon-48.png")
    save(compose_tile(180, 0.70, 0.0), WEB_ASSETS / "apple-touch-icon.png")
    save(compose_tile(192, 0.62, 0.0), WEB_ASSETS / "icon-192.png")
    save(compose_tile(512, 0.62, 0.0), WEB_ASSETS / "icon-512.png")

    for name, scale in DENSITIES.items():
        base = int(48 * scale)
        save(compose_tile(base, 0.70, 0.22), RES / f"mipmap-{name}" / "ic_launcher.png")
        save(compose_tile(base, 0.70, round_icon=True), RES / f"mipmap-{name}" / "ic_launcher_round.png")
        save(foreground(int(108 * scale)), RES / f"mipmap-{name}" / "ic_launcher_foreground.png")

    for folder, size in SPLASHES.items():
        save(splash(*size), RES / folder / "splash.png")

    for path, size in written:
        print(f"  {str(path):70s} {size:>8,} bytes")

    print(f"\n{len(written)} assets written")


if __name__ == "__main__":
    main()
