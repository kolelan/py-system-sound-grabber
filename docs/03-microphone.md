# Микрофон

## Базовый режим

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

Loopback-устройства в списке микрофонов не показываются.

## Расширенный режим (`*_ext`)

| Файл | Роль |
| --- | --- |
| `mic_recorder_ext.py` | Ядро сегментов |
| `mic_grab_ext.py` | GUI |

Возможности:

- выбор папки для сегментов
- индикатор уровня
- voice boost (подъём речевой полосы)
- буфер N секунд → автосохранение
- noise gate + pre/post-roll (мс до и после речи)
- форматы: `wav` / `flac` / `ogg` / `mp3`

```bash
python mic_grab_ext.py
```

Имена сегментов: `mic-YYYYMMDD-HH-MM-SS-001.ext`.

Примеры: [examples/microphone.md](examples/microphone.md).
