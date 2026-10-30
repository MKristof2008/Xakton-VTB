# src/metrics.py
"""KPI кейса: confusion matrix, точность/полнота/FPR, доля ложных сигналов,
доля ОШИБОЧНО ОГРАНИЧЕННЫХ операций (отдельно от ложных сигналов),
суммы предотвращённых и пропущенных хищений. Сравнение baseline vs решение.

Ложный сигнал = система пометила законную операцию подозрительной.
Ошибочно ограниченная = легитимный платёж фактически не прошёл (клиент не подтвердил/
не дождался). После подтверждения платёж может пройти — поэтому считаем отдельно.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .config import CONFIG, Config
from .decision import LEGAL_HOLD, LEGAL_HOLD_COOLING, SOFT, HARD, PASS, decide
from .rules import triggered_rules
from .scoring import RiskScorer, time_split

SUSPICIOUS = {LEGAL_HOLD, LEGAL_HOLD_COOLING, SOFT, HARD}


@dataclass
class KpiReport:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    precision: float = 0.0          # TP/(TP+FP) — точность
    recall: float = 0.0             # TP/(TP+FN) — полнота
    fpr: float = 0.0                # FP/(FP+TN) — доля ложных срабатываний среди законных
    false_alarm_share: float = 0.0  # FP/(TP+FP) — доля ложных сигналов
    wrong_restricted_count: int = 0       # легитимные операции, фактически не прошедшие
    wrong_restricted_share: float = 0.0   # доля от всех законных
    prevented_amount: float = 0.0   # сумма предотвращённых хищений
    missed_amount: float = 0.0      # сумма пропущенных хищений
    legit_blocked_amount: float = 0.0  # сумма легитимных платежей, не прошедших из-за ограничений
    total_fraud_amount: float = 0.0
    n_test: int = 0
    avg_friction_minutes: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _finalize(tp: int, fp: int, tn: int, fn: int, wrong: int,
              prevented: float, missed: float, legit_blocked: float,
              n_test: int, frictions: list[float]) -> KpiReport:
    r = KpiReport(tp=tp, fp=fp, tn=tn, fn=fn)
    r.precision = tp / (tp + fp) if tp + fp else 0.0
    r.recall = tp / (tp + fn) if tp + fn else 0.0
    r.fpr = fp / (fp + tn) if fp + tn else 0.0
    r.false_alarm_share = fp / (tp + fp) if tp + fp else 0.0
    r.wrong_restricted_count = wrong
    r.wrong_restricted_share = wrong / (fp + tn) if fp + tn else 0.0
    r.prevented_amount = float(prevented)
    r.missed_amount = float(missed)
    r.legit_blocked_amount = float(legit_blocked)
    r.total_fraud_amount = float(prevented + missed)
    r.n_test = n_test
    r.avg_friction_minutes = float(np.mean(frictions)) if frictions else 0.0
    return r


def evaluate(test: pd.DataFrame, scorer: RiskScorer | None, cfg: Config = CONFIG,
             baseline: bool = False) -> KpiReport:
    """Моделируем судьбу каждой тестовой операции.

    Подтверждение/непрохождение платежа — вероятностное (параметры из ScoringConfig):
    - легитимная + мягкое трение/остановка: проходит с вероятностью confirm_legit_soft
      (baseline: confirm_legit_baseline);
    - мошенническая + трение: проходит с вероятностью confirm_fraud_soft
      (часть жертв настаивает под давлением мошенника).
    R01: охлаждение не отменяется — легитимный платёж откладывается (считается ограниченным
    в моменте, но не отменённым), мошенничество предотвращается паузой.
    """
    rng = np.random.default_rng(cfg.data.seed)
    s = cfg.scoring
    scores = scorer.score_frame(test) if scorer is not None else np.zeros(len(test))

    tp = fp = tn = fn = wrong = 0
    prevented = missed = legit_blocked = 0.0
    frictions: list[float] = []

    for (_, row), score in zip(test.iterrows(), scores):
        d = decide(row, risk_score=None if baseline else float(score),
                   reasons=[], cfg=cfg, baseline=baseline)
        frictions.append(d.friction_minutes)
        suspicious = d.action in SUSPICIOUS
        # судьба операции
        if d.action in (LEGAL_HOLD, LEGAL_HOLD_COOLING, SOFT, HARD):
            if row["is_fraud"]:
                p_confirm = s.confirm_fraud_baseline if baseline else s.confirm_fraud_soft
            else:
                p_confirm = s.confirm_legit_baseline if baseline else s.confirm_legit_soft
            executed = rng.random() < p_confirm
        else:
            executed = True

        if row["is_fraud"]:
            if suspicious and not executed:
                tp += 1
                prevented += row["amount"]
            elif suspicious and executed:  # выявлено, но жертва подтвердила — деньги ушли
                tp += 1
                missed += row["amount"]
            else:
                fn += 1
                missed += row["amount"]
        else:
            if suspicious:
                fp += 1
                if not executed:
                    wrong += 1
                    legit_blocked += row["amount"]
            else:
                tn += 1
    return _finalize(tp, fp, tn, fn, wrong, prevented, missed, legit_blocked,
                     len(test), frictions)


def run_comparison(df: pd.DataFrame, cfg: Config = CONFIG) -> dict[str, KpiReport]:
    """Обучает скоринг на train, сравнивает baseline vs решение на одной тестовой выборке."""
    train, test = time_split(df, cfg)
    scorer = RiskScorer(cfg).fit(train)
    return {
        "baseline": evaluate(test, scorer=None, cfg=cfg, baseline=True),
        "solution": evaluate(test, scorer=scorer, cfg=cfg, baseline=False),
    }
