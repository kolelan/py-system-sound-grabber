"""Ядро записи системного звука через WASAPI loopback (Windows)."""

from __future__ import annotations

import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pyaudiowpatch as pyaudio


@dataclass(frozen=True)
class LoopbackDevice:
    index: int
    name: str
    channels: int
    sample_rate: int

    def __str__(self) -> str:
        return f"{self.index}: {self.name} ({self.channels} ch, {self.sample_rate} Hz)"


class RecorderError(Exception):
    """Ошибка инициализации или записи."""


class SystemAudioRecorder:
    """Пишет системный вывод (то, что играет сейчас) в WAV сразу на диск."""

    def __init__(self, chunk_size: int = 512, on_tick: Optional[Callable[[float], None]] = None):
        self.chunk_size = chunk_size
        self.on_tick = on_tick
        self._audio = pyaudio.PyAudio()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stream = None
        self._recording = False
        self._paused = False
        self._stop_requested = False
        self._started_at = 0.0
        self._paused_total = 0.0
        self._pause_started_at = 0.0
        self._device: Optional[LoopbackDevice] = None
        self._output_path: Optional[Path] = None
        self._last_error: Optional[BaseException] = None

    def close(self) -> None:
        self.stop()
        if self._audio is not None:
            self._audio.terminate()
            self._audio = None

    def __enter__(self) -> "SystemAudioRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def device(self) -> Optional[LoopbackDevice]:
        return self._device

    @property
    def output_path(self) -> Optional[Path]:
        return self._output_path

    @property
    def last_error(self) -> Optional[BaseException]:
        return self._last_error

    @property
    def elapsed(self) -> float:
        if self._started_at == 0.0:
            return 0.0
        now = time.monotonic()
        paused = self._paused_total
        if self._paused and self._pause_started_at:
            paused += now - self._pause_started_at
        return max(0.0, now - self._started_at - paused)

    def list_devices(self) -> list[LoopbackDevice]:
        try:
            return [
                self._to_device(info)
                for info in self._audio.get_loopback_device_info_generator()
            ]
        except Exception as exc:  # noqa: BLE001
            raise RecorderError(f"Не удалось получить список loopback-устройств: {exc}") from exc

    def get_default_device(self) -> LoopbackDevice:
        try:
            info = self._audio.get_default_wasapi_loopback()
        except OSError as exc:
            raise RecorderError("WASAPI недоступен на этой системе.") from exc
        except LookupError as exc:
            raise RecorderError(
                "Не найден loopback для устройства вывода по умолчанию. "
                "Проверьте: python -m pyaudiowpatch"
            ) from exc
        return self._to_device(info)

    def resolve_device(self, device_index: Optional[int] = None) -> LoopbackDevice:
        if device_index is None:
            return self.get_default_device()
        for device in self.list_devices():
            if device.index == device_index:
                return device
        raise RecorderError(f"Loopback-устройство с индексом {device_index} не найдено.")

    def start(
        self,
        output_path: str | Path,
        device_index: Optional[int] = None,
        duration: Optional[float] = None,
    ) -> LoopbackDevice:
        with self._lock:
            if self._recording:
                raise RecorderError("Запись уже идёт.")

            device = self.resolve_device(device_index)
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            self._device = device
            self._output_path = path
            self._recording = True
            self._paused = False
            self._stop_requested = False
            self._last_error = None
            self._started_at = time.monotonic()
            self._paused_total = 0.0
            self._pause_started_at = 0.0

            self._thread = threading.Thread(
                target=self._record_loop,
                args=(device, path, duration),
                daemon=True,
                name="wasapi-loopback-recorder",
            )
            self._thread.start()
            return device

    def pause(self) -> None:
        with self._lock:
            if not self._recording or self._paused:
                return
            self._paused = True
            self._pause_started_at = time.monotonic()

    def resume(self) -> None:
        with self._lock:
            if not self._recording or not self._paused:
                return
            self._paused_total += time.monotonic() - self._pause_started_at
            self._pause_started_at = 0.0
            self._paused = False

    def stop(self) -> Optional[Path]:
        with self._lock:
            thread = self._thread
            if not self._recording and thread is None:
                return self._output_path
            self._stop_requested = True

        if thread is not None and thread.is_alive():
            # Даём активному устройству дочитать текущий chunk (~10–20 мс).
            thread.join(timeout=1.0)
            if thread.is_alive():
                # Неактивный loopback может навсегда зависнуть в read — тогда закрываем stream.
                self._force_close_stream()
                thread.join(timeout=3.0)

        with self._lock:
            self._thread = None
            self._recording = False
            self._paused = False
            return self._output_path

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

    def _record_loop(
        self,
        device: LoopbackDevice,
        path: Path,
        duration: Optional[float],
    ) -> None:
        audio_format = pyaudio.paInt16
        sample_width = self._audio.get_sample_size(audio_format)
        wave_file = None

        try:
            wave_file = wave.open(str(path), "wb")
            wave_file.setnchannels(device.channels)
            wave_file.setsampwidth(sample_width)
            wave_file.setframerate(device.sample_rate)

            stream = self._audio.open(
                format=audio_format,
                channels=device.channels,
                rate=device.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=device.index,
            )
            self._stream = stream

            while not self._stop_requested:
                if duration is not None and self.elapsed >= duration:
                    break

                if self._paused:
                    time.sleep(0.05)
                    continue

                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                except Exception:  # noqa: BLE001 — stream закрыли из stop() при зависании
                    break

                wave_file.writeframes(data)

                if self.on_tick is not None:
                    try:
                        self.on_tick(self.elapsed)
                    except Exception:  # noqa: BLE001
                        pass

        except Exception as exc:  # noqa: BLE001
            self._last_error = exc
        finally:
            # Закрываем stream только из этого потока — так PortAudio стабильнее.
            stream = self._stream
            self._stream = None
            if stream is not None:
                try:
                    stream.stop_stream()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

            if wave_file is not None:
                try:
                    wave_file.close()
                except Exception:  # noqa: BLE001
                    pass

            with self._lock:
                self._recording = False
                self._paused = False
                self._stop_requested = False

    @staticmethod
    def _to_device(info: dict) -> LoopbackDevice:
        return LoopbackDevice(
            index=int(info["index"]),
            name=str(info["name"]),
            channels=int(info["maxInputChannels"]),
            sample_rate=int(info["defaultSampleRate"]),
        )
