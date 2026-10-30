# app.py — только UI. Вся логика в src/.
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config import CONFIG
from src.data_gen import generate
from src.decision import decide, FRICTION_MINUTES_BASELINE
from src.economics import build_report, check_budget
from src.explain import client_text
from src.metrics import run_comparison
from src.process import STAGES, RACI, RACI_COLS, BLOCKS
from src.rules import RULES
from src.scoring import RiskScorer, time_split
from src.timeline import gantt_figure

st.set_page_config(page_title="Деньги под защитой — ВТБ × Changellenge", layout="wide")
st.title("Деньги под защитой: антифрод без лишнего трения")
st.caption("⚠️ Данные синтетические, параметры экономики — допущения команды. "
           "Условия R01–R12 сверены с приказом ЦБ № ОД-2506.")


@st.cache_data
def load_data() -> pd.DataFrame:
    return generate()


@st.cache_resource
def load_model(df: pd.DataFrame) -> RiskScorer:
    train, _ = time_split(df)
    return RiskScorer().fit(train)


@st.cache_data
def load_kpi(_df: pd.DataFrame) -> dict:
    return run_comparison(_df)


df = load_data()
scorer = load_model(df)
kpi = load_kpi(df)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Задача и фокус", "Процесс", "Симулятор операции", "Метрики до/после",
    "Экономика", "Сроки", "Экспорт"])

with tab1:
    st.header("Фокус: переводы СБП + ДБО, социальная инженерия, клиенты 55+")
    st.write("СБП и счета (ДБО) — **≈75% денежного объёма хищений** у физлиц (II кв. 2026, ЦБ). "
             "По СБП возвращается лишь 2,1% похищенного. Соц. инженерия — 28 678 атак за квартал, +49,75% к I кв.")
    chan = pd.DataFrame({
        "Канал": ["Карты", "Счета (ДБО)", "СБП", "Эл. кошельки", "Без открытия счёта"],
        "Сумма, млрд ₽": [1.30, 2.17, 2.74, 0.06, 0.25],
        "Кол-во, тыс. оп.": [237.03, 84.02, 129.06, 6.00, 1.76]})
    c1, c2 = st.columns(2)
    c1.plotly_chart(px.bar(chan, x="Канал", y="Сумма, млрд ₽", title="Хищения по каналам, II кв. 2026 (ЦБ)"))
    c2.plotly_chart(px.bar(chan, x="Канал", y="Кол-во, тыс. оп.", title="Количество ОБДС"))
    st.write(f"Синтетический датасет: **{len(df):,}** операций, фрода **{df.is_fraud.mean():.2%}** (seed=42).")

with tab2:
    st.header("Этапы процесса")
    for s in STAGES:
        st.write("- " + s)
    st.subheader("RACI")
    st.dataframe(pd.DataFrame(RACI, columns=RACI_COLS), hide_index=True)
    st.subheader("Блоки: назначение / вход / выход")
    st.dataframe(pd.DataFrame(BLOCKS), hide_index=True)

with tab3:
    st.header("Симулятор операции")
    preset = st.radio("Пресет", ["Вручную", "История Никиты (легитимно, R09+R05)",
                                 "Бабушка и мошенники (соц. инженерия)"], horizontal=True)
    manual = preset == "Вручную"
    c1, c2, c3 = st.columns(3)
    amount = c1.number_input("Сумма, ₽", 100, 5_000_000,
                             90_000 if preset.startswith("История") else
                             300_000 if preset.startswith("Бабушка") else 20_000, step=1000)
    age55 = c1.checkbox("Клиент 55+", value=preset.startswith("Бабушка"))
    new_rec = c2.checkbox("Новый получатель", value=not manual)
    phone = c2.checkbox("Смена номера за 48 ч (R09)", value=preset.startswith("История"))
    new_dev = c2.checkbox("Новое устройство", value=False)
    night = c3.checkbox("Ночное время", value=False)
    atyp = c3.checkbox("Нетипичная сумма (R05)", value=not manual)
    social = c3.checkbox("Сигнал сторонней организации (R06)",
                         value=preset.startswith("Бабушка"))
    cbr = c1.checkbox("Получатель в базе ЦБ (R01)", value=False)
    guardian = c2.checkbox("Включена «Защита близких»", value=preset.startswith("Бабушка"))

    tx = {"amount": amount, "age_55plus": age55, "new_recipient": new_rec,
          "phone_changed_48h": phone, "new_device": new_dev, "is_night": night,
          "hour": 2 if night else 14, "is_atypical": atyp or phone,
          "third_party_signal": social, "nspk_signal": False,
          "recipient_in_cbr_db": cbr, "recipient_in_bank_db": False,
          "recipient_criminal_case": False, "recipient_in_gis": False,
          "device_in_cbr_db": False, "device_risk_factors": False, "atm_nfc_timeout": False,
          "self_transfer_amount": 250_000 if preset.startswith("Бабушка") else 0,
          "self_transfer_hours_ago": 3 if preset.startswith("Бабушка") else 999,
    "recipient_relation_months": 12,
          "atm_digital_card_deposit": False, "recipient_crossborder_24h_amount": 0,
          "data_lag": False, "guardian_enabled": guardian}
    row = pd.Series({**{k: 0 for k in ["amount"]}, **tx})
    score = scorer.score(row)
    reasons = scorer.reasons(row)
    d_new = decide(tx, risk_score=score, reasons=reasons)
    d_base = decide(tx, baseline=True)

    m1, m2 = st.columns(2)
    m1.metric("Risk score", f"{score:.2f}")
    m1.write("Причины: " + (", ".join(reasons) or "—"))
    m1.write("Сработавшие правила: " + (", ".join(d_new.rules_hit) or "нет"))
    m2.metric("Решение", d_new.action)
    m2.metric("Время трения (наше / baseline)",
              f"{d_new.friction_minutes:.0f} мин / {d_base.friction_minutes:.0f} мин")
    if d_new.action != "pass":
        st.info(client_text(d_new))
    else:
        st.success("Операция проходит без трения.")

