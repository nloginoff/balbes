#!/usr/bin/env python3
"""
Pre-download and load OpenAI Whisper model weights into the local cache.

Run once after deploy or when changing WHISPER_LOCAL_MODEL, so the first Telegram voice
message does not block on multi-GB download + cold load.

Usage (from repo root, with venv activated):
  ENV=prod python scripts/prefetch_whisper.py
  python scripts/prefetch_whisper.py --env dev

Requires the same .env.{env} as the orchestrator (shared Settings), or set WHISPER_LOCAL_MODEL / WHISPER_DEVICE in the environment before import.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prefetch openai-whisper model weights")
    parser.add_argument(
        "--env",
        default=os.environ.get("ENV", "prod"),
        help="Which env file to load (default: ENV or prod)",
    )
    args = parser.parse_args()
    os.environ["ENV"] = args.env

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    import whisper

    from shared.config import get_settings

    settings = get_settings()
    model_id = settings.whisper_local_model
    print(
        f"Prefetch Whisper: model={model_id!r} device={settings.whisper_device!r} "
        f"(this may download several GB on first run)...",
        flush=True,
    )
    whisper.load_model(model_id, device=settings.whisper_device)
    print("Whisper model ready.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
