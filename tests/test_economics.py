"""Тест экономики: бюджет в пределах ограничения кейса."""
from src.config import CONFIG
from src.economics import check_budget


def test_budget_within_cap():
    total, ok = check_budget(CONFIG)
    assert ok, f"затраты {total:,.0f} ₽ превышают лимит {CONFIG.economics.budget_cap:,.0f} ₽"
    assert total > 0
