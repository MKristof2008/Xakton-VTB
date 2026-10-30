# src/decision.py
"""Движок решений. Логика закона (161-ФЗ + ОД-2506) обязательна и неотменяема моделью.

Сработал любой R01–R12 → законная приостановка на 2 дня (для СБП — отказ с правом повторить);
подтверждение исполняет операцию, КРОМЕ R01 — там период охлаждения не отменяется согласием.
Ни один признак не сработал → решает ML-скоринг: low/medium/high.
Меры по 115-ФЗ (отмывание) — отдельный процесс, здесь не смешиваются.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import CONFIG, Config
from .rules import triggered_rules

# виды реакций
PASS = "pass"                      # пропуск без трения
SOFT = "soft_friction"             # мягкое трение: биометрия + предупреждение о сценарии
HARD = "enhanced_check"            # повышенная проверка: оператор + «защитник»
LEGAL_HOLD = "legal_hold"          # законная приостановка по R01–R12
LEGAL_HOLD_COOLING = "legal_hold_cooling"  # R01: охлаждение не отменяется согласием

# среднее время трения (мин) — для сравнения клиентского опыта
FRICTION_MINUTES = {PASS: 0.0, SOFT: 1.5, HARD: 15.0, LEGAL_HOLD: 20.0, LEGAL_HOLD_COOLING: 30.0}
FRICTION_MINUTES_BASELINE = {LEGAL_HOLD: 180.0, LEGAL_HOLD_COOLING: 180.0}  # звонок в поддержку, очередь


@dataclass
class Decision:
    action: str
    rules_hit: list[str] = field(default_factory=list)
    risk_score: float | None = None
    reasons: list[str] = field(default_factory=list)
    friction_minutes: float = 0.0
    guardian_requested: bool = False
    note: str = ""


def decide(tx: Any, risk_score: float | None = None, reasons: list[str] | None = None,
           cfg: Config = CONFIG, baseline: bool = False) -> Decision:
    """Решение по одной операции. risk_score обязателен, если не сработали правила
    (кроме baseline: там скоринг не используется — только правила и жёсткая остановка)."""
    hits = triggered_rules(tx, cfg)
    if hits:
        cooling = "R01" in hits
        action = LEGAL_HOLD_COOLING if cooling else LEGAL_HOLD
        fr = FRICTION_MINUTES_BASELINE[action] if baseline else FRICTION_MINUTES[action]
        note = ("Период охлаждения обязателен даже при согласии клиента (получатель в базе ЦБ)"
                if cooling else
                "Приостановка на 2 дня; подтверждение в один шаг исполняет операцию")
        return Decision(action=action, rules_hit=hits, risk_score=risk_score,
                        reasons=reasons or [], friction_minutes=fr, note=note)

    if baseline:
        return Decision(action=PASS, risk_score=None)

    assert risk_score is not None, "нужен risk_score для операции без правил"
    s = cfg.scoring
    if risk_score >= s.threshold_high:
        guardian = bool(tx.get("guardian_enabled") if isinstance(tx, dict)
                        else getattr(tx, "guardian_enabled", False))
        return Decision(action=HARD, risk_score=risk_score, reasons=reasons or [],
                        friction_minutes=FRICTION_MINUTES[HARD], guardian_requested=guardian,
                        note="Звонок антифрод-оператора" + (" + запрос «защитнику» (таймаут 12 ч)" if guardian else ""))
    if risk_score >= s.threshold_medium:
        return Decision(action=SOFT, risk_score=risk_score, reasons=reasons or [],
                        friction_minutes=FRICTION_MINUTES[SOFT],
                        note="Подтверждение биометрией + предупреждение о сценарии мошенничества")
    return Decision(action=PASS, risk_score=risk_score, reasons=reasons or [])
