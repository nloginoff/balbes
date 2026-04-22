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
MAX_CHART_LABELED_POINTS = 32
MAX_MAJOR_TICKS_PER_AXIS = 40
FIG_W, FIG_H = 9.0, 6.0
DPI = 120

# Whitelist for flat tool args merged into spec (registry)
CHART_SPEC_KEYS = frozenset(
    {
        "kind",
        "title",
        "xlabel",
        "ylabel",
        "grid",
        "series",
        "categories",
        "values",
        "bins",
        "style",
        "axes_origin",
        "grid_step",
        "points",
    }
)


class ChartRenderError(ValueError):
    pass


def _school_coordinate_style(spec: dict[str, Any]) -> bool:
    st = spec.get("style")
    if isinstance(st, str) and st.strip().lower() == "school":
        return True
    return spec.get("axes_origin") is True


def _ensure_axis_includes_zero(ax: Any, axis: str) -> None:
    """Expand xlim/ylim so 0 is visible (with small padding)."""
    get_lim = ax.get_xlim if axis == "x" else ax.get_ylim
    set_lim = ax.set_xlim if axis == "x" else ax.set_ylim
    lo, hi = get_lim()
    if lo > hi:
        lo, hi = hi, lo
    span = max(hi - lo, 1e-9)
    pad = 0.06 * span
    new_lo = min(lo, 0.0) - pad * 0.3
    new_hi = max(hi, 0.0) + pad * 0.3
    set_lim(new_lo, new_hi)


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


def _parse_positive_float(name: str, raw: Any, default: float) -> float:
    if raw is None:
        return default
    try:
        v = float(raw)
    except (TypeError, ValueError) as e:
        raise ChartRenderError(f"{name} must be a positive number") from e
    if not math.isfinite(v) or v <= 0:
        raise ChartRenderError(f"{name} must be a positive finite number")
    return v


def _set_ax_limits_from_labeled_points(ax: Any, spec: dict[str, Any]) -> None:
    """When there is no series, expand limits from `points` only (with margin)."""
    raw = spec.get("points")
    if not isinstance(raw, list) or not raw:
        return
    xs: list[float] = []
    ys: list[float] = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        try:
            xs.append(float(p.get("x")))
            ys.append(float(p.get("y")))
        except (TypeError, ValueError):
            continue
    if not xs:
        return
    pad_x = 0.08 * (max(xs) - min(xs) + 1e-9)
    pad_y = 0.08 * (max(ys) - min(ys) + 1e-9)
    ax.set_xlim(min(xs) - pad_x, max(xs) + pad_x)
    ax.set_ylim(min(ys) - pad_y, max(ys) + pad_y)


# Line through vertical asymptote (e.g. 1/x with x spanning 0 in one series): huge slope vs a straight line
_LINE_ASYMPTOTE_SLOPE_CAP = 400.0


def _break_line_at_vertical_asymptote_guess(
    xs: list[float], ys: list[float]
) -> tuple[list[float], list[float]]:
    """
    Insert NaN to split plot() so matplotlib does not draw a segment through x=0 when y jumps
    (hyperbola with poorly ordered / wide samples). Lines with moderate slope (g(x)) are kept.
    """
    if len(xs) < 2:
        return list(xs), list(ys)
    out_x: list[float] = [xs[0]]
    out_y: list[float] = [ys[0]]
    for j in range(len(xs) - 1):
        x0, x1 = xs[j], xs[j + 1]
        y0, y1 = ys[j], ys[j + 1]
        dx = x1 - x0
        if x0 * x1 < 0 and abs(dx) > 1e-15:
            dy = y1 - y0
            slope = abs(dy / dx)
            if slope > _LINE_ASYMPTOTE_SLOPE_CAP:
                out_x.append(float("nan"))
                out_y.append(float("nan"))
        out_x.append(x1)
        out_y.append(y1)
    return out_x, out_y


