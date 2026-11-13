"""Каталог локальных STT-моделей: список, скачивание, фабрика распознавателя."""

from __future__ import annotations

import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from stt_base import SttError, SttRecognizer

MODELS_ROOT = Path("models")
ProgressMsgFn = Callable[[float, str], None]

GIGAAM_REPO = "Dimitrius174/gigaam-v3-onnx-ru"
GIGAAM_FILES = (
    "model/gigaam_v3_rnnt_encoder.onnx",
    "model/gigaam_v3_rnnt_decoder.onnx",
    "model/gigaam_v3_rnnt_joint.onnx",
    "model/gigaam_v3_rnnt_tokens.txt",
)
WHISPER_REPO = "Systran/faster-whisper-small"
VOSK_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
VOSK_ZIP_ROOT = "vosk-model-small-ru-0.22"


@dataclass(frozen=True)
class SttModelSpec:
    id: str
    title: str
    button: str
    hint: str
    directory: Path
    marker: str
    engine: str


CATALOG: tuple[SttModelSpec, ...] = (
    SttModelSpec(
        id="gigaam-v3",
        title="GigaAM-v3 — русский",
        button="GigaAM-v3 (русский)",
        hint="Качество на русском, ONNX CPU",
        directory=MODELS_ROOT / "gigaam-v3",
        marker="gigaam_v3_rnnt_encoder.onnx",
        engine="gigaam",
    ),
    SttModelSpec(
        id="whisper-small",
        title="Whisper small — универсальный",
        button="Whisper small (универсальный)",
        hint="Много языков, heavier CPU",
        directory=MODELS_ROOT / "whisper-small",
        marker="model.bin",
        engine="whisper",
    ),
    SttModelSpec(
        id="vosk-small-ru",
        title="Vosk small-ru — слабый ПК",
        button="Vosk small-ru (слабый ПК)",
        hint="Лёгкая русская модель",
        directory=MODELS_ROOT / "vosk-small-ru",
        marker="am/final.mdl",
        engine="vosk",
    ),
)

MODEL_IDS: tuple[str, ...] = tuple(spec.id for spec in CATALOG)


def all_models() -> tuple[SttModelSpec, ...]:
    return CATALOG


def get_spec(model_id: str) -> SttModelSpec:
    for spec in CATALOG:
        if spec.id == model_id:
            return spec
    known = ", ".join(MODEL_IDS)
    raise SttError(f"Неизвестная модель: {model_id}. Доступны: {known}")


def is_installed(spec: SttModelSpec) -> bool:
    return (spec.directory / spec.marker).is_file()


def list_installed() -> list[SttModelSpec]:
    return [spec for spec in CATALOG if is_installed(spec)]


def open_recognizer(model_id: str) -> SttRecognizer:
    spec = get_spec(model_id)
    if not is_installed(spec):
        raise SttError(
            f"Модель не скачана: {spec.title}\n"
            f"Скачайте в GUI или: python stt_download_model.py {spec.id}"
        )
    if spec.engine == "gigaam":
        from gigaam_stt import GigaAMRecognizer

        return GigaAMRecognizer(spec.directory)
    if spec.engine == "whisper":
        from whisper_stt import WhisperRecognizer

        return WhisperRecognizer(spec.directory)
    if spec.engine == "vosk":
        from vosk_stt import VoskRecognizer

        return VoskRecognizer(spec.directory)
    raise SttError(f"Нет движка для {spec.id}")


def download(model_id: str, on_progress: Optional[ProgressMsgFn] = None) -> Path:
    spec = get_spec(model_id)
    spec.directory.mkdir(parents=True, exist_ok=True)
    if spec.engine == "gigaam":
        _download_gigaam(spec, on_progress)
    elif spec.engine == "whisper":
        _download_whisper(spec, on_progress)
    elif spec.engine == "vosk":
        _download_vosk(spec, on_progress)
    else:
        raise SttError(f"Нет загрузчика для {spec.id}")
    if not is_installed(spec):
        raise SttError(f"После скачивания нет файла {spec.marker} в {spec.directory}")
    _report(on_progress, 1.0, f"Готово: {spec.title}")
    return spec.directory


def _report(on_progress: Optional[ProgressMsgFn], frac: float, message: str) -> None:
    if on_progress is not None:
        on_progress(max(0.0, min(1.0, frac)), message)


def _download_gigaam(spec: SttModelSpec, on_progress: Optional[ProgressMsgFn]) -> None:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SttError("Нужен пакет huggingface_hub: pip install huggingface_hub") from exc

    cache = MODELS_ROOT / "_hf_cache_gigaam"
    total = len(GIGAAM_FILES)
    for index, rel in enumerate(GIGAAM_FILES):
        _report(on_progress, index / total, f"GigaAM: {Path(rel).name}")
        path = hf_hub_download(repo_id=GIGAAM_REPO, filename=rel, local_dir=str(cache))
        target = spec.directory / Path(rel).name
        target.write_bytes(Path(path).read_bytes())
        _report(on_progress, (index + 1) / total, f"GigaAM: {target.name}")


def _download_whisper(spec: SttModelSpec, on_progress: Optional[ProgressMsgFn]) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SttError("Нужен пакет huggingface_hub: pip install huggingface_hub") from exc

    _report(on_progress, 0.05, "Whisper small: скачивание (несколько минут)…")
    snapshot_download(repo_id=WHISPER_REPO, local_dir=str(spec.directory))
    _report(on_progress, 0.95, "Whisper small: файлы на месте")


def _download_vosk(spec: SttModelSpec, on_progress: Optional[ProgressMsgFn]) -> None:
    tmp = MODELS_ROOT / "_tmp_vosk"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    zip_path = tmp / "vosk.zip"
    _report(on_progress, 0.02, "Vosk: скачивание архива…")
    _download_file(VOSK_URL, zip_path, on_progress, scale=0.75)
    _report(on_progress, 0.8, "Vosk: распаковка…")
    extract_root = tmp / "extract"
    extract_root.mkdir()
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_root)
    src = extract_root / VOSK_ZIP_ROOT
    if not src.is_dir():
        dirs = [p for p in extract_root.iterdir() if p.is_dir()]
        if len(dirs) != 1:
            raise SttError("В архиве Vosk не найдена папка модели")
        src = dirs[0]
    if spec.directory.exists():
        shutil.rmtree(spec.directory)
    shutil.move(str(src), str(spec.directory))
    shutil.rmtree(tmp, ignore_errors=True)
    _report(on_progress, 0.95, "Vosk: модель распакована")


def _download_file(
    url: str,
    dest: Path,
    on_progress: Optional[ProgressMsgFn],
    scale: float,
) -> None:
    # timeout на urlopen действует и на каждое чтение. Медленный сервер
    # (alphacephei) легко молчит дольше 120 с — отсюда "The read operation timed out".
    last_error: Exception | None = None
    for attempt in range(1, 4):
        request = urllib.request.Request(url, headers={"User-Agent": "py-system-sound-grabber"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                with dest.open("wb") as handle:
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        if total:
                            _report(
                                on_progress,
                                scale * done / total,
                                f"Vosk: {done // (1024 * 1024)} / {total // (1024 * 1024)} МБ",
                            )
            return
        except Exception as exc:  # noqa: BLE001 — сеть, таймаут, обрыв
            last_error = exc
            dest.unlink(missing_ok=True)
            _report(on_progress, 0.02, f"Vosk: повтор {attempt}/3 после обрыва…")
    raise SttError(
        "Не удалось скачать Vosk: сервер долго не отвечал "
        f"({last_error}). Нажмите кнопку ещё раз."
    ) from last_error
