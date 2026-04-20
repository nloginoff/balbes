#!/usr/bin/env python3
"""Print Telegram HTML for canned strings (no Bot API). Run from repo root: ``python scripts/telegram_html_smoke.py``."""

from __future__ import annotations

import sys
from pathlib import Path

# dev/ as cwd or PYTHONPATH
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from shared.telegram_app.format_outbound import model_text_to_telegram_html  # noqa: E402


def main() -> None:
    samples = [
        "||**_Жирный курсив в спойлере_**||",
        "**_Жирный курсив в спойлере_**",
        "||***abc***||",
    ]
    for s in samples:
        print("---")
        print("IN :", s)
        print("OUT:", model_text_to_telegram_html(s))


if __name__ == "__main__":
    main()
