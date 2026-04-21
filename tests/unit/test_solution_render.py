"""Tests for solution PNG rendering."""

import pytest

from shared.solution_render import (
    PAGE_HEIGHT_PX,
    PAGE_WIDTH_PX,
    render_solution_pages,
)


def test_render_solution_pages_produces_png():
    pages = render_solution_pages("Шаг 1.\n$x^2 + y^2 = r^2$\nГотово.")
    assert len(pages) >= 1
    assert pages[0][:8] == b"\x89PNG\r\n\x1a\n"
    assert len(pages[0]) > 500


def test_fixed_dimensions_constants():
    assert PAGE_WIDTH_PX == 900
    assert PAGE_HEIGHT_PX == 1200


def test_empty_raises():
    with pytest.raises(ValueError):
        render_solution_pages("   ")
