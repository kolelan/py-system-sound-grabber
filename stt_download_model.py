#!/usr/bin/env python3
"""Скачать локальную STT-модель: gigaam-v3, whisper-small или vosk-small-ru."""

from __future__ import annotations

import argparse

from stt_base import SttError
from stt_catalog import MODEL_IDS, all_models, download, is_installed


def main() -> int:
    parser = argparse.ArgumentParser(description="Скачать модель распознавания речи")
    parser.add_argument(
        "model",
        nargs="?",
        default="gigaam-v3",
        choices=MODEL_IDS,
        help="Какую модель скачать (по умолчанию gigaam-v3)",
    )
    parser.add_argument("--list", action="store_true", help="Показать каталог и что уже установлено")
    args = parser.parse_args()

    if args.list:
        for spec in all_models():
            state = "установлена" if is_installed(spec) else "нет"
            print(f"{spec.id:16} {state:12} {spec.directory}  — {spec.hint}")
        return 0

    def on_progress(frac: float, message: str) -> None:
        print(f"[{frac * 100:5.1f}%] {message}")

    try:
        path = download(args.model, on_progress)
    except SttError as exc:
        print(f"Ошибка: {exc}")
        return 1
    print(f"Каталог: {path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
