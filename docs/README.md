# Документация

Описания сценариев и готовые примеры команд.

## Содержание

1. [Установка](01-install.md)
2. [Системный звук (WASAPI)](02-system-audio.md)
3. [Микрофон](03-microphone.md)
4. [Конференция: система + микрофон](04-conference.md)
5. [STT: локальные модели → текст → LLM](05-stt-gigaam.md)
6. [Старые прототипы](06-legacy-prototypes.md)

## Примеры

| Файл | О чём |
| --- | --- |
| [examples/system_audio.md](examples/system_audio.md) | Запись «что играет» |
| [examples/microphone.md](examples/microphone.md) | Микрофон и сегменты |
| [examples/conference.md](examples/conference.md) | Созвон в один файл / папку |
| [examples/stt_pipeline.md](examples/stt_pipeline.md) | Запись → распознавание → DeepSeek |

## Сценарий end-to-end

```text
conference_grab_ext / mic_grab_ext
        ↓  WAV / FLAC / …
stt_grab / stt_grab_gui   (GigaAM / Whisper / Vosk, CPU)
        ↓  текст
DeepSeek / другой LLM     (уточняющий промпт)
        ↓  итоговый текст
```

Подробно: [05-stt-gigaam.md](05-stt-gigaam.md) и [examples/stt_pipeline.md](examples/stt_pipeline.md).
