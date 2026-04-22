"""Textbook-style geometry diagrams: matplotlib Agg, structured spec (no arbitrary code)."""

from __future__ import annotations

import io
import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

MAX_VERTICES = 120
MAX_EDGES = 400
MAX_SEGMENTS = 300
MAX_CIRCLES = 40
MAX_ARCS = 40
MAX_LABELS = 80
FIG_W, FIG_H = 8.0, 8.0
DPI = 120

# Whitelist for flat tool args (registry)
GEOMETRY_SPEC_KEYS = frozenset(
    {
        "mode",
        "title",
        "segments",
        "circles",
        "arcs",
        "points",
        "vertices",
        "labels",
        "edges",
    }
)


class GeometryRenderError(ValueError):
    pass


def _pair_num2(name: str, raw: Any) -> tuple[float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise GeometryRenderError(f"{name} must be [x, y]")
    try:
        a, b = float(raw[0]), float(raw[1])
    except (TypeError, ValueError) as e:
        raise GeometryRenderError(f"{name} elements must be numbers") from e
    if not (math.isfinite(a) and math.isfinite(b)):
        raise GeometryRenderError(f"{name} must be finite")
    return a, b


def _triple(name: str, raw: Any) -> tuple[float, float, float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        raise GeometryRenderError(f"{name} must be [x, y, z]")
    try:
        return float(raw[0]), float(raw[1]), float(raw[2])
    except (TypeError, ValueError) as e:
        raise GeometryRenderError(f"{name} elements must be numbers") from e


def render_geometry_png(spec: dict[str, Any]) -> bytes:
    """
    Render PNG from structured geometry spec.

    mode "2d":
      segments: [[[x1,y1],[x2,y2]], ...]
      circles: [{ "center": [x,y], "radius": r, "fill": bool optional }]
      arcs: [{ "center": [x,y], "radius": r, "theta1": deg, "theta2": deg }], angles CCW from +x
      points: [{ "xy": [x,y], "label": str }]
    mode "3d":
      vertices: [[x,y,z], ...]
      labels: ["P","A", ...] same length as vertices (optional empty string to skip)
      edges: [[i,j], ...] integer indices into vertices
    Optional: title
    """
    if not isinstance(spec, dict):
        raise GeometryRenderError("spec must be an object")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Arc, Circle

    mode = (spec.get("mode") or "2d").strip().lower()
    title = (spec.get("title") or "").strip()

    if mode == "3d":
        return _render_3d(spec, title, plt)
    if mode != "2d":
        raise GeometryRenderError('mode must be "2d" or "3d"')

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI, facecolor="white")
    ax.set_aspect("equal")
    ax.set_facecolor("white")
    ax.axis("off")

    xs_b: list[float] = []
    ys_b: list[float] = []

    def extend_bounds(x: float, y: float) -> None:
        xs_b.append(x)
        ys_b.append(y)

    segments = spec.get("segments") or []
    if isinstance(segments, list) and segments:
        if len(segments) > MAX_SEGMENTS:
            raise GeometryRenderError(f"at most {MAX_SEGMENTS} segments")
        for si, seg in enumerate(segments):
            if not isinstance(seg, (list, tuple)) or len(seg) != 2:
                raise GeometryRenderError(f"segments[{si}] must be [[x1,y1],[x2,y2]]")
            p1 = _pair_num2(f"segments[{si}][0]", seg[0])
            p2 = _pair_num2(f"segments[{si}][1]", seg[1])
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], "k-", linewidth=1.6)
            extend_bounds(p1[0], p1[1])
            extend_bounds(p2[0], p2[1])

    circles = spec.get("circles") or []
    if isinstance(circles, list) and circles:
        if len(circles) > MAX_CIRCLES:
            raise GeometryRenderError(f"at most {MAX_CIRCLES} circles")
        for ci, c in enumerate(circles):
            if not isinstance(c, dict):
                raise GeometryRenderError(f"circles[{ci}] must be an object")
            cx, cy = _pair_num2(f"circles[{ci}].center", c.get("center"))
            r = c.get("radius")
            try:
                rad = float(r)
            except (TypeError, ValueError) as e:
                raise GeometryRenderError(f"circles[{ci}].radius must be a number") from e
            if not math.isfinite(rad) or rad <= 0:
                raise GeometryRenderError(f"circles[{ci}]: positive radius required")
            fill = bool(c.get("fill", False))
            circ = Circle(
                (cx, cy),
                rad,
                fill=fill,
                facecolor="#e6f2ff" if fill else "none",
                edgecolor="k",
                linewidth=1.4,
            )
            ax.add_patch(circ)
            extend_bounds(cx - rad, cy - rad)
            extend_bounds(cx + rad, cy + rad)

    arcs = spec.get("arcs") or []
    if isinstance(arcs, list) and arcs:
        if len(arcs) > MAX_ARCS:
            raise GeometryRenderError(f"at most {MAX_ARCS} arcs")
        for ai, a in enumerate(arcs):
            if not isinstance(a, dict):
                raise GeometryRenderError(f"arcs[{ai}] must be an object")
            cx, cy = _pair_num2(f"arcs[{ai}].center", a.get("center"))
            try:
                rad = float(a.get("radius"))
            except (TypeError, ValueError) as e:
                raise GeometryRenderError(f"arcs[{ai}].radius must be a number") from e
            t1 = float(a.get("theta1", 0))
            t2 = float(a.get("theta2", 90))
            if not (math.isfinite(rad) and rad > 0):
                raise GeometryRenderError(f"arcs[{ai}]: positive radius required")
            arc = Arc(
                (cx, cy),
                2 * rad,
                2 * rad,
                angle=0.0,
                theta1=t1,
                theta2=t2,
                fill=False,
                edgecolor="k",
                linewidth=1.4,
            )
            ax.add_patch(arc)
            extend_bounds(cx - rad, cy - rad)
            extend_bounds(cx + rad, cy + rad)

    points = spec.get("points") or []
    if isinstance(points, list) and points:
        if len(points) > MAX_LABELS:
            raise GeometryRenderError(f"at most {MAX_LABELS} point labels")
        for pi, p in enumerate(points):
            if not isinstance(p, dict):
                raise GeometryRenderError(f"points[{pi}] must be an object")
            x, y = _pair_num2(f"points[{pi}].xy", p.get("xy"))
            lab = str(p.get("label", "")).strip()
            extend_bounds(x, y)
            if lab:
                ax.plot(x, y, "ko", markersize=5)
                ax.annotate(
                    lab,
                    (x, y),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=11,
                    fontweight="normal",
                )
            else:
                ax.plot(x, y, "ko", markersize=4)

    has_2d = bool(
        (isinstance(segments, list) and len(segments) > 0)
        or (isinstance(circles, list) and len(circles) > 0)
        or (isinstance(arcs, list) and len(arcs) > 0)
        or (isinstance(points, list) and len(points) > 0)
    )
    if not has_2d:
        plt.close(fig)
        raise GeometryRenderError(
            "2d: укажи хотя бы одно из полей: segments, circles, arcs, points"
        )

    if xs_b and ys_b:
        pad_x = 0.08 * (max(xs_b) - min(xs_b) or 1.0)
        pad_y = 0.08 * (max(ys_b) - min(ys_b) or 1.0)
        ax.set_xlim(min(xs_b) - pad_x, max(xs_b) + pad_x)
        ax.set_ylim(min(ys_b) - pad_y, max(ys_b) + pad_y)

    if title:
        ax.set_title(title, fontsize=12, pad=8)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    data = buf.getvalue()
    if len(data) < 100:
        raise GeometryRenderError("rendered image is too small")
    return data


