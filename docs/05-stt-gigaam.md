# STT: локальные модели → текст → LLM

Сценарий постобработки записей: аудиофайл → распознавание на CPU → при необходимости правка/саммари через DeepSeek (или другой OpenAI-совместимый API).

## Зачем это здесь

После `conference_grab_ext` / `mic_grab_ext` на диске лежат WAV (или сжатые форматы). Этот контур превращает их в текст **локально** (модель на вашей машине), без отправки аудио в облако. В облако (по желанию) уходит уже только текст + ваш промпт.

```text
[запись] WAV/FLAC/…
    ↓
stt_catalog → gigaam | whisper | vosk   (CPU, 16 kHz mono)
    ↓
текст расшифровки
    ↓  (опционально)
llm_rewrite  (DeepSeek API / другой endpoint)
    ↓
итоговый текст / саммари / протокол
```

## Модели

| ID | Движок | Когда брать |
| --- | --- | --- |
| `gigaam-v3` | ONNX RNNT | русский, качество |
| `whisper-small` | faster-whisper | универсальный разбор, много языков |
| `vosk-small-ru` | Vosk | слабый ПК, русский, меньше места |

Скачивание кладёт файлы в `models/<id>/`. Установленные модели появляются в списке GUI.

## Файлы

| Файл | Роль |
| --- | --- |
| `stt_catalog.py` | Каталог, скачивание, выбор движка |
| `stt_base.py` | Общий контракт, аудио 16 kHz, пунктуация Silero |
| `gigaam_stt.py` | GigaAM-v3 ONNX |
| `whisper_stt.py` | Whisper small |
| `vosk_stt.py` | Vosk small-ru |
| `stt_download_model.py` | Скачивание из консоли |
| `stt_grab.py` | CLI |
| `stt_grab_gui.py` | GUI: файл → текст → LLM |
| `llm_rewrite.py` | HTTP Chat Completions (DeepSeek и совместимые) |

## Подготовка

```bash
pip install -r requirements.txt
python stt_download_model.py gigaam-v3
```

## CLI

```bash
# GigaAM по умолчанию
python stt_grab.py path\to\recording.wav

# другая модель
python stt_grab.py recording.wav --model whisper-small
python stt_grab.py recording.wav --model vosk-small-ru -o out.txt

# без Silero-пунктуации
python stt_grab.py recording.wav --no-punct

# сразу переработать через DeepSeek
python stt_grab.py recording.wav --rewrite-prompt "Сделай краткий протокол встречи" --api-key sk-...
```

Переменные окружения: `DEEPSEEK_API_KEY` (или `OPENAI_API_KEY` как запасной вариант для совместимых шлюзов).

Флаги LLM:

- `--api-base` — по умолчанию `https://api.deepseek.com`
- `--api-model` — `deepseek-chat` / `deepseek-flash` / …

## GUI

```bash
python stt_grab_gui.py
```

1. Выбрать аудио (или «Папка записей…» → `conference_captures`).
2. В блоке модели выбрать уже скачанную или нажать кнопку скачивания (GigaAM / Whisper / Vosk).
3. **Распознать** — текст появится в верхнем поле.
4. В блоке LLM: API key, base URL, model, уточняющий промпт.
5. **Отправить в LLM** — результат в нижнем поле.

Ключ в интерфейсе не сохраняется на диск автоматически; удобно держать его в `DEEPSEEK_API_KEY`.

## Как устроено распознавание

- Аудио приводится к **16 kHz mono** (записи 44.1/48 kHz stereo поддерживаются).
- Инференс на **CPU**. GigaAM режет длинные файлы на куски ~20 с.
- Опциональная пунктуация — Silero TE (русский; скачивается через `torch.hub` при первом включении). Для Whisper на других языках её лучше выключить.

## Типовые промпты для LLM

- «Исправь ошибки распознавания и расставь знаки препинания.»
- «Сделай краткий протокол: участники, решения, задачи.»
- «Выдели action items списком.»
- «Переведи расшифровку на английский, сохрани имена.»

## Ограничения

- Качество зависит от микрофона, шума и того, mono/stereo ли запись.
- Для stereo-конференции (L=система, R=mic) модель слышит **микс каналов** после сведения в mono — оба голоса в одной расшифровке.
- Первый запуск с пунктуацией может скачать Silero (~десятки MB).
- API-ключ и текст промпта уходят на выбранный LLM-endpoint — это уже не локальный контур.

Примеры команд: [examples/stt_pipeline.md](examples/stt_pipeline.md).
