"""Resize and encode user images for vision API (limits size / tokens)."""

from __future__ import annotations

import base64
import io
import logging

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIDE = 2048


def image_to_data_url_jpeg(data: bytes, max_side: int = DEFAULT_MAX_SIDE) -> str:
    """
    Downscale if needed, re-encode as JPEG, return data URL for OpenRouter image_url.
    """
    try:
        from PIL import Image
    except ImportError:
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    try:
        im = Image.open(io.BytesIO(data))
        im = im.convert("RGB")
        w, h = im.size
        if max(w, h) > max_side:
            im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85, optimize=True)
        out = buf.getvalue()
    except Exception as e:
        logger.warning("PIL image prep failed, sending raw: %s", e)
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    b64 = base64.b64encode(out).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
