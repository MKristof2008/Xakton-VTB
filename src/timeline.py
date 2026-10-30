# src/timeline.py
"""План внедрения на 6 месяцев + диаграмма Ганта (plotly)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px

PHASES = [
    {"Фаза": "Аудит данных и дизайн", "start": "2026-01-01", "end": "2026-01-31"},
    {"Фаза": "Правила R01–R12 и ML-модель", "start": "2026-02-01", "end": "2026-03-15"},
    {"Фаза": "Интеграция с ДБО и антифрод-шиной", "start": "2026-03-01", "end": "2026-04-15"},
    {"Фаза": "Теневой режим (shadow mode)", "start": "2026-04-10", "end": "2026-05-10"},
    {"Фаза": "Пилот на части трафика", "start": "2026-05-05", "end": "2026-06-05"},
    {"Фаза": "Раскатка на 100% трафика", "start": "2026-06-01", "end": "2026-06-30"},
]


def gantt_figure() -> "px.timeline":
    df = pd.DataFrame(PHASES)
    fig = px.timeline(df, x_start="start", x_end="end", y="Фаза", title="Внедрение за 6 месяцев")
    fig.update_yaxes(autorange="reversed")
    return fig
