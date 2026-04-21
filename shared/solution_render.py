"""
Render full math/text solutions to fixed-size PNG pages for chat clients (Telegram, MAX, web).

Uses matplotlib Agg + mathtext for LaTeX-like fragments; plain lines use DejaVu Sans (Cyrillic OK).
"""

from __future__ import annotations

import io
import logging
import textwrap
from typing import Final

logger = logging.getLogger(__name__)

# Fixed page size (pixels at given DPI) — same for every page of a solution
PAGE_WIDTH_PX: Final[int] = 900
PAGE_HEIGHT_PX: Final[int] = 1200
DPI: Final[int] = 120
FIG_WIDTH_IN: Final[float] = PAGE_WIDTH_PX / DPI
FIG_HEIGHT_IN: Final[float] = PAGE_HEIGHT_PX / DPI

# Horizontal: fig.text() does not reflow; ~52 Latin chars at 11pt fits 900px with margins
TEXT_X: Final[float] = 0.08
# Vertical spacing in figure coordinates (transFigure)
LINE_STEP: Final[float] = 0.022
TOP_Y: Final[float] = 0.94
BOTTOM_Y: Final[float] = 0.06
FONT_SIZE: Final[int] = 11
# Cyrillic and mathtext symbols are wider than ASCII — keep conservative
MAX_WRAP: Final[int] = 52
MAX_CHARS: Final[int] = 48_000
# Long unbreakable mathtext lines: shrink font to reduce horizontal overflow
_LONG_LINE_SHRINK_AT: Final[int] = 72
_MIN_FONT: Final[int] = 7
# Padding around tight bbox (pixels) when cropping white margins
CROP_PAD_PX: Final[int] = 10


def _split_into_physical_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        s = raw.rstrip()
        if not s:
            lines.append("")
            continue
        if len(s) <= MAX_WRAP:
            lines.append(s)
            continue
        wrapped = textwrap.wrap(s, width=MAX_WRAP, replace_whitespace=False)
        lines.extend(wrapped or [s])
    return lines


def _paginate(lines: list[str], max_lines: int) -> list[list[str]]:
    pages: list[list[str]] = []
    cur: list[str] = []
    for ln in lines:
        if len(cur) >= max_lines and cur:
            pages.append(cur)
            cur = []
        cur.append(ln)
    if cur:
        pages.append(cur)
    return pages if pages else [[]]


def _line_looks_like_math(stripped: str) -> bool:
    return (stripped.startswith("$") and stripped.endswith("$") and len(stripped) > 2) or (
        "\\" in stripped and any(c in stripped for c in r"^_")
    )


def _fontsize_for_line(stripped: str, base: int) -> int:
    n = len(stripped)
    if n <= _LONG_LINE_SHRINK_AT:
        return base
    # Progressive shrink for long formula lines
    return max(_MIN_FONT, int(base * (1.0 - min(0.35, (n - _LONG_LINE_SHRINK_AT) * 0.003))))


def _draw_line(fig, line: str, y: float, fontsize: int) -> float:
    stripped = line.strip()
    if not stripped:
        return y - LINE_STEP * 0.6

    use_math = _line_looks_like_math(stripped)
    if use_math and not (stripped.startswith("$") and stripped.endswith("$")):
        text = f"${stripped}$"
    else:
        text = stripped if use_math else line

    fs = _fontsize_for_line(stripped, fontsize) if use_math else fontsize
    if not use_math and len(stripped) > _LONG_LINE_SHRINK_AT + 20:
        fs = _fontsize_for_line(stripped, fontsize)

    try:
        if use_math:
            fig.text(
                TEXT_X,
                y,
                text,
                fontsize=fs,
                ha="left",
                va="top",
                transform=fig.transFigure,
            )
        else:
            fig.text(
                TEXT_X,
                y,
                line,
                fontsize=fs,
                ha="left",
                va="top",
                transform=fig.transFigure,
                family="DejaVu Sans",
            )
    except Exception as e:
        logger.debug("mathtext fallback for line: %s", e)
        fig.text(
            TEXT_X,
            y,
            line,
            fontsize=fs,
            ha="left",
            va="top",
            transform=fig.transFigure,
            family="DejaVu Sans",
        )
    return y - LINE_STEP


def _render_one_page(lines: list[str]) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(FIG_WIDTH_IN, FIG_HEIGHT_IN), dpi=DPI, facecolor="white")
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.set_facecolor("white")

    max_lines = int((TOP_Y - BOTTOM_Y) / LINE_STEP)
    y = TOP_Y
    for ln in lines[:max_lines]:
        y = _draw_line(fig, ln, y, FONT_SIZE)
        if y < BOTTOM_Y:
            break

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=DPI,
        facecolor="white",
        edgecolor="none",
    )
    plt.close(fig)
    return _tight_crop_png(buf.getvalue())


def _tight_crop_png(png_bytes: bytes) -> bytes:
    """Remove uniform white borders (especially empty bottom) after render."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return png_bytes

    im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    diff = ImageChops.difference(im, bg)
    bbox = diff.getbbox()
    if not bbox:
        return png_bytes
    w, h = im.size
    x0, y0, x1, y1 = bbox
    p = CROP_PAD_PX
    x0, y0 = max(0, x0 - p), max(0, y0 - p)
    x1, y1 = min(w, x1 + p), min(h, y1 + p)
    if x1 <= x0 or y1 <= y0:
        return png_bytes
    out = im.crop((x0, y0, x1, y1))
    ob = io.BytesIO()
    out.save(ob, format="PNG", optimize=True)
    return ob.getvalue()


def render_solution_pages(content: str) -> list[bytes]:
    """
    Render solution text to one or more PNG pages.

    Renders to a full-height canvas, then **tight-crops** each image to the ink bbox (removes
    empty bottom/white borders). Output width/height in pixels is therefore often less than
    PAGE_WIDTH_PX / PAGE_HEIGHT_PX when content is short.
    """
    text = (content or "").strip()
    if not text:
        raise ValueError("Пустой текст решения")
    if len(text) > MAX_CHARS:
        raise ValueError(f"Слишком длинный текст (макс. {MAX_CHARS} символов)")

    physical = _split_into_physical_lines(text)
    max_lines = int((TOP_Y - BOTTOM_Y) / LINE_STEP)
    pages_lines = _paginate(physical, max_lines=max_lines)
    return [_render_one_page(pl) for pl in pages_lines if pl]
