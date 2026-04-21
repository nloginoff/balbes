"""MAX outbound markdown conversion and raw chunking."""

from shared.max_format_outbound import (
    MAX_MARKDOWN_MSG_LIMIT,
    max_markdown_to_plain,
    model_text_to_max_markdown,
    raw_chunks_for_max_markdown,
    telegram_html_to_max_markdown,
)


def test_telegram_html_to_max_markdown_bold_italic_link() -> None:
    html = '<b>Hi</b> <i>there</i> <a href="https://ex.com">link</a>'
    md = telegram_html_to_max_markdown(html)
    assert "**Hi**" in md
    assert "*there*" in md
    assert "[link](https://ex.com)" in md


def test_underline_strike_code_max_syntax() -> None:
    html = "<u>u</u> <s>s</s> <code>c</code>"
    md = telegram_html_to_max_markdown(html)
    assert "++u++" in md
    assert "~~s~~" in md
    assert "`c`" in md


def test_model_text_fenced_block_becomes_fences() -> None:
    raw = "intro\n\n```py\nx = 1\n```\n"
    md = model_text_to_max_markdown(raw)
    assert "```" in md
    assert "x = 1" in md


def test_max_markdown_to_plain_strips_markup() -> None:
    plain = max_markdown_to_plain("**b** [t](https://a.com)")
    assert "b" in plain
    assert "t" in plain
    assert "**" not in plain
    assert "(" not in plain or "https" not in plain  # link stripped to label


def test_raw_chunks_respects_limit() -> None:
    # One coarse piece longer than limit after conversion — should split raw until pieces fit
    filler = "x\n\n" * 3000
    raw = filler + "tail " + "z" * 500
    chunks = raw_chunks_for_max_markdown(raw)
    assert len(chunks) >= 1
    for c in chunks:
        assert len(model_text_to_max_markdown(c)) <= MAX_MARKDOWN_MSG_LIMIT
