# src/rules.py
"""Правила R01–R12 по приказу ЦБ № ОД-2506 (сверено с текстом приказа).

Все 12 признаков юридически обязывающие: срабатывание любого → приостановка/отказ по 161-ФЗ,
скоринг модели отменить её не может. Маппинг на пункты приказа указан в поле clause.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import CONFIG, Config


@dataclass(frozen=True)
class Rule:
    rid: str
    name: str
    group: str
    clause: str  # пункт приказа ОД-2506


RULES: list[Rule] = [
    Rule("R01", "Получатель в базе Банка России", "Получатель и известные случаи", "1.1"),
    Rule("R02", "Получатель во внутренней базе банка", "Получатель и известные случаи", "1.7"),
    Rule("R03", "Уголовное дело о мошенничестве в отношении получателя", "Получатель и известные случаи", "1.8"),
    Rule("R04", "Сведения ГИС противодействия ИКТ-правонарушениям (с 01.03.2026)", "Получатель и известные случаи", "1.2"),
    Rule("R05", "Нетипичная для клиента операция", "Поведение и внешние сигналы", "1.6"),
    Rule("R06", "Сигнал сторонних организаций о риске (≥6 ч до перевода)", "Поведение и внешние сигналы", "1.9"),
    Rule("R07", "Информация НСПК о риске", "Поведение и внешние сигналы", "1.4"),
    Rule("R08", "Устройство из базы Банка России", "Устройство", "1.5"),
    Rule("R09", "Смена номера телефона за 48 ч до перевода", "Устройство", "1.10"),
    Rule("R10", "Факторы риска на устройстве / превышение норматива обмена НСПК (NFC-банкомат)", "Устройство", "1.10/1.3"),
    Rule("R11", "Новый получатель после перевода себе через СБП >200 тыс. ₽ <24 ч назад", "Последовательность переводов", "1.12"),
    Rule("R12", "Пополнение через банкомат цифровой картой после трансграничного перевода >100 тыс. ₽ за 24 ч", "Внесение наличных", "1.11"),
]


def triggered_rules(tx: Any, cfg: Config = CONFIG) -> list[str]:
    """Возвращает список id сработавших правил для операции (строка DataFrame или dict)."""
    g = tx.get if isinstance(tx, dict) else lambda k, d=None: getattr(tx, k, d)
    r = cfg.rules
    out: list[str] = []

    if g("recipient_in_cbr_db"):
        out.append("R01")
    if g("recipient_in_bank_db"):
        out.append("R02")
    if g("recipient_criminal_case"):
        out.append("R03")
    if g("recipient_in_gis"):
        out.append("R04")
    if g("is_atypical"):
        out.append("R05")
    if g("third_party_signal"):
        out.append("R06")
    if g("nspk_signal"):
        out.append("R07")
    if g("device_in_cbr_db"):
        out.append("R08")
    if g("phone_changed_48h"):
        out.append("R09")
    if g("device_risk_factors") or g("atm_nfc_timeout"):
        out.append("R10")
    if (g("self_transfer_amount", 0) > r.r11_self_transfer_min
            and g("self_transfer_hours_ago", 999) < r.r11_interval_hours
            and g("recipient_relation_months", 0) >= r.r11_no_relation_months):
        out.append("R11")
    if (g("atm_digital_card_deposit")
            and g("recipient_crossborder_24h_amount", 0) > r.r12_crossborder_min):
        out.append("R12")
    return out


def rule_meta(rid: str) -> Rule:
    return next(x for x in RULES if x.rid == rid)
