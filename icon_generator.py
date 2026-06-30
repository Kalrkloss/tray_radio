import os
import io
import logging
from typing import Optional

from PIL import Image, ImageDraw
import requests

logger = logging.getLogger(__name__)


def create_tray_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 2

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 120, 220, 255))
    draw.ellipse([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4], fill=(50, 160, 240, 255))
    draw.arc([cx - 6, cy - 3, cx + 2, cy + 3], 180, 360, fill=(255, 255, 255, 220), width=2)
    draw.arc([cx - 2, cy - 6, cx + 6, cy], 270, 90, fill=(255, 255, 255, 220), width=2)

    return img


def create_stopped_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 2

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(100, 100, 100, 255))
    draw.ellipse([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4], fill=(140, 140, 140, 255))

    sq = size // 6
    draw.rectangle([cx - sq, cy - sq, cx + sq, cy + sq], fill=(60, 60, 60, 200))

    return img


def create_playing_icon(size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 2

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(30, 180, 80, 255))
    draw.ellipse([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4], fill=(50, 220, 100, 255))

    bar_w = size // 8
    bar_gap = bar_w + 1
    for i, h in enumerate([12, 18, 8, 16]):
        bx = cx - bar_gap * 2 + i * bar_gap
        draw.rectangle([bx, cy + 8 - h, bx + bar_w, cy + 8], fill=(255, 255, 255, 200))

    return img


LOGO_CACHE_DIR = None


def get_logo_cache_dir():
    global LOGO_CACHE_DIR
    if LOGO_CACHE_DIR is None:
        LOGO_CACHE_DIR = os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "tray_radio",
            "logo_cache",
        )
        os.makedirs(LOGO_CACHE_DIR, exist_ok=True)
    return LOGO_CACHE_DIR


def fetch_logo(url: str) -> Optional[Image.Image]:
    if not url:
        return None
    cache_dir = get_logo_cache_dir()
    cache_key = url.replace("://", "_").replace("/", "_").replace("?", "_")[:100]
    cache_path = os.path.join(cache_dir, f"{cache_key}.png")

    if os.path.exists(cache_path):
        try:
            return Image.open(cache_path)
        except Exception:
            pass

    try:
        resp = requests.get(url, timeout=5)
        if resp.ok:
            img = Image.open(io.BytesIO(resp.content))
            img = img.convert("RGBA")
            img.save(cache_path, "PNG")
            return img
    except Exception as e:
        logger.debug(f"Failed to fetch logo {url}: {e}")
    return None
