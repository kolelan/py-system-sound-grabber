"""Общая запись аудио в wav/flac/ogg/mp3."""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import soundfile as sf

SUPPORTED_FORMATS: tuple[str, ...] = ("wav", "flac", "ogg", "mp3")


def to_mono_float(raw: bytes, channels: int) -> np.ndarray:
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data


def resample_mono(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    n = max(1, int(round(samples.size * dst_rate / src_rate)))
    x_old = np.linspace(0.0, 1.0, num=samples.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, samples.astype(np.float64)).astype(np.float32)


def write_audio(path: Path, audio: np.ndarray, sample_rate: int, fmt: str) -> None:
    """audio: shape (n,) mono или (n, ch) float32 -1..1."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "wav":
        pcm = np.clip(audio, -1.0, 1.0)
        if pcm.ndim == 1:
            channels = 1
            frames = (pcm * 32767.0).astype(np.int16)
        else:
            channels = pcm.shape[1]
            frames = (pcm * 32767.0).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(frames.tobytes())
        return

    subtype = {
        "flac": "PCM_16",
        "ogg": "VORBIS",
        "mp3": "MPEG_LAYER_III",
    }.get(fmt)
    kwargs: dict = {"format": fmt.upper()}
    if subtype:
        kwargs["subtype"] = subtype
    try:
        sf.write(str(path), audio, sample_rate, **kwargs)
    except Exception:
        sf.write(str(path), audio, sample_rate, format=fmt.upper())
