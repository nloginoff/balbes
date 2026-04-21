"""Extract plain text from common document types (PDF, docx, xlsx, xls, plain text).

Non-binary files are detected by **sniffing** (UTF-8/UTF-16/legacy encodings) so unknown
extensions (.py, .pl, no extension) work without maintaining a huge allowlist.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_EXTRACT_CHARS = 120_000

# Formats handled by structured parsers only
_STRUCTURED_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".xls"})

# If sniff fails, still try UTF-8 replace for these (known text/code extensions)
_FALLBACK_UTF8_SUFFIXES = frozenset(
    {
        ".txt",
        ".md",
        ".csv",
        ".log",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".env",
        ".ini",
        ".cfg",
        ".properties",
        ".xml",
        ".html",
        ".htm",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".mjs",
        ".cjs",
        ".py",
        ".pyw",
        ".pyi",
        ".pl",
        ".pm",
        ".t",
        ".r",
        ".R",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        ".c",
        ".h",
        ".cpp",
        ".cc",
        ".cxx",
        ".hpp",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".swift",
        ".rb",
        ".php",
        ".cs",
        ".fs",
        ".scala",
        ".clj",
        ".tex",
        ".bib",
        ".srt",
        ".vtt",
        ".vue",
        ".svelte",
        ".graphql",
        ".gradle",
        ".dockerfile",
    }
)


def _truncate(s: str) -> tuple[str, bool]:
    if len(s) <= MAX_EXTRACT_CHARS:
        return s, False
    return s[: MAX_EXTRACT_CHARS - 80] + "\n\n… [текст обрезан по лимиту]", True


def _mostly_printable(s: str, threshold: float = 0.82) -> bool:
    if not s or not s.strip():
        return False
    n = len(s)
    if s.count("\ufffd") / n > 0.02:
        return False
    ok = sum(1 for c in s if c.isprintable() or c in "\n\r\t\f\v")
    return (ok / n) >= threshold


def sniff_plain_text_bytes(data: bytes) -> str | None:
    """
    If bytes look like human-readable plain text, return decoded string; else None.
    Exported for tests and optional reuse.
    """
    if not data:
        return None
    if len(data) > 50 * 1024 * 1024:
        return None

    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        try:
            t = data.decode("utf-16")
            return t if _mostly_printable(t) else None
        except Exception:
            return None

    sample = data[: min(len(data), 65536)]
    if b"\x00" in sample:
        return None

    for enc in ("utf-8-sig", "utf-8", "cp1251", "koi8-r", "latin-1"):
        try:
            t = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if _mostly_printable(t):
            return t
    return None


def extract_text_from_bytes(filename: str, data: bytes) -> tuple[str, str | None]:
    """
    Returns (extracted_text, error_message).
    error_message is set when nothing could be read (caller may still use empty string).
    """
    if not data:
        return "", "Пустой файл"

    suffix = Path(filename or "").suffix.lower()
    name_l = (filename or "").lower()

    try:
        # ── PDF ──────────────────────────────────────────────────────────
        if suffix == ".pdf" or (not suffix and data[:4] == b"%PDF"):
            import fitz  # PyMuPDF

            doc = fitz.open(stream=data, filetype="pdf")
            parts: list[str] = []
            for page in doc:
                parts.append(page.get_text() or "")
            doc.close()
            raw = "\n\n".join(parts).strip()
            if not raw:
                return (
                    "",
                    "В PDF не найдено текстового слоя (возможно, скан). Пришлите фото страницы или используйте /vision.",
                )
            out, _ = _truncate(raw)
            return out, None

        # ── DOCX ─────────────────────────────────────────────────────────
        if suffix == ".docx":
            import docx

            try:
                d = docx.Document(io.BytesIO(data))
                raw = "\n".join(p.text for p in d.paragraphs).strip()
            except Exception as e:
                logger.warning("docx parse failed for %s: %s", filename, e)
                sniff = sniff_plain_text_bytes(data)
                if sniff is not None:
                    out, _ = _truncate(sniff.strip())
                    return out, f"DOCX не распознан; обработан как текст: {e!s}"
                return "", f"Не удалось прочитать DOCX: {e!s}"

            if not raw:
                sniff = sniff_plain_text_bytes(data)
                if sniff is not None:
                    out, _ = _truncate(sniff.strip())
                    return out, "DOCX без текста; применено определение по содержимому"
                return "", "Не удалось прочитать DOCX"
            out, _ = _truncate(raw)
            return out, None

        # ── XLSX ───────────────────────────────────────────────────────────
        if suffix == ".xlsx":
            import openpyxl

            try:
                wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
                lines: list[str] = []
                for sheet in wb.worksheets:
                    lines.append(f"## {sheet.title}")
                    for row in sheet.iter_rows(values_only=True):
                        cells = [str(c) if c is not None else "" for c in row]
                        if any(str(x).strip() for x in cells):
                            lines.append("\t".join(cells))
                wb.close()
                raw = "\n".join(lines).strip()
            except Exception as e:
                logger.warning("xlsx parse failed for %s: %s", filename, e)
                sniff = sniff_plain_text_bytes(data)
                if sniff is not None:
                    out, _ = _truncate(sniff.strip())
                    return out, f"XLSX не прочитан; обработан как текст: {e!s}"
                return "", f"Не удалось прочитать XLSX: {e!s}"

            if not raw:
                sniff = sniff_plain_text_bytes(data)
                if sniff is not None:
                    out, _ = _truncate(sniff.strip())
                    return out, "Таблица пуста; применено определение по содержимому"
                return "", "Таблица пуста"
            out, _ = _truncate(raw)
            return out, None

        # ── XLS (legacy) ─────────────────────────────────────────────────
        if suffix == ".xls":
            import xlrd

            try:
                book = xlrd.open_workbook(file_contents=data)
                lines: list[str] = []
                for sheet in book.sheets():
                    lines.append(f"## {sheet.name}")
                    for row_idx in range(sheet.nrows):
                        row = sheet.row_values(row_idx)
                        cells = [str(c) if c is not None else "" for c in row]
                        if any(x.strip() for x in cells):
                            lines.append("\t".join(cells))
                raw = "\n".join(lines).strip()
            except Exception as e:
                logger.warning("xls parse failed for %s: %s", filename, e)
                sniff = sniff_plain_text_bytes(data)
                if sniff is not None:
                    out, _ = _truncate(sniff.strip())
                    return out, f"XLS не прочитан; обработан как текст: {e!s}"
                return "", f"Не удалось прочитать XLS: {e!s}"

            if not raw:
                sniff = sniff_plain_text_bytes(data)
                if sniff is not None:
                    out, _ = _truncate(sniff.strip())
                    return out, "Таблица пуста; применено определение по содержимому"
                return "", "Таблица пуста"
            out, _ = _truncate(raw)
            return out, None

        # ── Plain text: sniff first (unknown ext, no ext, code files) ────
        if suffix not in _STRUCTURED_SUFFIXES:
            sniffed = sniff_plain_text_bytes(data)
            if sniffed is not None:
                out, _ = _truncate(sniffed.strip())
                return out, None

            if suffix in _FALLBACK_UTF8_SUFFIXES or (not suffix and "readme" in name_l):
                text = data.decode("utf-8", errors="replace")
                out, _ = _truncate(text.strip())
                if out.strip():
                    return out, None

    except Exception as e:
        logger.warning("document_extract failed for %s: %s", filename, e)
        return "", f"Не удалось прочитать файл: {e!s}"

    return "", f"Неподдерживаемый тип файла ({suffix or 'без расширения'}) — не похоже на текст"
