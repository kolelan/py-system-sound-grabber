# Примеры: системный звук

## Список loopback-устройств

```bash
python grab.py --list
```

## Запись 30 секунд в файл

```bash
python grab.py -o capture.wav -d 30
```

## Запись до Ctrl+C с выбором устройства

```bash
python grab.py -o capture.wav -i 20
```

## GUI

```bash
python grab_gui.py
```
