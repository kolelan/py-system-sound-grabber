# py-system-sound-grabber

Запись звука на Windows: системный вывод, микрофон и конференция (система + mic). Сегменты и длинные файлы пишутся на диск без удержания всей сессии в RAM (для continuous WAV).

## Установка

```bash
pip install -r requirements.txt
```

Зависимости: [`PyAudioWPatch`](https://github.com/s0d3s/PyAudioWPatch), `numpy`, `soundfile`.

## Системный звук (WASAPI loopback)

| Файл | Роль |
| --- | --- |
| `recorder.py` | Ядро loopback |
| `grab.py` | CLI |
| `grab_gui.py` | GUI |

```bash
python grab.py --list
python grab.py -o capture.wav -d 30
python grab_gui.py
```

Выбирайте loopback **того** устройства, на которое идёт звук (`[default]`).

## Микрофон

| Файл | Роль |
| --- | --- |
| `mic_recorder.py` | Ядро |
| `mic_grab.py` | CLI |
| `mic_grab_gui.py` | GUI |

```bash
python mic_grab.py --list
python mic_grab.py -o voice.wav -d 10
python mic_grab_gui.py
```

### Микрофон ext

`mic_grab_ext.py` / `mic_recorder_ext.py` — эксперимент, базовый mic не ломает:

- папка сегментов, уровень, voice boost
- буфер N сек → файл
- noise gate + **pre/post-roll (мс до и после речи)**
- форматы: `wav` / `flac` / `ogg` / `mp3`

```bash
python mic_grab_ext.py
```

## Конференция: система + микрофон

Сценарий созвона: слышите собеседников (loopback) и говорите в микрофон.

| Файл | Роль |
| --- | --- |
| `conference_recorder_ext.py` | Ядро |
| `conference_grab_ext.py` | GUI |

```bash
python conference_grab_ext.py
```

Возможности:

- **continuous** — один большой файл
- **segments** — нарезка в папку по N секунд
- **stereo** — L = система, R = микрофон (удобно для постобработки)
- **mix** — моно-микс
- опциональный gate + pre/post-roll в режиме сегментов
- voice boost на канале микрофона

Общие хелперы форматов: `audio_io.py`.

## Сравнение

| Подход | Файлы | Зрелость |
| --- | --- | --- |
| WASAPI loopback | `recorder.py`, `grab.py`, `grab_gui.py` | основной |
| Микрофон | `mic_recorder.py`, `mic_grab.py`, `mic_grab_gui.py` | основной |
| Микрофон ext | `mic_recorder_ext.py`, `mic_grab_ext.py` | эксперимент |
| Конференция ext | `conference_recorder_ext.py`, `conference_grab_ext.py` | эксперимент |

## Ограничения

- Ориентир — Windows.
- Continuous в сжатых форматах (mp3/ogg/flac) копит до стопа — для длинных созвонов лучше `wav` или режим segments.
- Неактивный loopback может «зависнуть» на чтении до стопа.
- DRM может давать тишину в loopback.

## Лицензия и использование

Учебный/прототипный проект. Записывайте только звук, на который у вас есть права.
