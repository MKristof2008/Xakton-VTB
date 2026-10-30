"""Тесты правил R01–R12."""
from src.rules import triggered_rules

CLEAN = dict(
    recipient_in_cbr_db=False, recipient_in_bank_db=False, recipient_criminal_case=False,
    recipient_in_gis=False, is_atypical=False, third_party_signal=False, nspk_signal=False,
    device_in_cbr_db=False, phone_changed_48h=False, device_risk_factors=False,
    atm_nfc_timeout=False, self_transfer_amount=0, self_transfer_hours_ago=999,
    recipient_relation_months=12, atm_digital_card_deposit=False,
    recipient_crossborder_24h_amount=0,
)


def test_clean_transaction_no_rules():
    assert triggered_rules(CLEAN) == []


def test_r01_cbr_db():
    assert "R01" in triggered_rules({**CLEAN, "recipient_in_cbr_db": True})


def test_r09_phone_change():
    assert "R09" in triggered_rules({**CLEAN, "phone_changed_48h": True})


def test_r11_full_conditions():
    tx = {**CLEAN, "self_transfer_amount": 250_000, "self_transfer_hours_ago": 5,
          "recipient_relation_months": 12}
    assert "R11" in triggered_rules(tx)
    # сумма меньше порога — правило не срабатывает
    assert "R11" not in triggered_rules({**tx, "self_transfer_amount": 150_000})
    # давние отношения с получателем — не срабатывает
    assert "R11" not in triggered_rules({**tx, "recipient_relation_months": 2})
