"""
Запись конференции: системный звук (WASAPI loopback) + микрофон.

Режимы:
- continuous — один большой файл
- segments — нарезка в папку по buffer_seconds

Раскладка:
- stereo — L = система, R = микрофон (удобно для постобработки)
- mix — моно-микс
"""

from __future__ import annotations

import queue
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional

import numpy as np
import pyaudiowpatch as pyaudio

from audio_io import (
    SUPPORTED_FORMATS,
    resample_mono,
    stamped_filename,
    to_mono_float,
    write_audio,
)
from mic_recorder import MicDevice, MicrophoneRecorder
from mic_recorder_ext import NoiseGateWithPadding, VoicePresenceEQ
from recorder import LoopbackDevice, RecorderError

MixMode = Literal["stereo", "mix"]
WriteMode = Literal["continuous", "segments"]


@dataclass
class ConferenceSettings:
    output_dir: Path = Path("conference_captures")
    continuous_path: Path = Path("conference_captures") / "conference.wav"
    write_mode: WriteMode = "continuous"
    buffer_seconds: float = 30.0
    mix_mode: MixMode = "stereo"
    audio_format: str = "wav"
    chunk_size: int = 1024
    # gate применяется к миксу/микрофону только в segments (опционально)
    use_gate: bool = False
    noise_gate_db: float = -45.0
    pre_roll_ms: int = 250
    post_roll_ms: int = 400
    voice_boost_mic: bool = True
    voice_boost_db: float = 6.0
    system_gain: float = 1.0
    mic_gain: float = 1.0


@dataclass
class ConferenceLevel:
    system_db: float
    mic_db: float
    buffer_fill: float
    gated: bool