def _render_3d(spec: dict[str, Any], title: str, plt: Any) -> bytes:
    vertices = spec.get("vertices")
    if not isinstance(vertices, list) or not vertices:
        raise GeometryRenderError("3d mode requires non-empty vertices[]")
    if len(vertices) > MAX_VERTICES:
        raise GeometryRenderError(f"at most {MAX_VERTICES} vertices")

    pts3: list[tuple[float, float, float]] = []
    for vi, v in enumerate(vertices):
        pts3.append(_triple(f"vertices[{vi}]", v))

    labels = spec.get("labels")
    if labels is not None:
        if not isinstance(labels, list) or len(labels) != len(pts3):
            raise GeometryRenderError("labels[] must have same length as vertices[]")
    else:
        labels = [""] * len(pts3)

    edges = spec.get("edges") or []
    if not isinstance(edges, list):
        raise GeometryRenderError("edges must be an array")
    if len(edges) > MAX_EDGES:
        raise GeometryRenderError(f"at most {MAX_EDGES} edges")

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI, facecolor="white")
    ax = fig.add_subplot(111, projection="3d", facecolor="white")

    n = len(pts3)
    for ei, e in enumerate(edges):
        if not isinstance(e, (list, tuple)) or len(e) != 2:
            raise GeometryRenderError(f"edges[{ei}] must be [i, j]")
        i, j = int(e[0]), int(e[1])
        if not (0 <= i < n and 0 <= j < n):
            raise GeometryRenderError(f"edges[{ei}]: indices out of range 0..{n - 1}")
        a, b = pts3[i], pts3[j]
        ax.plot(
            [a[0], b[0]],
            [a[1], b[1]],
            [a[2], b[2]],
            "k-",
            linewidth=1.4,
        )

    for i, p in enumerate(pts3):
        ax.scatter([p[0]], [p[1]], [p[2]], c="k", s=20)
        lab = str(labels[i] or "").strip()
        if lab:
            ax.text(
                p[0],
                p[1],
                p[2],
                f"  {lab}",
                fontsize=10,
            )

    if title:
        ax.set_title(title, fontsize=12, pad=8)

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white", bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    data = buf.getvalue()
    if len(data) < 100:
        raise GeometryRenderError("rendered image is too small")
    return data
