"""Smoke tests for deterministic chart/geometry matplotlib renders."""

import pytest

from shared.agent_tools.registry import ToolDispatcher, _summarize_input
from shared.chart_render import _coerce_axis_step, render_chart_png
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


def test_coerce_chart_spec_flat_line_without_spec_key():
    args = {
        "kind": "line",
        "series": [{"label": "L", "x": [0, 1], "y": [0, 1]}],
    }
    spec, err = ToolDispatcher._coerce_chart_spec(args)
    assert err is None
    assert spec == {
        "kind": "line",
        "series": [{"label": "L", "x": [0, 1], "y": [0, 1]}],
    }


def test_coerce_chart_spec_nested_spec_wins():
    args = {
        "kind": "bar",
        "spec": {
            "kind": "line",
            "series": [{"label": "A", "x": [0], "y": [0]}],
        },
    }
    spec, err = ToolDispatcher._coerce_chart_spec(args)
    assert err is None
    assert spec["kind"] == "line"


def test_coerce_geometry_spec_flat_2d():
    args = {
        "mode": "2d",
        "segments": [[[0, 0], [1, 0]]],
    }
    spec, err = ToolDispatcher._coerce_geometry_spec(args)
    assert err is None
    assert spec["mode"] == "2d" and "segments" in spec


def test_summarize_input_render_chart_flat():
    s = _summarize_input(
        "render_chart",
        {
            "kind": "scatter",
            "style": "school",
            "series": [{"label": "S", "x": [-1, 0, 1], "y": [1, 0, 1]}],
        },
    )
    assert s == "kind=scatter"
    g = _summarize_input("render_geometry", {"mode": "2d", "segments": [[[0, 0], [1, 1]]]})
    assert g == "mode=2d"


def test_render_chart_line_school_style_png():
    spec = {
        "kind": "line",
        "style": "school",
        "series": [{"label": "y", "x": [-1, 0, 1], "y": [-1, 0, 1]}],
    }
    png = render_chart_png(spec)
    assert len(png) > 200
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_coerce_axis_step_caps_tick_density():
    assert _coerce_axis_step(20.0, 1.0) == 1.0
    assert _coerce_axis_step(100.0, 1.0) > 1.0
    assert _coerce_axis_step(100.0, 1.0) == 5.0


def test_render_chart_school_labeled_points():
    spec = {
        "kind": "line",
        "style": "school",
        "grid_step": 1,
        "series": [{"label": "f", "x": [-2, 2], "y": [-1, 1]}],
        "points": [
            {"x": 0, "y": 0, "label": "O"},
            {"x": -1, "y": 0.5, "label": "A"},
        ],
    }
    png = render_chart_png(spec)
    assert len(png) > 200
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