class ConferenceRecorder:
    def __init__(
        self,
        settings: Optional[ConferenceSettings] = None,
        on_level: Optional[Callable[[ConferenceLevel], None]] = None,
        on_saved: Optional[Callable[[Path], None]] = None,
    ):
        self.settings = settings or ConferenceSettings()
        self.on_level = on_level
        self.on_saved = on_saved

        self._audio = pyaudio.PyAudio()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._sys_stream = None
        self._mic_stream = None
        self._recording = False
        self._stop_requested = False
        self._last_error: Optional[BaseException] = None
        self._sys_device: Optional[LoopbackDevice] = None
        self._mic_device: Optional[MicDevice] = None
        self._chunks: list[np.ndarray] = []
        self._buffer_samples = 0
        self._saved_count = 0
        self._wave_file = None
        self._sample_rate = 48000
        self._channels = 2
        self._eq: Optional[VoicePresenceEQ] = None
        self._gate: Optional[NoiseGateWithPadding] = None
        self._sys_q: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._mic_q: queue.Queue[bytes] = queue.Queue(maxsize=64)

    def close(self) -> None:
        self.stop()
        if self._audio is not None:
            self._audio.terminate()
            self._audio = None

    def __enter__(self) -> "ConferenceRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def last_error(self) -> Optional[BaseException]:
        return self._last_error

    @property
    def buffer_fill(self) -> float:
        if self.settings.write_mode != "segments":
            return 0.0
        need = max(1, int(self.settings.buffer_seconds * self._sample_rate))
        with self._lock:
            return min(1.0, self._buffer_samples / need)

    def list_loopbacks(self) -> list[LoopbackDevice]:
        return [
            LoopbackDevice(
                index=int(info["index"]),
                name=str(info["name"]),
                channels=int(info["maxInputChannels"]),
                sample_rate=int(info["defaultSampleRate"]),
            )
            for info in self._audio.get_loopback_device_info_generator()
        ]

    def get_default_loopback(self) -> LoopbackDevice:
        try:
            info = self._audio.get_default_wasapi_loopback()
        except OSError as exc:
            raise RecorderError("WASAPI недоступен.") from exc
        except LookupError as exc:
            raise RecorderError("Default loopback не найден.") from exc
        return LoopbackDevice(
            index=int(info["index"]),
            name=str(info["name"]),
            channels=int(info["maxInputChannels"]),
            sample_rate=int(info["defaultSampleRate"]),
        )

    def list_mics(self) -> list[MicDevice]:
        devices: list[MicDevice] = []
        for index in range(self._audio.get_device_count()):
            info = self._audio.get_device_info_by_index(index)
            if MicrophoneRecorder._is_microphone(info):
                devices.append(MicrophoneRecorder._to_device(info))
        return devices

    def get_default_mic(self) -> MicDevice:
        try:
            info = self._audio.get_default_input_device_info()
        except OSError as exc:
            raise RecorderError("Нет микрофона по умолчанию.") from exc
        if MicrophoneRecorder._is_microphone(info):
            return MicrophoneRecorder._to_device(info)
        mics = self.list_mics()
        if not mics:
            raise RecorderError("Микрофоны не найдены.")
        return mics[0]

    def start(
        self,
        loopback_index: Optional[int] = None,
        mic_index: Optional[int] = None,
    ) -> tuple[LoopbackDevice, MicDevice]:
        fmt = self.settings.audio_format.lower()
        if fmt not in SUPPORTED_FORMATS:
            raise RecorderError(f"Формат {fmt} не поддержан")
        if self.settings.write_mode == "segments" and self.settings.buffer_seconds <= 0:
            raise RecorderError("buffer_seconds должен быть > 0")

        with self._lock:
            if self._recording:
                raise RecorderError("Запись уже идёт.")

            sys_dev = self._resolve_loopback(loopback_index)
            mic_dev = self._resolve_mic(mic_index)
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)

            self._sys_device = sys_dev
            self._mic_device = mic_dev
            self._sample_rate = sys_dev.sample_rate
            self._channels = 2 if self.settings.mix_mode == "stereo" else 1
            self._recording = True
            self._stop_requested = False
            self._last_error = None
            self._chunks = []
            self._buffer_samples = 0
            self._saved_count = 0
            self._eq = (
                VoicePresenceEQ(self._sample_rate, self.settings.voice_boost_db)
                if self.settings.voice_boost_mic
                else None
            )
            self._gate = None
            if self.settings.write_mode == "segments" and self.settings.use_gate:
                self._gate = NoiseGateWithPadding(
                    sample_rate=self._sample_rate,
                    threshold_db=self.settings.noise_gate_db,
                    pre_roll_ms=self.settings.pre_roll_ms,
                    post_roll_ms=self.settings.post_roll_ms,
                )

            if self.settings.write_mode == "continuous":
                path = Path(self.settings.continuous_path)
                if path.suffix.lower().lstrip(".") != fmt:
                    path = path.with_suffix(f".{fmt}")
                path.parent.mkdir(parents=True, exist_ok=True)
                self.settings.continuous_path = path
                self._open_continuous_writer(path, fmt)

            # PortAudio/WASAPI: открытие stream надёжнее из вызывающего потока (GUI/main).
            self._sys_q = queue.Queue(maxsize=64)
            self._mic_q = queue.Queue(maxsize=64)
            self._open_streams(sys_dev, mic_dev)

            self._thread = threading.Thread(
                target=self._process_loop,
                args=(sys_dev, mic_dev),
                daemon=True,
                name="conference-recorder",
            )
            self._thread.start()
            return sys_dev, mic_dev

    def stop(self) -> list[Path]:
        with self._lock:
            thread = self._thread
            if not self._recording and thread is None:
                return []
            self._stop_requested = True

        # Стримы открыты в вызывающем потоке — закрываем здесь после остановки process loop.
        if thread is not None and thread.is_alive():
            thread.join(timeout=5.0)
        self._force_close_streams()

        saved: list[Path] = []
        if self.settings.write_mode == "segments":
            path = self._flush_segments(force=True)
            if path is not None:
                saved.append(path)
        else:
            path = self._close_continuous_writer()
            if path is not None:
                saved.append(path)
                if self.on_saved:
                    try:
                        self.on_saved(path)
                    except Exception:  # noqa: BLE001
                        pass

        with self._lock:
            self._thread = None
            self._recording = False
            return saved

    def _resolve_loopback(self, index: Optional[int]) -> LoopbackDevice:
        if index is None:
            return self.get_default_loopback()
        for d in self.list_loopbacks():
            if d.index == index:
                return d
        raise RecorderError(f"Loopback {index} не найден")

    def _resolve_mic(self, index: Optional[int]) -> MicDevice:
        if index is None:
            return self.get_default_mic()
        for d in self.list_mics():
            if d.index == index:
                return d
        raise RecorderError(f"Микрофон {index} не найден")

    def _open_continuous_writer(self, path: Path, fmt: str) -> None:
        if fmt == "wav":
            wf = wave.open(str(path), "wb")
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            self._wave_file = wf
        else:
            # для сжатых форматов копить в RAM-сегменты и писать при stop —
            # для длинных конференций лучше wav; иначе сегментный режим
            self._wave_file = None
            self._chunks = []
            self._buffer_samples = 0

    def _close_continuous_writer(self) -> Optional[Path]:
        path = Path(self.settings.continuous_path)
        with self._lock:
            wf = self._wave_file
            self._wave_file = None
        if wf is not None:
            try:
                wf.close()
            except Exception:  # noqa: BLE001
                pass
            return path if path.exists() else None

        # non-wav continuous: один файл из накопленного буфера
        with self._lock:
            if not self._chunks:
                return None
            audio = np.concatenate(self._chunks, axis=0)
            self._chunks = []
            self._buffer_samples = 0
        try:
            write_audio(path, audio, self._sample_rate, self.settings.audio_format)
            return path
        except Exception as exc:  # noqa: BLE001
            self._last_error = exc
            return None

    def _force_close_streams(self) -> None:
        with self._lock:
            streams = []
            for attr in ("_sys_stream", "_mic_stream"):
                stream = getattr(self, attr)
                setattr(self, attr, None)
                if stream is not None:
                    streams.append(stream)
        for stream in streams:
            try:
                stream.stop_stream()
            except Exception:  # noqa: BLE001
                pass
            try:
                stream.close()
            except Exception:  # noqa: BLE001
                pass

    def _open_streams(self, sys_dev: LoopbackDevice, mic_dev: MicDevice) -> None:
        def sys_cb(in_data, frame_count, time_info, status):  # noqa: ARG001
            if self._stop_requested:
                return (None, pyaudio.paComplete)
            try:
                self._sys_q.put_nowait(in_data)
            except queue.Full:
                pass
            return (in_data, pyaudio.paContinue)

        def mic_cb(in_data, frame_count, time_info, status):  # noqa: ARG001
            if self._stop_requested:
                return (None, pyaudio.paComplete)
            try:
                self._mic_q.put_nowait(in_data)
            except queue.Full:
                pass
            return (in_data, pyaudio.paContinue)

        self._sys_stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=sys_dev.channels,
            rate=sys_dev.sample_rate,
            input=True,
            frames_per_buffer=self.settings.chunk_size,
            input_device_index=sys_dev.index,
            stream_callback=sys_cb,
        )
        self._mic_stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=mic_dev.channels,
            rate=mic_dev.sample_rate,
            input=True,
            frames_per_buffer=self.settings.chunk_size,
            input_device_index=mic_dev.index,
            stream_callback=mic_cb,
        )
        self._sys_stream.start_stream()
        self._mic_stream.start_stream()

    def _process_loop(self, sys_dev: LoopbackDevice, mic_dev: MicDevice) -> None:
        # Два блокирующих InputStream на Windows часто взаимно зависают.
        # Callback + очереди — рабочий путь для loopback и mic одновременно.
        try:
            need = int(self.settings.buffer_seconds * self._sample_rate)

            while not self._stop_requested:
                try:
                    sys_raw = self._sys_q.get(timeout=0.25)
                except queue.Empty:
                    continue
                try:
                    mic_raw = self._mic_q.get(timeout=0.25)
                except queue.Empty:
                    continue

                sys_mono = to_mono_float(sys_raw, sys_dev.channels) * self.settings.system_gain
                mic_mono = to_mono_float(mic_raw, mic_dev.channels) * self.settings.mic_gain
                # подогнать длительность mic-чанка под sys (разные sample rate)
                target_n = sys_mono.size
                if mic_dev.sample_rate != self._sample_rate or mic_mono.size != target_n:
                    duration = sys_mono.size / float(sys_dev.sample_rate)
                    target_mic = max(1, int(round(duration * mic_dev.sample_rate)))
                    if mic_mono.size < target_mic:
                        mic_mono = np.pad(mic_mono, (0, target_mic - mic_mono.size))
                    elif mic_mono.size > target_mic:
                        mic_mono = mic_mono[:target_mic]
                    mic_mono = resample_mono(mic_mono, mic_dev.sample_rate, self._sample_rate)
                    if mic_mono.size < target_n:
                        mic_mono = np.pad(mic_mono, (0, target_n - mic_mono.size))
                    else:
                        mic_mono = mic_mono[:target_n]

                if self._eq is not None:
                    mic_mono = self._eq.process(mic_mono)

                if self.settings.mix_mode == "stereo":
                    frame = np.column_stack([sys_mono, mic_mono]).astype(np.float32)
                else:
                    frame = np.clip(0.5 * sys_mono + 0.5 * mic_mono, -1.0, 1.0).astype(np.float32)

                sys_db = self._db(sys_mono)
                mic_db = self._db(mic_mono)
                gate_db = max(sys_db, mic_db)
                gated = False

                if self.settings.write_mode == "segments" and self._gate is not None:
                    kept, gated = self._gate.process(frame, gate_db)
                    if kept is None:
                        self._emit_level(sys_db, mic_db, gated=True)
                        continue
                    frame = kept

                self._write_frame(frame, need)
                self._emit_level(sys_db, mic_db, gated=gated)

        except Exception as exc:  # noqa: BLE001
            self._last_error = exc
        finally:
            with self._lock:
                self._recording = False

    def _write_frame(self, frame: np.ndarray, need: int) -> None:
        if self.settings.write_mode == "continuous" and self._wave_file is not None:
            pcm = np.clip(frame, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype(np.int16)
            with self._lock:
                if self._wave_file is not None:
                    self._wave_file.writeframes(pcm.tobytes())
            return

        # segments или continuous non-wav
        with self._lock:
            self._chunks.append(frame)
            self._buffer_samples += int(frame.shape[0])
            ready = (
                self.settings.write_mode == "segments"
                and self._buffer_samples >= need
            )
        if ready:
            self._flush_segments(force=False)

    def _flush_segments(self, force: bool) -> Optional[Path]:
        with self._lock:
            need = int(self.settings.buffer_seconds * self._sample_rate)
            if self._buffer_samples == 0:
                return None
            if self.settings.write_mode == "segments" and (not force) and self._buffer_samples < need:
                return None
            if self.settings.write_mode != "segments" and not force:
                return None

            full = np.concatenate(self._chunks, axis=0)
            if force and (
                self.settings.write_mode != "segments" or self._buffer_samples < need
            ):
                audio = full
                self._chunks = []
                self._buffer_samples = 0
            else:
                audio = full[:need]
                rest = full[need:]
                if rest.size:
                    self._chunks = [rest]
                    self._buffer_samples = int(rest.shape[0])
                else:
                    self._chunks = []
                    self._buffer_samples = 0

            fmt = self.settings.audio_format.lower()
            out_dir = self.settings.output_dir
            self._saved_count += 1
            count = self._saved_count

        path = out_dir / stamped_filename("conf", fmt, seq=count)
        try:
            write_audio(path, audio, self._sample_rate, fmt)
        except Exception as exc:  # noqa: BLE001
            self._last_error = exc
            return None
        if self.on_saved:
            try:
                self.on_saved(path)
            except Exception:  # noqa: BLE001
                pass
        return path

    def _emit_level(self, system_db: float, mic_db: float, gated: bool) -> None:
        if self.on_level is None:
            return
        try:
            self.on_level(
                ConferenceLevel(
                    system_db=system_db,
                    mic_db=mic_db,
                    buffer_fill=self.buffer_fill,
                    gated=gated,
                )
            )
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _db(samples: np.ndarray) -> float:
        rms = float(np.sqrt(np.mean(np.square(samples))) + 1e-12)
        return float(20.0 * np.log10(rms))
