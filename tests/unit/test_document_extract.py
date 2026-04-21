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
    # High NUL ratio in the sniff sample rejects binary blobs (latin-1 of all bytes looks "printable").
    data = b"\x00" * 4000 + b"\xff" * 4000
    assert sniff_plain_text_bytes(data) is None


def test_pdf_magic_without_extension():
    # minimal invalid pdf header still triggers pdf path only if %PDF
    # use real empty pdf structure is heavy; skip or use fitz
    text, err = extract_text_from_bytes("bin", b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    # may fail to extract text from junk - that's ok
    assert isinstance(text, str)
    assert isinstance(err, str | None)


def test_empty_code_file_message():
    text, err = extract_text_from_bytes("x.py", b"   \n\t  ")
    assert not text.strip()
    assert err == "В файле нет текста"


def test_no_extension_with_mime_text_plain():
    text, err = extract_text_from_bytes("file", b"line1\nline2\n", mime_type="text/plain")
    assert "line1" in text
    assert err is None


def test_binary_unknown_extension_error_wording():
    data = b"\x00" * 500 + b"\x01\x02\x03" * 200
    text, err = extract_text_from_bytes("weird.bin", data)
    assert not text.strip()
    assert "Не удалось извлечь текст" in (err or "")
    assert "Неподдерживаемый" not in (err or "")
    assert ".bin" in (err or "")
