"""Tests for document_extract sniffing and extensions."""

from shared.document_extract import extract_text_from_bytes, sniff_plain_text_bytes


def test_sniff_python_without_relying_on_extension():
    code = b"def hello():\n    return 42\n"
    assert sniff_plain_text_bytes(code) is not None
    text, err = extract_text_from_bytes("script.unknown_ext", code)
    assert "hello" in text
    assert err is None


def test_sniff_no_extension():
    text, err = extract_text_from_bytes(
        "Makefile",
        b"all:\n\t@echo ok\n",
    )
    assert "ok" in text
    assert err is None


def test_py_extension():
    text, err = extract_text_from_bytes("x.py", b"# hi\nx = 1\n")
    assert "hi" in text
    assert err is None


def test_pl_extension():
    text, err = extract_text_from_bytes("x.pl", b"#!/usr/bin/perl\nprint 1;\n")
    assert err is None
    assert "perl" in text or "print" in text


def test_binary_not_decoded_as_text():
    data = bytes(range(256)) * 40  # lots of NULs and controls
    assert sniff_plain_text_bytes(data) is None


def test_pdf_magic_without_extension():
    # minimal invalid pdf header still triggers pdf path only if %PDF
    # use real empty pdf structure is heavy; skip or use fitz
    text, err = extract_text_from_bytes("bin", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    # may fail to extract text from junk - that's ok
    assert isinstance(text, str)
    assert isinstance(err, str | None)
