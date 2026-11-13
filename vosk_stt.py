"""Vosk small-ru: лёгкое русское распознавание на CPU."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import numpy as np

from stt_base import SAMPLE_RATE, ProgressFn, SttError, load_audio_16k_mono, maybe_punctuate

DEFAULT_MODEL_DIR = Path("models") / "vosk-small-ru"


class VoskRecognizer:
    model_id = "vosk-small-ru"

    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR):
        model_dir = Path(model_dir)
        if not (model_dir / "am" / "final.mdl").is_file():
            raise SttError(
                f"Vosk не найден: {model_dir}\n"
                "Скачайте: python stt_download_model.py vosk-small-ru"
            )
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except ImportError as exc:
            raise SttError("Нужен пакет vosk: pip install vosk") from exc

        SetLogLevel(-1)
        self.model_dir = model_dir
        self._model = Model(str(model_dir))
        self._recognizer_cls = KaldiRecognizer

    def summary(self) -> str:
        return (
            f"Vosk small-ru (CPU)\n"
            f"  dir: {self.model_dir.resolve()}\n"
            f"  язык: русский, лёгкая модель"
        )

    def transcribe(
        self,
        audio_path: str | Path,
        punctuate: bool = True,
        on_progress: Optional[ProgressFn] = None,
    ) -> str:
        audio = load_audio_16k_mono(audio_path)
        pcm = np.clip(audio, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16).tobytes()
        rec = self._recognizer_cls(self._model, SAMPLE_RATE)
        rec.SetWords(False)

        step = 8000
        parts: list[str] = []
        total = max(1, len(pcm))
        for offset in range(0, len(pcm), step):
            chunk = pcm[offset : offset + step]
            if rec.AcceptWaveform(chunk):
                parts.append(_text_of(rec.Result()))
            if on_progress is not None:
                on_progress(min(1.0, (offset + len(chunk)) / total))
        parts.append(_text_of(rec.FinalResult()))
        if on_progress is not None:
            on_progress(1.0)
        text = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
        return maybe_punctuate(text, punctuate)


def _text_of(raw: str) -> str:
    try:
        return str(json.loads(raw).get("text") or "").strip()
    except json.JSONDecodeError:
        return ""
