"""Тесты метрик: сравнение baseline vs решение на маленькой синтетике."""
from src.config import Config, DataConfig
from src.data_gen import generate
from src.metrics import run_comparison

SMALL = Config(data=DataConfig(n_transactions=6_000, seed=42))


def test_comparison_returns_both_reports():
    rep = run_comparison(generate(SMALL), cfg=SMALL)
    assert set(rep) == {"baseline", "solution"}
    assert rep["baseline"].n_test > 0


def test_solution_not_worse_on_wrong_restrictions():
    """Ключевое обещание решения: меньше ошибочных ограничений и не хуже по выявлению."""
    rep = run_comparison(generate(SMALL), cfg=SMALL)
    b, s = rep["baseline"], rep["solution"]
    assert s.wrong_restricted_share <= b.wrong_restricted_share
    assert s.tp >= b.tp
    assert s.recall >= b.recall
    assert s.avg_friction_minutes < b.avg_friction_minutes