def _coerce_axis_step(span: float, base_step: float) -> float:
    """Pick a major tick step >= base_step so the axis has at most MAX_MAJOR_TICKS_PER_AXIS ticks."""
    span = max(abs(span), 1e-9)
    step = max(base_step, 1e-9)
    while span / step > MAX_MAJOR_TICKS_PER_AXIS + 1e-6:
        if step < 1.5:
            step = 2.0
        elif step < 3.5:
            step = 5.0
        elif step < 7.5:
            step = 10.0
        else:
            step *= 2.0
    return step


def _apply_school_grid_and_ticks(ax: Any, spec: dict[str, Any]) -> None:
    """
    After limits are set from data (and zero included), force major ticks on a fixed step
    so the grid matches 'школьная' unit cells instead of matplotlib AutoLocator (2, 5, ...).
    """
    from matplotlib.ticker import MultipleLocator, NullLocator

    base = _parse_positive_float("grid_step", spec.get("grid_step"), 1.0)

    xlo, xhi = ax.get_xlim()
    if xlo > xhi:
        xlo, xhi = xhi, xlo
    ylo, yhi = ax.get_ylim()
    if ylo > yhi:
        ylo, yhi = yhi, ylo

    xstep = _coerce_axis_step(xhi - xlo, base)
    ystep = _coerce_axis_step(yhi - ylo, base)

    ax.xaxis.set_major_locator(MultipleLocator(xstep))
    ax.yaxis.set_major_locator(MultipleLocator(ystep))

    # Finer minor grid inside each major cell when major step is 1
    if abs(xstep - 1.0) < 1e-6:
        ax.xaxis.set_minor_locator(MultipleLocator(0.2))
    else:
        ax.xaxis.set_minor_locator(NullLocator())

    if abs(ystep - 1.0) < 1e-6:
        ax.yaxis.set_minor_locator(MultipleLocator(0.2))
    else:
        ax.yaxis.set_minor_locator(NullLocator())

    ax.grid(True, which="major", alpha=0.35, linestyle="--", linewidth=0.7, zorder=0)
    ax.grid(
        True,
        which="minor",
        alpha=0.15,
        linestyle=":",
        linewidth=0.45,
        zorder=0,
    )
    ax.tick_params(axis="both", which="major", labelsize=8)


def _draw_labeled_points(ax: Any, spec: dict[str, Any]) -> None:
    """Markers + text for intersections, vertices — not line segments between two coords."""
    raw = spec.get("points")
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ChartRenderError("points must be a list")
    if len(raw) > MAX_CHART_LABELED_POINTS:
        raise ChartRenderError(f"points: at most {MAX_CHART_LABELED_POINTS} items")

    import matplotlib.pyplot as plt

    cmap = plt.get_cmap("tab10")
    colors = [cmap(i % 10) for i in range(10)]

    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            raise ChartRenderError(f"points[{i}] must be an object")
        try:
            px = float(p.get("x"))
            py = float(p.get("y"))
        except (TypeError, ValueError) as e:
            raise ChartRenderError(f"points[{i}].x and .y must be numbers") from e
        if not math.isfinite(px) or not math.isfinite(py):
            raise ChartRenderError(f"points[{i}]: coordinates must be finite")
        col = p.get("color")
        if isinstance(col, str) and col.strip():
            mcol: str | None = col.strip()
        else:
            mcol = colors[i % len(colors)]
        lab = p.get("label")
        label = str(lab).strip() if lab is not None else ""
        ax.plot(
            [px],
            [py],
            marker="o",
            ms=7,
            mew=1.0,
            mec="#333333",
            color=mcol,
            linestyle="None",
            zorder=4,
            clip_on=True,
        )
        if label:
            ax.annotate(
                label,
                (px, py),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=8,
                zorder=4,
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "#cccccc", "alpha": 0.92},
            )


