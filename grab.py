#!/usr/bin/env python3
"""CLI: запись системного звука через WASAPI loopback."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from recorder import RecorderError, SystemAudioRecorder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Запись того, что сейчас воспроизводит Windows (WASAPI loopback).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="system_recording.wav",
        help="Путь к WAV-файлу (по умолчанию: system_recording.wav)",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=None,
        help="Длительность в секундах. Без флага — до Ctrl+C",
    )
    parser.add_argument(
        "-i",
        "--device",
        type=int,
        default=None,
        help="Индекс loopback-устройства (см. --list)",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Показать доступные WASAPI loopback-устройства и выйти",
    )
    return parser


def list_devices(recorder: SystemAudioRecorder) -> int:
    devices = recorder.list_devices()
    if not devices:
        print("Loopback-устройства не найдены.")
        return 1

    try:
        default = recorder.get_default_device()
        default_index = default.index
    except RecorderError:
        default_index = None

    print("WASAPI loopback-устройства:")
    for device in devices:
        mark = " [default]" if device.index == default_index else ""
        print(f"  {device}{mark}")
    return 0


def record(recorder: SystemAudioRecorder, args: argparse.Namespace) -> int:
    output = Path(args.output)
    device = recorder.start(
        output_path=output,
        device_index=args.device,
        duration=args.duration,
    )
    print(f"Запись с: {device}")
    print(f"Файл: {output.resolve()}")
    if args.duration:
        print(f"Длительность: {args.duration:.1f} с (или Ctrl+C для стопа)")
    else:
        print("Идёт запись… Ctrl+C — стоп")

    try:
        while recorder.is_recording:
            elapsed = recorder.elapsed
            if args.duration:
                print(f"\r  {elapsed:6.1f} / {args.duration:.1f} с", end="", flush=True)
            else:
                print(f"\r  {elapsed:6.1f} с", end="", flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nОстановка…")
    finally:
        path = recorder.stop()

    if recorder.last_error:
        print(f"Ошибка записи: {recorder.last_error}", file=sys.stderr)
        return 1

    if path and path.exists():
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"\nСохранено: {path.resolve()} ({size_mb:.2f} MB)")
        return 0

    print("\nФайл не создан.", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with SystemAudioRecorder() as recorder:
            if args.list:
                return list_devices(recorder)
            return record(recorder, args)
    except RecorderError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