with tab4:
    st.header("Baseline (только правила, жёсткая остановка) vs Наше решение")
    b, s = kpi["baseline"], kpi["solution"]
    rows = [
        ("Объём пропущенных хищений, ₽", f"{b.missed_amount:,.0f}", f"{s.missed_amount:,.0f}"),
        ("Корректно выявлено (TP)", f"{b.tp}", f"{s.tp}"),
        ("Полнота (recall)", f"{b.recall:.1%}", f"{s.recall:.1%}"),
        ("Доля ложных сигналов FP/(TP+FP)", f"{b.false_alarm_share:.1%}", f"{s.false_alarm_share:.1%}"),
        ("Ошибочно ограничено операций (шт)", f"{b.wrong_restricted_count}", f"{s.wrong_restricted_count}"),
        ("Доля ошибочно ограниченных среди законных", f"{b.wrong_restricted_share:.2%}",
         f"{s.wrong_restricted_share:.2%}"),
        ("Среднее время трения, мин", f"{b.avg_friction_minutes:.1f}", f"{s.avg_friction_minutes:.1f}"),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["KPI", "Baseline", "Решение"]), hide_index=True)

with tab5:
    st.header("Экономика")
    scen = st.select_slider("Сценарий", list(CONFIG.economics.scenario_multipliers), "Базовый")
    rep = build_report(b, s, scenario=scen)
    if not rep.budget_ok:
        st.error(f"Бюджет превышен: {rep.total_cost:,.0f} ₽ > {CONFIG.economics.budget_cap:,.0f} ₽")
    c1, c2, c3 = st.columns(3)
    c1.metric("Затраты на внедрение", f"{rep.total_cost/1e6:.1f} млн ₽")
    c2.metric("Эффект за год", f"{rep.annual_effect/1e6:.1f} млн ₽")
    c3.metric("ROI (год 1)", f"{rep.roi:.0%}")
    c1.metric("NPV (3 года)", f"{rep.npv/1e6:.1f} млн ₽")
    c2.metric("Окупаемость", f"{rep.payback_months:.1f} мес" if rep.payback_months != float("inf") else "—")
    c3.metric("Δ NPS (допущение)", f"+{rep.nps_delta:.2f} п.п.")
    st.subheader("Затраты по статьям")
    st.dataframe(pd.DataFrame(rep.costs.items(), columns=["Статья", "₽"]), hide_index=True)
    st.subheader("Эффект по источникам")
    st.dataframe(pd.DataFrame(rep.effect_parts.items(), columns=["Источник", "₽/год"]), hide_index=True)
    st.subheader("Допущения")
    st.dataframe(pd.DataFrame(rep.assumptions, columns=["Допущение", "Значение", "Обоснование"]),
                 hide_index=True)

with tab6:
    st.header("Сроки: 6 месяцев")
    st.plotly_chart(gantt_figure())

with tab7:
    st.header("Экспорт сводки для отчёта")
    md = f"""# Сводка цифр (данные синтетические, экономика — допущения)

## KPI (baseline → решение)
- Пропущенные хищения: {b.missed_amount:,.0f} → {s.missed_amount:,.0f} ₽
- Предотвращено: {b.prevented_amount:,.0f} → {s.prevented_amount:,.0f} ₽
- TP: {b.tp} → {s.tp}; recall: {b.recall:.1%} → {s.recall:.1%}
- Доля ложных сигналов: {b.false_alarm_share:.1%} → {s.false_alarm_share:.1%}
- Ошибочно ограничено: {b.wrong_restricted_count} → {s.wrong_restricted_count} оп.
- Среднее трение: {b.avg_friction_minutes:.1f} → {s.avg_friction_minutes:.1f} мин

## Экономика (базовый сценарий)
- Затраты: {rep.total_cost:,.0f} ₽; эффект/год: {rep.annual_effect:,.0f} ₽
- ROI: {rep.roi:.0%}; NPV 3 года: {rep.npv:,.0f} ₽; окупаемость: {rep.payback_months:.1f} мес

## Допущения
""" + "\n".join(f"- {a}: {v} ({o})" for a, v, o in rep.assumptions)
    st.download_button("Скачать сводку (Markdown)", md, "summary.md")
    st.download_button("Скачать датасет (CSV)", df.to_csv(index=False), "transactions.csv")
