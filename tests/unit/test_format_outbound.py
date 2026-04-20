"""Unit tests for Telegram HTML formatting of model output."""

import logging

import pytest
from telegram.constants import ParseMode
from telegram.error import BadRequest

from shared.telegram_app.format_outbound import (
    TELEGRAM_HTML_MSG_LIMIT,
    model_text_to_telegram_html,
    raw_chunks_for_telegram_html,
    send_reply_html_with_plain_fallback,
    split_raw_coarse_for_telegram,
    telegram_message_text_units,
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
        assert (
            telegram_message_text_units(model_text_to_telegram_html(c)) <= TELEGRAM_HTML_MSG_LIMIT
        )


def test_raw_chunks_split_when_emoji_utf16_exceeds_limit() -> None:
    """Emoji are 2 UTF-16 units each; len() can stay under 4096 while Telegram rejects the body."""
    raw = "\U0001f600" * 2100  # 😀 × 2100 → 4200 UTF-16 units
    assert len(raw) < TELEGRAM_HTML_MSG_LIMIT
    assert telegram_message_text_units(raw) > TELEGRAM_HTML_MSG_LIMIT
    chunks = raw_chunks_for_telegram_html(raw)
    assert len(chunks) > 1
    for c in chunks:
        body = model_text_to_telegram_html(c)
        assert telegram_message_text_units(body) <= TELEGRAM_HTML_MSG_LIMIT


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


def test_bare_https_url_clickable() -> None:
    s = model_text_to_telegram_html("См. https://a.com/x. Далее")
    assert 'href="https://a.com/x"' in s
    assert "</a>. Далее" in s


def test_bare_url_inside_parentheses() -> None:
    s = model_text_to_telegram_html("Посетите (https://example.com/) ок")
    assert 'href="https://example.com/"' in s
    assert "example.com/)" not in s.split("href=")[1][:80]


def test_bare_print_line_becomes_code() -> None:
    s = model_text_to_telegram_html('x:\nprint("hi")')
    assert "<code>" in s and "print" in s


def test_star_underscore_nested_no_literal_marks() -> None:
    """*_x_* and ***_y_***: _italic_ runs before * / *** so Telegram gets tags, not raw _ *."""
    s = model_text_to_telegram_html("*_Секретное сообщение_*")
    assert "<i>Секретное сообщение</i>" == s
    assert "_" not in s and "*" not in s
    s2 = model_text_to_telegram_html("***_Помните_***")
    assert s2 == "<b><i>Помните</i></b>"
    assert "_" not in s2 and "*" not in s2


def test_strike_tilde() -> None:
    s = model_text_to_telegram_html("~~z~~")
    assert s == "<s>z</s>"


def test_bold_italic_combo_star_underscore() -> None:
    s = model_text_to_telegram_html("*__a__*")
    assert "<b>" in s and "<i>" in s


def test_anchor_single_quoted_href() -> None:
    s = model_text_to_telegram_html("<a href='https://t.me/x'>y</a>")
    assert 'href="https://t.me/x"' in s and "y" in s


def test_blockquote_labeled_md_prefix() -> None:
    s = model_text_to_telegram_html("MD: > Это цитата")
    assert s == "<blockquote>Это цитата</blockquote>"


def test_blockquote_bracket_number_prefix() -> None:
    s = model_text_to_telegram_html("[10] MD: > Один")
    assert "<blockquote>Один</blockquote>" in s


def test_triple_star_bold_italic() -> None:
    assert model_text_to_telegram_html("***ab***") == "<b><i>ab</i></b>"


def test_split_coarse_does_not_bisect_triple_backtick_block() -> None:
    """Hard cut inside ``` breaks <pre>; coarse split should move cut before the fence."""
    pad = "p" * 1200
    fence_body = "c" * 80 + "\n"
    text = pad + "\n```\n" + fence_body + "```\n" + pad
    chunks = split_raw_coarse_for_telegram(text, limit=900)
    for ch in chunks:
        h = model_text_to_telegram_html(ch)
        assert h.count("<pre>") == h.count("</pre>")


def test_golden_test3_snippet() -> None:
    """Сжатый фрагмент пользовательского теста №3 (MD/HTML/цитата/спойлер)."""
    raw = """### Заголовок
[1] ЖИРНЫЙ:
MD: **Жирный текст**
HTML: <b>Жирный текст</b>

[2] КУРСИВ:
MD: *Курсивный текст*
HTML: <i>Курсивный текст</i>

[4] СПОЙЛЕР:
MD: ||скрытый текст||
HTML: <tg-spoiler>скрытый текст</tg-spoiler>

[10] ЦИТАТА:
MD: > Это цитата

[7] ***жирный курсив***
"""
    s = model_text_to_telegram_html(raw)
    assert "<b>Жирный текст</b>" in s
    assert "<i>Курсивный текст</i>" in s
    assert "<tg-spoiler>скрытый текст</tg-spoiler>" in s
    assert "<blockquote>Это цитата</blockquote>" in s
    assert "<b><i>жирный курсив</i></b>" in s


async def test_send_reply_html_fallback_on_badrequest(caplog: pytest.LogCaptureFixture) -> None:
    """BadRequest on HTML send triggers plain fallback; outbound logs are emitted."""
    caplog.set_level(logging.INFO)
    calls: list[tuple[str, str | None]] = []

    async def send_coro(text: str, *, parse_mode: str | None = None) -> None:
        calls.append((text, parse_mode))
        if parse_mode == ParseMode.HTML:
            raise BadRequest('Unsupported start tag "bad" at byte offset 0')

    await send_reply_html_with_plain_fallback(send_coro, "x **y**")
    assert len(calls) == 2
    assert calls[1][1] is None
    assert any("telegram_html_outbound" in r.message for r in caplog.records)
    assert any(r.levelno >= logging.WARNING and "BadRequest" in r.message for r in caplog.records)
