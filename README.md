# py-system-sound-grabber

Запись звука на Windows: системный вывод (то, что играет) и микрофон. WAV пишется сразу на диск, без накопления всей сессии в RAM.

## Установка

```bash
pip install -r requirements.txt
```

Зависимость: [`PyAudioWPatch`](https://github.com/s0d3s/PyAudioWPatch) (WASAPI + обычный ввод).

## Системный звук (WASAPI loopback)

Пишет то, что сейчас играет (фильм, плеер, браузер), без Stereo Mix и без блокировки воспроизведения.

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

Выбирайте loopback **того** устройства, на которое идёт звук (`[default]` в `--list`). Неактивный endpoint может «зависнуть» на чтении до стопа.

## Микрофон

| Файл | Роль |
| --- | --- |
| `mic_recorder.py` | Ядро записи с входа |
| `mic_grab.py` | CLI |
| `mic_grab_gui.py` | GUI |

```bash
python mic_grab.py --list
python mic_grab.py -o voice.wav -d 10
python mic_grab_gui.py
```

Loopback-устройства в списке микрофонов не показываются.

## Цель

| Нужно | Не нужно |
| --- | --- |
| Системный звук и/или микрофон | Обход DRM |
| Воспроизведение не прерывается при loopback | Сервис/трей (пока нет) |
| Фоновая запись в WAV | |

## Как устроен loopback

Приложения отдают звук в playback-устройство. WASAPI умеет слушать тот же endpoint в режиме **loopback** — виртуальный вход вида `Динамики … [Loopback]`.

Исторические альтернативы (прототипы в репо): Stereo Mix, VB-Audio Virtual Cable.

## Карта старых прототипов

| Файл | Назначение |
| --- | --- |
| `proto1.py` / `record-ui.py` / `mic-rec.py` | Ранние опыты (часто mic) |
| `stereo-mix.py` / `sounddevice.py` | Stereo Mix / кабель по имени |
| `sound-gui.py` / `start-grab.py` | GUI со Stereo Mix |

Для новой работы: `grab*` (система) и `mic_grab*` (микрофон).

## Сравнение

| Подход | Файлы | Зрелость |
| --- | --- | --- |
| WASAPI loopback | `recorder.py`, `grab.py`, `grab_gui.py` | основной |
| Микрофон | `mic_recorder.py`, `mic_grab.py`, `mic_grab_gui.py` | основной |
| Stereo Mix / sounddevice | старые скрипты | прототип |

## Ограничения

- Ориентир — Windows.
- Нет иконки в трее / hotkey.
- Только WAV PCM; DRM может давать тишину в loopback.

## Возможное развитие

- Иконка в трее и hotkey старт/стоп
- Одновременная запись mic + system (два трека / микс)
- FLAC/MP3 поверх сырого потока

## Лицензия и использование

Учебный/прототипный проект. Записывайте только звук, на который у вас есть права.
