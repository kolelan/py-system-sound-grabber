"""Расширенная запись с микрофона: буфер, noise gate + pre/post-roll, voice EQ, сегменты."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pyaudiowpatch as pyaudio

from audio_io import SUPPORTED_FORMATS, stamped_filename, to_mono_float, write_audio
from mic_recorder import MicDevice, MicrophoneRecorder
from recorder import RecorderError


@dataclass
class ExtSettings:
    output_dir: Path = Path("mic_segments")
    buffer_seconds: float = 10.0
    noise_gate_db: float = -40.0
    pre_roll_ms: int = 200  # мс до открытия gate — сохранить «хвост» до речи
    post_roll_ms: int = 300  # мс после тишины — ещё писать, не резать конец фразы
    voice_boost: bool = True
    voice_boost_db: float = 6.0
    audio_format: str = "wav"
    chunk_size: int = 1024


@dataclass
class LevelInfo:
    rms: float
    peak: float
    db: float
    gated: bool
    buffer_fill: float


class VoicePresenceEQ:
    """Подъём «голосовой» полосы (300 Гц–3.4 кГц) + ослабление гула <80 Гц."""

    def __init__(self, sample_rate: int, gain_db: float = 6.0):
        self._sample_rate = sample_rate
        self._gain = float(10 ** (gain_db / 20.0))

    def process(self, samples: np.ndarray) -> np.ndarray:
        if samples.size < 8:
            return samples
        spectrum = np.fft.rfft(samples.astype(np.float32, copy=False))
        freqs = np.fft.rfftfreq(samples.size, d=1.0 / self._sample_rate)
        spectrum[(freqs >= 300.0) & (freqs <= 3400.0)] *= self._gain
        spectrum[freqs < 80.0] *= 0.35
        out = np.fft.irfft(spectrum, n=samples.size)
        return np.clip(out, -1.0, 1.0).astype(np.float32)


class NoiseGateWithPadding:
    """
    Noise gate с запасом до/после речи.
    - pre_roll: кольцевой буфер тишины; при открытии gate отдаётся вместе с текущим чанком
    - post_roll: после падения ниже порога ещё hold_ms пишем в выход
    """

    def __init__(self, sample_rate: int, threshold_db: float, pre_roll_ms: int, post_roll_ms: int):
        self.threshold_db = threshold_db
        self._pre_max = max(0, int(sample_rate * max(0, pre_roll_ms) / 1000.0))
        self._post_max = max(0, int(sample_rate * max(0, post_roll_ms) / 1000.0))
        self._pre: deque[np.ndarray] = deque()
        self._pre_samples = 0
        self._open = False
        self._post_left = 0

    @staticmethod
    def _n_samples(chunk: np.ndarray) -> int:
        return int(chunk.shape[0])

    def process(self, chunk: np.ndarray, db: float) -> tuple[Optional[np.ndarray], bool]:
        """
        Возвращает (audio_to_keep | None, is_gated).
        chunk: (n,) или (n, ch). is_gated=True — чанк не пошёл в запись.
        """
        above = db >= self.threshold_db
        n = self._n_samples(chunk)

        if above:
            parts: list[np.ndarray] = []
            if not self._open and self._pre_samples > 0:
                parts.extend(self._pre)
            parts.append(chunk)
            self._open = True
            self._post_left = self._post_max
            self._pre.clear()
            self._pre_samples = 0
            return np.concatenate(parts, axis=0), False

        if self._open and self._post_left > 0:
            take = min(n, self._post_left)
            self._post_left -= take
            kept = chunk[:take]
            if self._post_left <= 0:
                self._open = False
                rest = chunk[take:]
                if self._n_samples(rest) > 0:
                    self._push_pre(rest)
            return kept, False

        self._open = False
        self._push_pre(chunk)
        return None, True

    def _push_pre(self, chunk: np.ndarray) -> None:
        if self._pre_max <= 0:
            return
        self._pre.append(chunk)
        self._pre_samples += self._n_samples(chunk)
        while self._pre_samples > self._pre_max and self._pre:
            overflow = self._pre_samples - self._pre_max
            first = self._pre.popleft()
            first_n = self._n_samples(first)
            if first_n <= overflow:
                self._pre_samples -= first_n
            else:
                self._pre.appendleft(first[overflow:])
                self._pre_samples -= overflow


class SegmentedMicRecorder:
    """Слушает микрофон, копит только «не тишину» (с pre/post-roll), сохраняет сегменты."""

    def __init__(
        self,
        settings: Optional[ExtSettings] = None,
        on_level: Optional[Callable[[LevelInfo], None]] = None,
        on_saved: Optional[Callable[[Path], None]] = None,
    ):
        self.settings = settings or ExtSettings()
        self.on_level = on_level
        self.on_saved = on_saved

        self._audio = pyaudio.PyAudio()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stream = None
        self._recording = False
        self._stop_requested = False
        self._device: Optional[MicDevice] = None
        self._last_error: Optional[BaseException] = None
        self._eq: Optional[VoicePresenceEQ] = None
        self._gate: Optional[NoiseGateWithPadding] = None
        self._chunks: list[np.ndarray] = []
        self._buffer_samples = 0
        self._saved_count = 0

    def close(self) -> None:
        self.stop()
        if self._audio is not None:
            self._audio.terminate()
            self._audio = None

    def __enter__(self) -> "SegmentedMicRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def device(self) -> Optional[MicDevice]:
        return self._device

    @property
    def last_error(self) -> Optional[BaseException]:
        return self._last_error

    @property
    def buffer_fill(self) -> float:
        need = max(1, int(self.settings.buffer_seconds * (self._device.sample_rate if self._device else 44100)))
        with self._lock:
            return min(1.0, self._buffer_samples / need)

    def list_devices(self) -> list[MicDevice]:
        devices: list[MicDevice] = []
        for index in range(self._audio.get_device_count()):
            info = self._audio.get_device_info_by_index(index)
            if MicrophoneRecorder._is_microphone(info):
                devices.append(MicrophoneRecorder._to_device(info))
        return devices

    def get_default_device(self) -> MicDevice:
        try:
            info = self._audio.get_default_input_device_info()
        except OSError as exc:
            raise RecorderError("Нет устройства ввода по умолчанию.") from exc
        if MicrophoneRecorder._is_microphone(info):
            return MicrophoneRecorder._to_device(info)
        devices = self.list_devices()
        if not devices:
            raise RecorderError("Микрофоны не найдены.")
        return devices[0]

    def resolve_device(self, device_index: Optional[int] = None) -> MicDevice:
        if device_index is None:
            return self.get_default_device()
        for device in self.list_devices():
            if device.index == device_index:
                return device
        raise RecorderError(f"Микрофон с индексом {device_index} не найден.")

    def start(self, device_index: Optional[int] = None) -> MicDevice:
        fmt = self.settings.audio_format.lower()
        if fmt not in SUPPORTED_FORMATS:
            raise RecorderError(f"Неизвестный формат: {fmt}. Доступно: {', '.join(SUPPORTED_FORMATS)}")
        if self.settings.buffer_seconds <= 0:
            raise RecorderError("buffer_seconds должен быть > 0")

        with self._lock:
            if self._recording:
                raise RecorderError("Запись уже идёт.")

            device = self.resolve_device(device_index)
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)

            self._device = device
            self._recording = True
            self._stop_requested = False
            self._last_error = None
            self._chunks = []
            self._buffer_samples = 0
            self._saved_count = 0
            self._eq = (
                VoicePresenceEQ(device.sample_rate, self.settings.voice_boost_db)
                if self.settings.voice_boost
                else None
            )
            self._gate = NoiseGateWithPadding(
                sample_rate=device.sample_rate,
                threshold_db=self.settings.noise_gate_db,
                pre_roll_ms=self.settings.pre_roll_ms,
                post_roll_ms=self.settings.post_roll_ms,
            )

            self._thread = threading.Thread(
                target=self._capture_loop,
                args=(device,),
                daemon=True,
                name="mic-segment-recorder",
            )
            self._thread.start()
            return device

    def stop(self, flush: bool = True) -> list[Path]:
        with self._lock:
            thread = self._thread
            if not self._recording and thread is None:
                return []
            self._stop_requested = True

        saved: list[Path] = []
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
            if thread.is_alive():
                self._force_close_stream()
                thread.join(timeout=3.0)

        if flush:
            path = self._flush_buffer(force=True)
            if path is not None:
                saved.append(path)

        with self._lock:
            self._thread = None
            self._recording = False
            return saved

    def _force_close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop_stream()
        except Exception:  # noqa: BLE001
            pass
        try:
            stream.close()
        except Exception:  # noqa: BLE001
            pass

    def _capture_loop(self, device: MicDevice) -> None:
        try:
            stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=device.channels,
                rate=device.sample_rate,
                input=True,
                frames_per_buffer=self.settings.chunk_size,
                input_device_index=device.index,
            )
            self._stream = stream
            need = int(self.settings.buffer_seconds * device.sample_rate)
            assert self._gate is not None

            while not self._stop_requested:
                try:
                    raw = stream.read(self.settings.chunk_size, exception_on_overflow=False)
                except Exception:  # noqa: BLE001
                    break

                mono = to_mono_float(raw, device.channels)
                if self._eq is not None:
                    mono = self._eq.process(mono)

                rms = float(np.sqrt(np.mean(np.square(mono))) + 1e-12)
                peak = float(np.max(np.abs(mono))) if mono.size else 0.0
                db = float(20.0 * np.log10(rms))
                kept, gated = self._gate.process(mono, db)

                if kept is not None:
                    with self._lock:
                        self._chunks.append(kept)
                        self._buffer_samples += int(kept.size)
                        fill = min(1.0, self._buffer_samples / need)
                        ready = self._buffer_samples >= need
                    if ready:
                        self._flush_buffer(force=False)
                        fill = self.buffer_fill
                else:
                    fill = self.buffer_fill

                if self.on_level is not None:
                    try:
                        self.on_level(
                            LevelInfo(rms=rms, peak=peak, db=db, gated=gated, buffer_fill=fill)
                        )
                    except Exception:  # noqa: BLE001
                        pass

        except Exception as exc:  # noqa: BLE001
            self._last_error = exc
        finally:
            self._force_close_stream()
            with self._lock:
                self._recording = False
                self._stop_requested = False

    def _flush_buffer(self, force: bool) -> Optional[Path]:
        with self._lock:
            if self._device is None:
                return None
            need = int(self.settings.buffer_seconds * self._device.sample_rate)
            if self._buffer_samples == 0:
                return None
            if not force and self._buffer_samples < need:
                return None

            full = np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.float32)
            if force and self._buffer_samples < need:
                audio = full
                self._chunks = []
                self._buffer_samples = 0
            else:
                audio = full[:need]
                rest = full[need:]
                if rest.size:
                    self._chunks = [rest]
                    self._buffer_samples = int(rest.size)
                else:
                    self._chunks = []
                    self._buffer_samples = 0

            device = self._device
            fmt = self.settings.audio_format.lower()
            out_dir = self.settings.output_dir
            self._saved_count += 1
            count = self._saved_count

        path = out_dir / stamped_filename("mic", fmt, seq=count)
        try:
            write_audio(path, audio, device.sample_rate, fmt)
        except Exception as exc:  # noqa: BLE001
            self._last_error = exc
            return None

        if self.on_saved is not None:
            try:
                self.on_saved(path)
            except Exception:  # noqa: BLE001
                pass
        return path