def render_chart_png(spec: dict[str, Any]) -> bytes:
    """
    Build a PNG from `spec`.

    kind:
      - line | scatter: series: [{ "label": str, "x": [...], "y": [...] }]
      - bar: categories: [...], values: [...] OR series: [{ "label", "values" }] with len = len(categories)
      - histogram: values: [...], optional bins (int)
    Optional: title, xlabel, ylabel, grid (bool).
    School style (line/scatter): **style: "school"** or **axes_origin: true** — axes through 0, major
    grid with step **grid_step** (default 1). Intersections/vertices: use **points** (markers), not
    a two-point **series** (that draws a segment). For smooth curves, use many samples in x/y; split
    branches (e.g. hyperbola) into separate **series** (or the renderer may cut spurious near-vertical
    segments across the y-axis). **points**-only: markers + grid (no `series` yet) is allowed.
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
    school = _school_coordinate_style(spec) and kind in ("line", "scatter")

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI, facecolor="white")
    ax.set_facecolor("white")
    # Line/scatter + school: grid and series z-order so data stays above grid/axes
    line_scatter_school = False

    if kind in ("line", "scatter"):
        series = spec.get("series")
        points_raw = spec.get("points")
        has_points = isinstance(points_raw, list) and len(points_raw) > 0
        has_series = isinstance(series, list) and len(series) > 0

        if not has_series and not has_points:
            raise ChartRenderError(
                "kind line/scatter needs at least one of: non-empty **series** "
                "[{ label, x, y }, …] (curves) or **points** [{ x, y, label? }…] (markers). "
                "For 1/x use **two** series (x<0 and x>0) or one series per branch so x does not "
                "increase through 0, or the renderer splits steep bridges across y-axis automatically."
            )

        if not has_series and has_points:
            # Markers + grid only (LLM often calls with points before filling series; avoids error loops)
            if school:
                line_scatter_school = True
            _set_ax_limits_from_labeled_points(ax, spec)
            if school:
                _ensure_axis_includes_zero(ax, "x")
                _ensure_axis_includes_zero(ax, "y")
                ax.axhline(0, color="#333333", linewidth=1.0, zorder=2)
                ax.axvline(0, color="#333333", linewidth=1.0, zorder=2)
                _apply_school_grid_and_ticks(ax, spec)
            _draw_labeled_points(ax, spec)
        else:
            if len(series) > MAX_SERIES:
                raise ChartRenderError(f"at most {MAX_SERIES} series")
            if school:
                line_scatter_school = True
            for si, s in enumerate(series):
                if not isinstance(s, dict):
                    raise ChartRenderError(f"series[{si}] must be an object")
                lab = str(s.get("label") or f"S{si + 1}")
                xs = _finite_list(f"series[{si}].x", s.get("x"), MAX_POINTS_PER_SERIES)
                ys = _finite_list(f"series[{si}].y", s.get("y"), MAX_POINTS_PER_SERIES)
                if len(xs) != len(ys):
                    raise ChartRenderError(f"series[{si}]: x and y length mismatch")
                if kind == "line":
                    xs_b, ys_b = _break_line_at_vertical_asymptote_guess(xs, ys)
                    ax.plot(xs_b, ys_b, label=lab, linewidth=2, zorder=3)
                else:
                    ax.scatter(xs, ys, label=lab, s=36, zorder=3)
            if len(series) > 1 or (series and str(series[0].get("label") or "").strip()):
                leg = ax.legend(loc="best", fontsize=9)
                if leg:
                    leg.set_zorder(5)
            if school:
                _ensure_axis_includes_zero(ax, "x")
                _ensure_axis_includes_zero(ax, "y")
                ax.axhline(0, color="#333333", linewidth=1.0, zorder=2)
                ax.axvline(0, color="#333333", linewidth=1.0, zorder=2)
                _apply_school_grid_and_ticks(ax, spec)
            _draw_labeled_points(ax, spec)

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
    if grid and not line_scatter_school:
        ax.grid(True, alpha=0.35, linestyle="--")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    data = buf.getvalue()
    if len(data) < 100:
        raise ChartRenderError("rendered image is too small")
    return data
