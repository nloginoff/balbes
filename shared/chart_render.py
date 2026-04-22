"""Deterministic matplotlib (Agg) charts from a JSON-like spec — no LLM, no shell."""

from __future__ import annotations

import io
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

MAX_POINTS_PER_SERIES = 8_000
MAX_SERIES = 12
MAX_BINS = 200
FIG_W, FIG_H = 9.0, 6.0
DPI = 120


class ChartRenderError(ValueError):
    pass


def _finite_list(name: str, raw: Any, max_n: int) -> list[float]:
    if not isinstance(raw, list):
        raise ChartRenderError(f"{name} must be a list")
    if len(raw) > max_n:
        raise ChartRenderError(f"{name}: at most {max_n} points")
    out: list[float] = []
    for i, v in enumerate(raw):
        try:
            x = float(v)
        except (TypeError, ValueError) as e:
            raise ChartRenderError(f"{name}[{i}] is not a number") from e
        if not math.isfinite(x):
            raise ChartRenderError(f"{name}[{i}] is not finite")
        out.append(x)
    return out


def render_chart_png(spec: dict[str, Any]) -> bytes:
    """
    Build a PNG from `spec`.

    kind:
      - line | scatter: series: [{ "label": str, "x": [...], "y": [...] }]
      - bar: categories: [...], values: [...] OR series: [{ "label", "values" }] with len = len(categories)
      - histogram: values: [...], optional bins (int)
    Optional: title, xlabel, ylabel, grid (bool).
    """
    if not isinstance(spec, dict):
        raise ChartRenderError("spec must be an object")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    kind = (spec.get("kind") or "line").strip().lower()
    title = (spec.get("title") or "").strip()
    xlabel = (spec.get("xlabel") or "").strip()
    ylabel = (spec.get("ylabel") or "").strip()
    grid = bool(spec.get("grid", True))

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI, facecolor="white")
    ax.set_facecolor("white")

    if kind in ("line", "scatter"):
        series = spec.get("series")
        if not isinstance(series, list) or not series:
            raise ChartRenderError("kind line/scatter requires non-empty series array")
        if len(series) > MAX_SERIES:
            raise ChartRenderError(f"at most {MAX_SERIES} series")
        for si, s in enumerate(series):
            if not isinstance(s, dict):
                raise ChartRenderError(f"series[{si}] must be an object")
            lab = str(s.get("label") or f"S{si + 1}")
            xs = _finite_list(f"series[{si}].x", s.get("x"), MAX_POINTS_PER_SERIES)
            ys = _finite_list(f"series[{si}].y", s.get("y"), MAX_POINTS_PER_SERIES)
            if len(xs) != len(ys):
                raise ChartRenderError(f"series[{si}]: x and y length mismatch")
            if kind == "line":
                ax.plot(xs, ys, label=lab, linewidth=2)
            else:
                ax.scatter(xs, ys, label=lab, s=36)
        if len(series) > 1 or (series and str(series[0].get("label") or "").strip()):
            ax.legend(loc="best", fontsize=9)

    elif kind == "bar":
        categories = spec.get("categories")
        if isinstance(spec.get("series"), list) and spec["series"]:
            series_list = spec["series"]
            if len(series_list) > MAX_SERIES:
                raise ChartRenderError(f"at most {MAX_SERIES} bar series")
            if not categories or not isinstance(categories, list):
                raise ChartRenderError("bar with series[] requires categories[]")
            cats = [str(c) for c in categories]
            n = len(cats)
            m = len(series_list)
            x_base = list(range(n))
            bar_w = 0.8 / max(m, 1)
            for si, s in enumerate(series_list):
                if not isinstance(s, dict):
                    raise ChartRenderError(f"series[{si}] must be an object")
                vals = s.get("values")
                v = _finite_list(f"series[{si}].values", vals, MAX_POINTS_PER_SERIES)
                if len(v) != n:
                    raise ChartRenderError(
                        f"series[{si}].values length must match categories ({n})"
                    )
                lab = str(s.get("label") or f"S{si + 1}")
                offset = (si - (m - 1) / 2) * bar_w
                xpos = [xb + offset for xb in x_base]
                ax.bar(xpos, v, width=bar_w * 0.92, label=lab)
            ax.set_xticks(x_base)
            ax.set_xticklabels(cats, rotation=20, ha="right")
            ax.legend(loc="best", fontsize=9)
        else:
            if not categories or not isinstance(categories, list):
                raise ChartRenderError("bar requires categories[] or series[]+categories")
            vals = _finite_list("values", spec.get("values"), MAX_POINTS_PER_SERIES)
            cats = [str(c) for c in categories]
            if len(cats) != len(vals):
                raise ChartRenderError("categories and values must have the same length")
            xpos = range(len(cats))
            ax.bar(xpos, vals, color="steelblue", width=0.65)
            ax.set_xticks(list(xpos))
            ax.set_xticklabels(cats, rotation=20, ha="right")

    elif kind == "histogram":
        vals = _finite_list("values", spec.get("values"), MAX_POINTS_PER_SERIES * 2)
        bins = spec.get("bins", 20)
        try:
            bi = int(bins)
        except (TypeError, ValueError) as e:
            raise ChartRenderError("bins must be an integer") from e
        if bi < 1 or bi > MAX_BINS:
            raise ChartRenderError(f"bins must be between 1 and {MAX_BINS}")
        ax.hist(vals, bins=bi, color="steelblue", edgecolor="white", linewidth=0.5)

    else:
        raise ChartRenderError(f"unknown kind: {kind!r} (use line, scatter, bar, histogram)")

    if title:
        ax.set_title(title, fontsize=12)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)
    if grid:
        ax.grid(True, alpha=0.35, linestyle="--")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    data = buf.getvalue()
    if len(data) < 100:
        raise ChartRenderError("rendered image is too small")
    return data
