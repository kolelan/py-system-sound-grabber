# Установка

## Требования

- Windows 10/11
- Python 3.10+ (проверено на 3.11)
- Для записи: аудиоустройства Windows (WASAPI)
- Для STT: диск под выбранные модели (GigaAM ~310 MB, Whisper small ~500 MB, Vosk small-ru ~45 MB) + PyTorch/torchaudio для GigaAM и Silero

## Зависимости проекта

```bash
pip install -r requirements.txt
```

Состав `requirements.txt`:

- запись: `PyAudioWPatch`, `numpy`, `soundfile`
- STT: `onnxruntime`, `torch`, `torchaudio`, `pandas`, `huggingface_hub`, `faster-whisper`, `vosk`

`tkinter` обычно уже есть в установке Python на Windows.

## Модели распознавания

Веса не хранятся в репозитории. В GUI (`stt_grab_gui.py`) их можно скачать кнопками, либо из консоли:

```bash
python stt_download_model.py --list
python stt_download_model.py gigaam-v3
python stt_download_model.py whisper-small
python stt_download_model.py vosk-small-ru
```

| ID | Куда | Зачем |
| --- | --- | --- |
| `gigaam-v3` | `models/gigaam-v3/` | русский, качество (ONNX) |
| `whisper-small` | `models/whisper-small/` | универсальный, много языков |
| `vosk-small-ru` | `models/vosk-small-ru/` | лёгкая русская модель |

Каталог `models/` в `.gitignore`. GigaAM: [Dimitrius174/gigaam-v3-onnx-ru](https://huggingface.co/Dimitrius174/gigaam-v3-onnx-ru). Whisper: `Systran/faster-whisper-small`. Vosk: `vosk-model-small-ru-0.22`.

## Ключ LLM (опционально)

Для доработки текста после STT:

- переменная окружения `DEEPSEEK_API_KEY`, или
- поле API key в `stt_grab_gui.py`, или
- флаг `--api-key` в `stt_grab.py`

Base URL по умолчанию: `https://api.deepseek.com` (можно указать другой OpenAI-совместимый endpoint).
