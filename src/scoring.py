# src/scoring.py
"""ML-скоринг: LogisticRegression + GradientBoosting, калибровка, split по времени.

Применяется только к операциям без сработавших R01–R12 (см. decision.py).
Выход: risk_score 0–1 и топ-3 причины (по |вкладу признака| в логит).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .config import CONFIG, Config

FEATURES = [
    "amount", "hour", "is_night", "new_recipient", "phone_changed_48h",
    "new_device", "device_risk_factors", "is_atypical", "age_55plus",
    "data_lag", "self_transfer_amount", "recipient_relation_months",
]
FEATURE_RU = {
    "amount": "Крупная сумма", "hour": "Время суток", "is_night": "Ночная операция",
    "new_recipient": "Новый получатель", "phone_changed_48h": "Недавняя смена номера",
    "new_device": "Новое устройство", "device_risk_factors": "Факторы риска на устройстве",
    "is_atypical": "Нетипичная операция", "age_55plus": "Клиент 55+",
    "data_lag": "Данные поступили с задержкой",
    "self_transfer_amount": "Недавний перевод себе из другого банка",
    "recipient_relation_months": "Давность отношений с получателем",
}


def time_split(df: pd.DataFrame, cfg: Config = CONFIG) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Хвост по времени — тестовая выборка (без перемешивания)."""
    k = int(len(df) * (1 - cfg.scoring.test_size_time_split))
    return df.iloc[:k], df.iloc[k:]


class RiskScorer:
    def __init__(self, cfg: Config = CONFIG) -> None:
        self.cfg = cfg
        base = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=cfg.data.seed)
        self.logreg = CalibratedClassifierCV(
            Pipeline([("sc", StandardScaler()), ("lr", base)]), cv=3)
        self.gbm = CalibratedClassifierCV(
            GradientBoostingClassifier(random_state=cfg.data.seed), cv=3)
        self._inner: LogisticRegression | None = None

    def fit(self, train: pd.DataFrame) -> "RiskScorer":
        X, y = train[FEATURES].astype(float), train["is_fraud"].astype(int)
        self.logreg.fit(X, y)
        self.gbm.fit(X, y)
        for est in self.logreg.calibrated_classifiers_:
            self._inner = est.estimator.named_steps["lr"]
        return self

    def _scale(self, row: pd.Series) -> pd.DataFrame:
        return row[FEATURES].astype(float).to_frame().T

    def score(self, row: pd.Series) -> float:
        """Ансамбль: среднее откалиброванных вероятностей logreg и GBM."""
        X = self._scale(row)
        p = 0.5 * self.logreg.predict_proba(X)[0, 1] + 0.5 * self.gbm.predict_proba(X)[0, 1]
        if row.get("data_lag"):
            p = min(1.0, p + self.cfg.scoring.data_lag_shift)  # ступень осторожности при data_lag
        return float(p)

    def reasons(self, row: pd.Series, top: int = 3) -> list[str]:
        """Топ-3 причины по |коэффициент × стандартизованное значение| логистической модели."""
        if self._inner is None:
            return []
        pipe = self.logreg.calibrated_classifiers_[0].estimator
        x = pipe.named_steps["sc"].transform(self._scale(row))[0]
        lr: LogisticRegression = pipe.named_steps["lr"]
        contrib = lr.coef_[0] * x
        order = np.argsort(-np.abs(contrib))[:top]
        return [FEATURE_RU[FEATURES[i]] for i in order if contrib[i] > 0]

    def score_frame(self, df: pd.DataFrame) -> np.ndarray:
        X = df[FEATURES].astype(float)
        p = 0.5 * self.logreg.predict_proba(X)[:, 1] + 0.5 * self.gbm.predict_proba(X)[:, 1]
        return np.minimum(1.0, p + df["data_lag"].to_numpy() * self.cfg.scoring.data_lag_shift)
