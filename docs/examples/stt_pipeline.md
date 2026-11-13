# Пример: запись → текст → DeepSeek

Полный контур обработки созвона или голосовой заметки.

## 1. Зависимости и модель

```bash
pip install -r requirements.txt
python stt_download_model.py --list
python stt_download_model.py gigaam-v3
```

## 2. Запись

Конференция:

```bash
python conference_grab_ext.py
```

Или только микрофон:

```bash
python mic_grab_ext.py
```

Допустим, получился файл:

```text
conference_captures\conference-20261113-14-30-01.wav
```

## 3. Распознавание (CLI)

```bash
python stt_grab.py conference_captures\conference-20261113-14-30-01.wav --model gigaam-v3 -o transcript.txt
```

Сразу с правкой через LLM:

```bash
set DEEPSEEK_API_KEY=sk-...
python stt_grab.py conference_captures\conference-20261113-14-30-01.wav ^
  -o protocol.txt ^
  --rewrite-prompt "Сделай краткий протокол: темы, решения, задачи с ответственными"
```

## 4. Распознавание (GUI)

```bash
python stt_grab_gui.py
```

1. **Папка записей…** → выбрать WAV.
2. Выбрать модель в списке (или скачать GigaAM / Whisper / Vosk).
3. **Распознать**.
4. В промпте, например:  
   `Исправь ошибки ASR и оформи как протокол встречи.`
5. Вставить API key (или заранее `DEEPSEEK_API_KEY`).
6. **Отправить в LLM**.

## 5. Другой LLM-endpoint

Если прокси/совместимый шлюз:

```bash
python stt_grab.py file.wav ^
  --rewrite-prompt "Суммаризуй" ^
  --api-base https://your-gateway.example/v1 ^
  --api-model gpt-4o-mini ^
  --api-key sk-...
```

В GUI те же поля: Base URL и Model.
