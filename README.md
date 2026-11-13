# py-system-sound-grabber

Запись звука на Windows и локальное распознавание речи (GigaAM, Whisper, Vosk).

Типовой путь: **записали конференцию/микрофон → получили WAV → распознали текст → при желании доработали через DeepSeek**.

## Быстрый старт

```bash
pip install -r requirements.txt
```

| Задача | Команда | Документация |
| --- | --- | --- |
| Системный звук | `python grab_gui.py` | [docs/02-system-audio.md](docs/02-system-audio.md) |
| Микрофон | `python mic_grab_gui.py` | [docs/03-microphone.md](docs/03-microphone.md) |
| Конференция (система + mic) | `python conference_grab_ext.py` | [docs/04-conference.md](docs/04-conference.md) |
| Речь → текст | `python stt_grab_gui.py` | [docs/05-stt-gigaam.md](docs/05-stt-gigaam.md) |

Полный индекс: [docs/README.md](docs/README.md). Примеры команд: [docs/examples/](docs/examples/).

## Карта модулей

| Область | Ядро | CLI / GUI |
| --- | --- | --- |
| System loopback | `recorder.py` | `grab.py`, `grab_gui.py` |
| Микрофон | `mic_recorder.py` | `mic_grab.py`, `mic_grab_gui.py` |
| Микрофон (сегменты, gate) | `mic_recorder_ext.py` | `mic_grab_ext.py` |
| Конференция | `conference_recorder_ext.py` | `conference_grab_ext.py` |
| STT | `stt_catalog.py`, `gigaam_stt.py`, `whisper_stt.py`, `vosk_stt.py` | `stt_grab.py`, `stt_grab_gui.py` |
| LLM-правка текста | `llm_rewrite.py` | через STT GUI/CLI |

Общие утилиты: `audio_io.py`. Установка и зависимости: [docs/01-install.md](docs/01-install.md).

## Ограничения

- Ориентир — Windows (WASAPI).
- Неактивный loopback может «зависнуть» до стопа.
- DRM иногда даёт тишину в loopback.
- Веса моделей не в git — скачиваются отдельно (GigaAM / Whisper / Vosk).

## Лицензия

Учебный/прототипный проект. Записывайте и распознавайте только контент, на который у вас есть права.
