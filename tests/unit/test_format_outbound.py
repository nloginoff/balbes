"""Unit tests for Telegram HTML formatting of model output."""

from shared.telegram_app.format_outbound import (
    TELEGRAM_HTML_MSG_LIMIT,
    model_text_to_telegram_html,
    raw_chunks_for_telegram_html,
)


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


def test_raw_chunks_split_when_html_longer_than_telegram_limit() -> None:
    """`&` becomes `&amp;` (5 chars); a 4096-char raw chunk can exceed API limit after escape."""
    raw = "&" * 4096
    chunks = raw_chunks_for_telegram_html(raw)
    assert len(chunks) > 1
    for c in chunks:
        assert len(model_text_to_telegram_html(c)) <= TELEGRAM_HTML_MSG_LIMIT


def test_bold_double_underscore() -> None:
    s = model_text_to_telegram_html("__x__")
    assert s == "<b>x</b>"


def test_spoiler_double_pipe() -> None:
    s = model_text_to_telegram_html("||secret||")
    assert "<tg-spoiler>" in s and "secret" in s


def test_markdown_link() -> None:
    s = model_text_to_telegram_html("[t](https://a.com)")
    assert 'href="https://a.com"' in s
    assert "<a " in s


def test_raw_simple_html_not_double_escaped() -> None:
    s = model_text_to_telegram_html("<b>ok</b>")
    assert s == "<b>ok</b>"


def test_wrong_spoiler_tag_mapped() -> None:
    s = model_text_to_telegram_html("<spoiler>x</spoiler>")
    assert s == "<tg-spoiler>x</tg-spoiler>"


def test_blockquote_gt_line() -> None:
    s = model_text_to_telegram_html("> quote")
    assert "<blockquote>" in s and "quote" in s


def test_heading_stripped_to_bold() -> None:
    s = model_text_to_telegram_html("### Title")
    assert s == "<b>Title</b>"


def test_nested_html_b_i() -> None:
    s = model_text_to_telegram_html("<b><i>x</i></b>")
    assert s == "<b><i>x</i></b>"


def test_strike_tilde() -> None:
    s = model_text_to_telegram_html("~~z~~")
    assert s == "<s>z</s>"


def test_bold_italic_combo_star_underscore() -> None:
    s = model_text_to_telegram_html("*__a__*")
    assert "<b>" in s and "<i>" in s


def test_anchor_single_quoted_href() -> None:
    s = model_text_to_telegram_html("<a href='https://t.me/x'>y</a>")
    assert 'href="https://t.me/x"' in s and "y" in s
