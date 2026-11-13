# Старые прототипы

Ранние эксперименты до WASAPI loopback / единого ядра. Для новой работы не нужны, оставлены как история.

| Файл | Назначение |
| --- | --- |
| `proto1.py` | Первый рекордер (часто устройство по умолчанию) |
| `mic-rec.py` | Микрофон + стоп по пробелу |
| `stereo-mix.py` | Поиск Stereo Mix по имени |
| `sounddevice.py` | sounddevice + поиск loopback-имени |
| `record-ui.py` | Минимальный GUI mic |
| `sound-gui.py` / `start-grab.py` | GUI со Stereo Mix |

Актуальные точки входа — в [корневом README](../README.md) и сценариях `02`–`05`.
