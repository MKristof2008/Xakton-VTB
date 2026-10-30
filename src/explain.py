# src/explain.py
"""Тексты клиенту: что произошло, почему, что делать.

По умолчанию — шаблоны. Если в окружении есть LLM_API_KEY — опциональный вызов
OpenAI-совместимого API (LLM_BASE_URL); без ключа или при ошибке — шаблон, без исключений.
"""
from __future__ import annotations

import json
import os
import urllib.request

from .decision import Decision, LEGAL_HOLD, LEGAL_HOLD_COOLING, SOFT, HARD, PASS
from .rules import rule_meta

TEMPLATES = {
    LEGAL_HOLD: ("Ваш перевод приостановлен на 2 дня по требованию закона (161-ФЗ): "
                 "операция имеет признаки из перечня Банка России ({rules}). "
                 "Если вы уверены в получателе, подтвердите перевод в приложении в течение суток — "
                 "и мы исполним его незамедлительно. Никто из сотрудников банка не просит вас переводить деньги."),
    LEGAL_HOLD_COOLING: ("Получатель найден в базе Банка России о мошеннических операциях. "
                         "По закону действует обязательный период охлаждения: перевод можно будет "
                         "повторить не раньше конца следующего календарного дня. Пожалуйста, не переводите "
                         "деньги по просьбе звонящих — настоящие сотрудники банка так не делают."),
    SOFT: ("Операция выглядит необычно ({reasons}). Подтвердите её биометрией в приложении. "
           "Если вам звонили и просили перевести деньги на «безопасный счёт» — это мошенники. Положите трубку."),
    HARD: ("Мы хотим убедиться, что перевод делаете вы по своей воле. Оператор банка свяжется с вами. "
           "{guardian}Проверка занимает около 15 минут — это защита ваших денег."),
    PASS: "",
}


def client_text(decision: Decision) -> str:
    """Шаблонный текст по решению; при наличии LLM_API_KEY — попытка улучшить формулировку."""
    rules = ", ".join(f"{r} ({rule_meta(r).name})" for r in decision.rules_hit) or "—"
    reasons = ", ".join(decision.reasons) if decision.reasons else "необычные параметры"
    guardian = ("Ваш «защитник» в сервисе «Защита близких» также получит запрос (ответ нужен в течение 12 часов). "
                if decision.guardian_requested else "")
    text = TEMPLATES[decision.action].format(rules=rules, reasons=reasons, guardian=guardian)
    improved = _llm_rewrite(text)
    return improved or text


def _llm_rewrite(text: str) -> str | None:
    key = os.environ.get("LLM_API_KEY")
    if not key or not text:
        return None
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    try:
        req = urllib.request.Request(
            f"{base.rstrip('/')}/chat/completions",
            data=json.dumps({
                "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": "Перепиши сообщение банка клиенту: доброжелательно, коротко, без канцелярита. Не меняй смысл и сроки."},
                    {"role": "user", "content": text}],
                "max_tokens": 300, "temperature": 0.3,
            }).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None  # без ключа/сети — работаем на шаблонах
