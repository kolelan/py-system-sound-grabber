"""Whisper small через faster-whisper: универсальное распознавание на CPU."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from stt_base import ProgressFn, SttError, load_audio_16k_mono, maybe_punctuate

DEFAULT_MODEL_DIR = Path("models") / "whisper-small"


class WhisperRecognizer:
    model_id = "whisper-small"

    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR):
        model_dir = Path(model_dir)
        if not (model_dir / "model.bin").is_file():
            raise SttError(
                f"Whisper не найден: {model_dir / 'model.bin'}\n"
                "Скачайте: python stt_download_model.py whisper-small"
            )
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SttError("Нужен пакет faster-whisper: pip install faster-whisper") from exc

        self.model_dir = model_dir
        self.model = WhisperModel(
            str(model_dir),
            device="cpu",
            compute_type="int8",
            local_files_only=True,
        )

    def summary(self) -> str:
        return (
            f"Whisper small (faster-whisper, CPU int8)\n"
            f"  dir: {self.model_dir.resolve()}\n"
            f"  язык: авто (универсальный)"
        )

    def transcribe(
        self,
        audio_path: str | Path,
        punctuate: bool = True,
        on_progress: Optional[ProgressFn] = None,
    ) -> str:
        audio = load_audio_16k_mono(audio_path)
        duration = max(audio.size / 16_000, 0.001)
        segments, _info = self.model.transcribe(
            audio,
            language=None,
            vad_filter=True,
            beam_size=1,
        )
        parts: list[str] = []
        for segment in segments:
            piece = (segment.text or "").strip()
            if piece:
                parts.append(piece)
            if on_progress is not None:
                on_progress(min(1.0, float(segment.end) / duration))
        if on_progress is not None:
            on_progress(1.0)
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        return maybe_punctuate(text, punctuate)
