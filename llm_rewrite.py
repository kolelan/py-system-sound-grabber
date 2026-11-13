"""Переработка текста через DeepSeek / любой OpenAI-совместимый Chat Completions API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"  # также: deepseek-flash, deepseek-v4-pro


@dataclass
class LlmSettings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_sec: float = 120.0


class LlmError(Exception):
    """Ошибка вызова LLM API."""


def rewrite_text(
    text: str,
    prompt: str,
    settings: LlmSettings,
    system_prompt: Optional[str] = None,
) -> str:
    """
    Отправляет распознанный текст + уточняющий промпт в LLM.
    Возвращает переработанный текст.
    """
    text = (text or "").strip()
    prompt = (prompt or "").strip()
    if not text:
        raise LlmError("Нет текста для переработки.")
    if not settings.api_key.strip():
        raise LlmError("Не указан API-ключ.")

    system = system_prompt or (
        "Ты помощник по редактуре расшифровок речи. "
        "Исправь текст по инструкции пользователя, сохрани смысл. "
        "Отвечай только итоговым текстом без пояснений."
    )
    user_content = (
        f"Инструкция:\n{prompt}\n\n"
        f"Текст расшифровки:\n{text}"
    )

    base = settings.base_url.rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.api_key.strip()}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LlmError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"Сеть: {exc.reason}") from exc

    try:
        data = json.loads(raw)
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LlmError(f"Неожиданный ответ API: {raw[:500]}") from exc


def api_key_from_env() -> str:
    return (
        os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
