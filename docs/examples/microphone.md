# Примеры: микрофон

## Базовый CLI

```bash
python mic_grab.py --list
python mic_grab.py -o voice.wav -d 15
```

## Базовый GUI

```bash
python mic_grab_gui.py
```

## Сегменты с gate (ext)

```bash
python mic_grab_ext.py
```

В GUI:

1. Выберите микрофон и папку (например `mic_segments`).
2. Задайте буфер (сек), порог gate, pre/post-roll.
3. Старт — сегменты появятся как `mic-YYYYMMDD-HH-MM-SS-001.wav`.
