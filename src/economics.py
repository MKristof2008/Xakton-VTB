# src/economics.py
"""Стоимость внедрения и экономический эффект. Итог затрат ≤ 50 млн ₽ (проверка).

Эффект за год (экстраполяция квартальных метрик на год):
- сохранённые средства клиентов (доля ВТБ в ОБДС — параметр vtb_share_obds, 12%);
- экономия на обращениях в поддержку и разборах (меньше ложных ограничений);
- сохранённый комиссионный доход (платежи, которые прошли благодаря мягкому трению);
- NPS → удержание: явное допущение в config (п.п. за событие).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import CONFIG, Config
from .metrics import KpiReport

# ОБДС физлиц РФ за квартал по каналам фокуса (счета+СБП), млн ₽ — обзор ЦБ II кв. 2026
OBDS_Q_SBP_ACCOUNTS_MLN = 2_166.08 + 2_741.02
QUARTERS_PER_YEAR = 4
# ОБДС физлиц РФ за квартал, всех клиентов: 458 655 ед. / 7 350,72 млн ₽ (II кв. 2026)
OBDS_Q_ALL_OPS = 458_655
AVG_FRAUD_AMOUNT = 7_350_720_000 / OBDS_Q_ALL_OPS  # ≈16 тыс. ₽, в нашей выборке фрод крупнее


@dataclass
class EconomicsReport:
    costs: dict[str, float]
    total_cost: float
    budget_ok: bool
    annual_effect: float
    effect_parts: dict[str, float]
    roi: float
    npv: float
    payback_months: float
    nps_delta: float
    scale_ops_year: float = 0.0  # экстраполяция теста на годовой поток операций ВТБ (фокус)
    scenario: str = "Базовый"
    assumptions: list[tuple[str, str, str]] = field(default_factory=list)


def check_budget(cfg: Config = CONFIG) -> tuple[float, bool]:
    total = sum(cfg.economics.costs.values())
    return total, total <= cfg.economics.budget_cap


def annual_effect(base: KpiReport, sol: KpiReport, cfg: Config = CONFIG,
                  multiplier: float = 1.0) -> tuple[float, dict[str, float], float]:
    """Годовой эффект, ₽. Тест = квартал синтетики; экстраполируем на годовой поток ВТБ.

    Масштаб: доля ВТБ в ОБДС (12%, допущение) × объёмы ЦБ II кв. 2026 (счета+СБП).
    Сумма отклонённого законного перевода — НЕ убыток банка; убыток — только
    недополученный комиссионный доход (p2p_fee_rate) и стоимость обращений.
    """
    e = cfg.economics
    # годовой поток операций ВТБ в каналах фокуса (допущение: средний чек как в нашей выборке)
    scale_ops = OBDS_Q_ALL_OPS * e.vtb_share_obds * QUARTERS_PER_YEAR  # операций/год
    avg_fraud = base.total_fraud_amount / max(1, base.tp + base.fn)

    # сохранённые средства клиентов: прирост предотвращённого объёма × масштаб ВТБ
    extra_share = max(0.0, sol_prevented_share(base, sol))
    extra_prevented_total = (OBDS_Q_SBP_ACCOUNTS_MLN * 1e6 * QUARTERS_PER_YEAR
                             * e.vtb_share_obds * extra_share)
    # банку монетизируется только доля компенсаций/резервов (payout_share);
    # полная сумма предотвращённых хищений — социальный эффект, считается отдельно (как в кейсе)
    extra_prevented = extra_prevented_total * e.payout_share
    # экономия на поддержке/разборах: каждое избежанное ошибочное ограничение
    avoided_share = max(0.0, base.wrong_restricted_share - sol.wrong_restricted_share)
    avoided_ops_year = avoided_share * scale_ops
    support_saving = avoided_ops_year * (e.support_call_cost + e.manual_review_cost)
    # сохранённый комиссионный доход: легитимные суммы, которые в baseline не прошли
    avg_legit_blocked_base = base.legit_blocked_amount / max(1, base.wrong_restricted_count)
    fee_saving = avoided_ops_year * avg_legit_blocked_base * e.p2p_fee_rate
    # удержание: часть клиентов уходит после ошибочного ограничения (NPS → churn)
    retention_saving = (avoided_ops_year * e.churn_share_per_wrong_restriction
                        * e.client_annual_value)

    total = (extra_prevented + support_saving + fee_saving + retention_saving) * multiplier
    return total, {
        "Сохранённые средства клиентов, доля банка (год)": extra_prevented * multiplier,
        "Экономия на поддержке и разборах (год)": support_saving * multiplier,
        "Сохранённый комиссионный доход (год)": fee_saving * multiplier,
        "Удержание клиентов, NPS → churn (год)": retention_saving * multiplier,
    }, scale_ops


def sol_prevented_share(base: KpiReport, sol: KpiReport) -> float:
    """Прирост доли предотвращённого объёма хищений (решение vs baseline)."""
    tb = base.prevented_amount + base.missed_amount
    ts = sol.prevented_amount + sol.missed_amount
    if tb <= 0 or ts <= 0:
        return 0.0
    return sol.prevented_amount / ts - base.prevented_amount / tb


def nps_delta(base: KpiReport, sol: KpiReport, cfg: Config = CONFIG) -> float:
    e = cfg.economics
    avoided = max(0, base.wrong_restricted_count - sol.wrong_restricted_count)
    extra_fraud_stopped = max(0, sol.tp - base.tp)
    return avoided * e.nps_gain_per_avoided_fp + extra_fraud_stopped * e.nps_gain_per_prevented_fraud


def npv(annual: float, cost: float, cfg: Config = CONFIG) -> float:
    r, n = cfg.economics.discount_rate, cfg.economics.horizon_years
    return -sum(cfg.economics.costs.values()) + sum(annual / (1 + r) ** y for y in range(1, n + 1))


def build_report(base: KpiReport, sol: KpiReport, cfg: Config = CONFIG,
                 scenario: str = "Базовый") -> EconomicsReport:
    e = cfg.economics
    total_cost, ok = check_budget(cfg)
    mult = e.scenario_multipliers[scenario]
    annual, parts, scale_ops = annual_effect(base, sol, cfg, mult)
    roi = (annual - total_cost) / total_cost if total_cost else 0.0
    payback = total_cost / annual * 12 if annual > 0 else float("inf")
    assumptions = [
        ("Доля ВТБ в ОБДС физлиц", f"{e.vtb_share_obds:.0%}", "Допущение; доля в хищениях не публикуется"),
        ("Доля компенсаций банка в предотвращённом", f"{e.payout_share:.0%}",
         "Допущение; по ЦБ II кв. 2026 возмещено 13,7% ОБДС, по СБП 2,1%"),
        ("Стоимость обращения в поддержку", f"{e.support_call_cost:,.0f} ₽", "Среднерыночная оценка (допущение)"),
        ("Стоимость разбора оператором", f"{e.manual_review_cost:,.0f} ₽", "20–30 мин работы (допущение)"),
        ("Комиссионный доход с P2P", f"{e.p2p_fee_rate:.1%} от суммы", "Допущение (межбанк/вывод)"),
        ("Отток после ошибочного ограничения", f"{e.churn_share_per_wrong_restriction:.0%} клиентов",
         "Допущение; обосновывается NPS-опросами"),
        ("Годовой доход с активного клиента ДБО", f"{e.client_annual_value:,.0f} ₽", "Допущение (среднерыночная оценка)"),
        ("NPS за избежанное ложное ограничение", f"+{e.nps_gain_per_avoided_fp} п.п.", "Допущение (слабо обосновано)"),
        ("Ставка дисконтирования", f"{e.discount_rate:.0%}", "≈ключевая ставка + премия (допущение)"),
        ("Сумма ОБДС по СБП+счета, квартал", f"{OBDS_Q_SBP_ACCOUNTS_MLN:,.0f} млн ₽", "Обзор ЦБ II кв. 2026"),
    ]
    return EconomicsReport(costs=dict(e.costs), total_cost=total_cost, budget_ok=ok,
                           annual_effect=annual, effect_parts=parts, roi=roi,
                           npv=npv(annual, total_cost, cfg), payback_months=payback,
                           nps_delta=nps_delta(base, sol, cfg), scale_ops_year=scale_ops,
                           scenario=scenario,
                           assumptions=assumptions)
