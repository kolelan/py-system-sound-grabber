"""Общий контракт локального STT и загрузка аудио 16 kHz mono."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Protocol

import numpy as np

SAMPLE_RATE = 16_000
ProgressFn = Callable[[float], None]


class SttError(Exception):
    """Ошибка загрузки модели, скачивания или распознавания."""


class SttRecognizer(Protocol):
    model_id: str

    def transcribe(
        self,
        audio_path: str | Path,
        punctuate: bool = True,
        on_progress: Optional[ProgressFn] = None,
    ) -> str: ...

    def summary(self) -> str: ...


def load_audio_16k_mono(path: str | Path) -> np.ndarray:
    import soundfile as sf

    from audio_io import resample_mono

    audio, sr = sf.read(str(path), always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if int(sr) != SAMPLE_RATE:
        audio = resample_mono(audio, int(sr), SAMPLE_RATE)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 1e-6:
        audio = audio / peak * 0.95
    return audio.astype(np.float32)


def maybe_punctuate(text: str, enabled: bool) -> str:
    """Silero TE (русский). Ошибки пунктуации не валят распознавание."""
    text = (text or "").strip()
    if not enabled or not text:
        return text
    try:
        return str(_punctuation_model()(text, lan="ru")).strip()
    except Exception:  # noqa: BLE001
        return text


_te_model = None


def _punctuation_model():
    global _te_model
    if _te_model is not None:
        return _te_model

    import sys

    hub_dir = Path.home() / ".cache" / "torch" / "hub" / "snakers4_silero-models_master"
    silero_src = hub_dir / "src" / "silero"
    if silero_src.is_dir():
        sys.path.insert(0, str(silero_src))
        from silero import silero_te  # type: ignore

        _, _, _, _, apply_te = silero_te()
        _te_model = apply_te
        return _te_model

    import torch

    _model, _example_texts, _languages, _punct, apply_te = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_te",
    )
    _te_model = apply_te
    return _te_model
