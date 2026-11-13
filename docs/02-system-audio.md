# Системный звук (WASAPI loopback)

Запись того, что сейчас играет: фильм, браузер, плеер. Воспроизведение не блокируется. Stereo Mix не нужен.

## Файлы

| Файл | Роль |
| --- | --- |
| `recorder.py` | Ядро |
| `grab.py` | CLI |
| `grab_gui.py` | GUI |

## Запуск

```bash
python grab.py --list
python grab.py -o capture.wav -d 30
python grab_gui.py
```

## Важно

Выбирайте loopback **того** playback-устройства, на которое реально идёт звук (в `--list` помечен `[default]`). Неактивный endpoint может «зависнуть» на чтении до стопа.

Примеры: [examples/system_audio.md](examples/system_audio.md).
