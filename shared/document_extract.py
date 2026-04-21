"""Extract plain text from common document types (PDF, docx, xlsx, xls, text)."""

from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Hard cap after extraction (chars) — rest truncated with notice
MAX_EXTRACT_CHARS = 120_000


def _truncate(s: str) -> tuple[str, bool]:
    if len(s) <= MAX_EXTRACT_CHARS:
        return s, False
    return s[: MAX_EXTRACT_CHARS - 80] + "\n\n… [текст обрезан по лимиту]", True


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
        if suffix in (".txt", ".md", ".csv", ".log", ".json", ".yaml", ".yml", ".toml", ".env"):
            text = data.decode("utf-8", errors="replace")
            out, _ = _truncate(text.strip())
            return out, None

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
            out, trunc = _truncate(raw)
            if trunc:
                return out, None
            return out, None

        if suffix == ".docx":
            import docx

            d = docx.Document(io.BytesIO(data))
            raw = "\n".join(p.text for p in d.paragraphs).strip()
            if not raw:
                return "", "Не удалось прочитать DOCX"
            out, _ = _truncate(raw)
            return out, None

        if suffix == ".xlsx":
            import openpyxl

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
            if not raw:
                return "", "Таблица пуста"
            out, _ = _truncate(raw)
            return out, None

        if suffix == ".xls":
            # Legacy Excel (BIFF), not ZIP — openpyxl only supports .xlsx
            import xlrd

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
            if not raw:
                return "", "Таблица пуста"
            out, _ = _truncate(raw)
            return out, None

        # Guess text by extension
        if "readme" in name_l and suffix == "":
            text = data.decode("utf-8", errors="replace")
            out, _ = _truncate(text.strip())
            return out, None

    except Exception as e:
        logger.warning("document_extract failed for %s: %s", filename, e)
        return "", f"Не удалось прочитать файл: {e!s}"

    return "", f"Неподдерживаемый тип файла ({suffix or 'без расширения'})"
