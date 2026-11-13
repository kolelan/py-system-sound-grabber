#!/usr/bin/env python3
"""CLI: распознавание аудио локальной моделью (GigaAM / Whisper / Vosk)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from llm_rewrite import LlmError, LlmSettings, api_key_from_env, rewrite_text
from stt_base import SttError
from stt_catalog import MODEL_IDS, open_recognizer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Распознать речь локально. Опционально — доработка через DeepSeek.",
    )
    p.add_argument("audio", nargs="?", help="Аудиофайл (wav/flac/ogg/mp3…)")
    p.add_argument(
        "--model",
        default="gigaam-v3",
        choices=MODEL_IDS,
        help="Модель: gigaam-v3 | whisper-small | vosk-small-ru",
    )
    p.add_argument("-o", "--output", default=None, help="Сохранить текст в файл")
    p.add_argument("--no-punct", action="store_true", help="Без Silero-пунктуации")
    p.add_argument(
        "--rewrite-prompt",
        default=None,
        help="Если задан — отправить текст в LLM с этим уточняющим промптом",
    )
    p.add_argument("--api-key", default=None, help="API-ключ (иначе DEEPSEEK_API_KEY)")
    p.add_argument(
        "--api-base",
        default="https://api.deepseek.com",
        help="Base URL OpenAI-совместимого API",
    )
    p.add_argument(
        "--api-model",
        default="deepseek-chat",
        help="Имя модели (deepseek-chat / deepseek-flash / …)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.audio:
        build_parser().print_help()
        return 1

    audio = Path(args.audio)
    if not audio.is_file():
        print(f"Файл не найден: {audio}", file=sys.stderr)
        return 1

    try:
        print(f"Загрузка модели: {args.model}", file=sys.stderr)
        asr = open_recognizer(args.model)
        print(asr.summary(), file=sys.stderr)

        t0 = time.perf_counter()
        text = asr.transcribe(audio, punctuate=not args.no_punct)
        dt = time.perf_counter() - t0
        print(f"STT {dt:.1f}s", file=sys.stderr)
    except SttError as exc:
        print(f"Ошибка STT: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    if args.rewrite_prompt:
        key = (args.api_key or api_key_from_env()).strip()
        try:
            text = rewrite_text(
                text,
                args.rewrite_prompt,
                LlmSettings(api_key=key, base_url=args.api_base, model=args.api_model),
            )
        except LlmError as exc:
            print(f"Ошибка LLM: {exc}", file=sys.stderr)
            return 1

    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"Сохранено: {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
