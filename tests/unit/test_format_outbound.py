"""Unit tests for Telegram HTML formatting of model output."""

from shared.telegram_app.format_outbound import model_text_to_telegram_html


def test_escape_lt_gt_amp() -> None:
    s = model_text_to_telegram_html("a < b & c > d")
    assert "&lt;" in s and "&amp;" in s
    assert "<b>" not in s or "a " in s  # not interpreted as tag


def test_underscore_path_not_markdown() -> None:
    s = model_text_to_telegram_html("file: foo/bar_baz.py")
    assert "bar_baz" in s
    assert "<i>" not in s


def test_bold_double_star() -> None:
    s = model_text_to_telegram_html("**hello** world")
    assert "<b>hello</b>" in s
    assert "world" in s


def test_inline_code() -> None:
    s = model_text_to_telegram_html("use `rm -rf /` carefully")
    assert "<code>" in s
    assert "rm -rf /" in s or "rm -rf /" in html_unescape_safe(s)


def html_unescape_safe(s: str) -> str:
    import html as h

    return h.unescape(s)


def test_fenced_code_block() -> None:
    raw = "```\na < b\n```"
    s = model_text_to_telegram_html(raw)
    assert "<pre>" in s
    assert "&lt;" in s


def test_empty() -> None:
    assert model_text_to_telegram_html("") == ""


def test_bold_after_escape() -> None:
    s = model_text_to_telegram_html("**x < y**")
    assert "<b>" in s
    assert "&lt;" in s
