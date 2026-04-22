"""Smoke tests for deterministic chart/geometry matplotlib renders."""

import pytest

from shared.chart_render import render_chart_png
from shared.geometry_render import GeometryRenderError, render_geometry_png


def test_render_chart_line_png():
    spec = {
        "kind": "line",
        "title": "t",
        "series": [{"label": "y=x", "x": [0, 1, 2], "y": [0, 1, 2]}],
    }
    png = render_chart_png(spec)
    assert len(png) > 200
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_chart_histogram():
    spec = {"kind": "histogram", "values": [0.1, 0.2, 0.5, 0.3], "bins": 4}
    png = render_chart_png(spec)
    assert len(png) > 200


def test_render_geometry_2d_segment():
    spec = {
        "mode": "2d",
        "segments": [[[0, 0], [1, 0]], [[1, 0], [0.5, 0.8]]],
        "points": [{"xy": [0, 0], "label": "A"}, {"xy": [1, 0], "label": "B"}],
    }
    png = render_geometry_png(spec)
    assert len(png) > 200
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_geometry_3d_edge():
    spec = {
        "mode": "3d",
        "vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "labels": ["O", "X", "Y", "Z"],
        "edges": [[0, 1], [0, 2], [0, 3]],
    }
    png = render_geometry_png(spec)
    assert len(png) > 200


def test_render_geometry_2d_empty_errors():
    with pytest.raises(GeometryRenderError, match="2d:"):
        render_geometry_png({"mode": "2d"})
