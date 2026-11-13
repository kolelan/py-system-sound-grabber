# Примеры: конференция

## GUI

```bash
python conference_grab_ext.py
```

### Один файл созвона

1. Режим **Один большой файл**.
2. Папка: `conference_captures`.
3. Файл: `conference.wav` (базовое имя).
4. Формат: `wav`, раскладка: `stereo`.
5. **Старт** — на диск уйдёт что-то вроде  
   `conference_captures\conference-20261113-14-30-01.wav`.

### Сегменты для постобработки

1. Режим **Сегменты в папку**.
2. Сегмент, сек: `30`–`60`.
3. При необходимости включите gate + pre/post-roll.
4. Файлы: `conf-YYYYMMDD-HH-MM-SS-001.wav`, …

Дальше эти файлы можно отдать в STT: [stt_pipeline.md](stt_pipeline.md).
