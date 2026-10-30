# src/data_gen.py
"""Генерация синтетических операций. Воспроизводимо: фиксированный seed из config."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CONFIG, Config

SCENARIOS = ["social_engineering", "phishing", "malware", "legit"]


def generate(cfg: Config = CONFIG) -> pd.DataFrame:
    d = cfg.data
    rng = np.random.default_rng(d.seed)
    n = d.n_transactions

    is_fraud = rng.random(n) < d.fraud_rate
    age_55plus = rng.random(n) < d.share_55plus
    # среди фрода доля 55+ выше (допущение DataConfig.fraud_share_55plus)
    n_fraud = int(is_fraud.sum())
    idx_fraud = np.where(is_fraud)[0]
    flip = rng.choice(idx_fraud, size=int(n_fraud * d.fraud_share_55plus), replace=False)
    age_55 = age_55plus.copy()
    age_55[flip] = True

    channel = np.where(rng.random(n) < d.share_sbp, "SBP", "DBO")
    hour = rng.integers(0, 24, n)
    data_lag = rng.random(n) < d.data_lag_share
    guardian = rng.random(n) < cfg.scoring.guardian_coverage

    # суммы: логнормальное распределение; у фрода и «рискованных» легитимных — крупнее
    amount = np.exp(rng.normal(np.log(3_000), 1.0, n)).round(2)
    risky_legit = (~is_fraud) & (rng.random(n) < d.risky_legit_share)
    big = is_fraud | risky_legit
    amount[big] = np.exp(rng.normal(np.log(60_000), 0.9, int(big.sum()))).round(2)
    atypical_amount = big & (rng.random(n) < 0.8)

    scenario = np.full(n, "legit", dtype=object)
    fa = rng.random(n)
    scenario[is_fraud & (fa < d.scenario_social)] = "social_engineering"
    scenario[is_fraud & (fa >= d.scenario_social) & (fa < d.scenario_social + d.scenario_phishing)] = "phishing"
    scenario[is_fraud & (fa >= d.scenario_social + d.scenario_phishing)] = "malware"

    p = lambda prob_fraud, prob_legit: np.where(
        is_fraud, rng.random(n) < prob_fraud, rng.random(n) < prob_legit)

    # поведенческие и технические признаки (вход для R01–R12)
    new_recipient = p(0.90, 0.08)
    phone_changed_48h = p(0.35, 0.005) | (risky_legit & (rng.random(n) < 0.25))
    new_device = p(0.40, 0.02)
    device_risk_factors = p(0.25, 0.002)
    device_in_cbr_db = p(0.10, 0.0005)
    recipient_in_cbr_db = p(0.08, 0.0002)
    recipient_in_bank_db = p(0.10, 0.0005)
    recipient_criminal_case = p(0.05, 0.0001)
    recipient_in_gis = p(0.06, 0.0002)
    third_party_signal = p(0.30, 0.001)
    nspk_signal = p(0.12, 0.001)
    night = (hour < 6) | (hour >= 23)
    is_atypical = atypical_amount | (night & p(0.5, 0.05)) | new_device

    # у части фрода есть «подтверждение звонком клиенту» → правила R05/R06 не срабатывают;
    # эти операции ловит только ML (иначе на синтетике правила перекрывают весь фрод)
    phone_confirm = is_fraud & (rng.random(n) < 0.6)
    third_party_signal = third_party_signal & ~phone_confirm
    device_risk_factors = device_risk_factors & ~(phone_confirm & (rng.random(n) < 0.5))
    is_atypical = is_atypical & ~phone_confirm

    # R11: перевод себе >200 тыс. <24 ч назад + новый получатель без отношений 6 мес
    self_transfer_amount = np.where(p(0.25, 0.002), 250_000.0, 0.0)
    self_transfer_hours_ago = np.where(self_transfer_amount > 0, rng.uniform(1, 20, n), 999.0)
    recipient_relation_months = np.where(new_recipient, rng.uniform(6, 60, n), rng.uniform(0, 5, n))

    # R12: пополнение через банкомат цифровой картой + трансграничный перевод получателя >100 тыс. за 24 ч
    atm_digital_card_deposit = p(0.05, 0.003)
    recipient_crossborder_24h_amount = np.where(p(0.06, 0.0003), 150_000.0, 0.0)

    # R10 (п. 1.3): превышение норматива времени обмена НСПК при бесконтактной операции
    atm_nfc_timeout = p(0.04, 0.001)

    ts = pd.date_range("2026-04-01", periods=n, freq="min")  # квартал, монотонно — для time split

    return pd.DataFrame({
        "tx_id": [f"T{i:06d}" for i in range(n)],
        "timestamp": ts,
        "age_55plus": age_55,
        "channel": channel,
        "amount": amount,
        "hour": hour,
        "is_night": night,
        "new_recipient": new_recipient,
        "phone_changed_48h": phone_changed_48h,
        "new_device": new_device,
        "device_risk_factors": device_risk_factors,
        "device_in_cbr_db": device_in_cbr_db,
        "recipient_in_cbr_db": recipient_in_cbr_db,
        "recipient_in_bank_db": recipient_in_bank_db,
        "recipient_criminal_case": recipient_criminal_case,
        "recipient_in_gis": recipient_in_gis,
        "third_party_signal": third_party_signal,
        "nspk_signal": nspk_signal,
        "is_atypical": is_atypical,
        "self_transfer_amount": self_transfer_amount,
        "self_transfer_hours_ago": self_transfer_hours_ago,
        "recipient_relation_months": recipient_relation_months,
        "atm_digital_card_deposit": atm_digital_card_deposit,
        "recipient_crossborder_24h_amount": recipient_crossborder_24h_amount,
        "atm_nfc_timeout": atm_nfc_timeout,
        "data_lag": data_lag,
        "guardian_enabled": guardian,
        "is_fraud": is_fraud,
        "scenario": scenario,
    })


if __name__ == "__main__":
    df = generate()
    import os
    os.makedirs("data", exist_ok=True)
    df.to_csv("data/transactions.csv", index=False)
    print(f"data/transactions.csv: {len(df)} строк, фрода {df.is_fraud.mean():.3%}")
