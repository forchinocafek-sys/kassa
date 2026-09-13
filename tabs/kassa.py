import json
import textwrap
import pandas as pd
import requests
import streamlit as st
from config import EXPENSE_CHOICES, INCOME_CATEGORIES, SUPABASE_URL, headers
from utils import (
    get_int,
    get_start_balance,
    log_audit,
    prepare_df,
    sanitize_df,
)


def get_short_cat(cat_str):
    if not cat_str or pd.isna(cat_str):
        return ""
    cat_str = str(cat_str).strip()
    if "➔" in cat_str:
        return cat_str.split("➔")[-1].strip()
    elif "->" in cat_str:
        return cat_str.split("->")[-1].strip()
    return cat_str


EXPENSE_SHORT_TO_FULL = {}
SHORT_EXPENSE_CHOICES = [""]

for full_cat in EXPENSE_CHOICES:
    short_cat = get_short_cat(full_cat)
    if short_cat and short_cat not in SHORT_EXPENSE_CHOICES:
        SHORT_EXPENSE_CHOICES.append(short_cat)
        EXPENSE_SHORT_TO_FULL[short_cat] = full_cat

EXPENSE_FULL_TO_SHORT = {v: k for k, v in EXPENSE_SHORT_TO_FULL.items()}
INCOME_CHOICES = [""] + [c for c in INCOME_CATEGORIES if c]


def render_kassa_tab(selected_date, can_edit):
    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, ви переглядаєте цей день в режимі «Тільки читання»."
        )

    start_balance = get_int(get_start_balance(selected_date))

    # --- 1. БЛОК: НА ПОЧАТОК ДНЯ ---
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
            <span style="font-size: 20px; font-weight: 700; color: #111827;">🏦 На початок дня:</span>
            <span style="background-color: #ffffff; padding: 6px 18px; border-radius: 10px; border: 1px solid #eaeaea; font-size: 20px; font-weight: 800; color: #111827;">
                {start_balance} грн
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # --- 2. ТАБЛИЦЫ ДОХОДОВ И РАСХОДОВ ---
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.subheader("📈 Надходження")
        inc_df = prepare_df(
            st.session_state["inc_data"], ["Категорія", "Сума", "Примітка"]
        )

        edited_inc_df = st.data_editor(
            inc_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn(
                    "Стаття надходження",
                    options=INCOME_CHOICES,
                    required=False,
                ),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1, format="%d грн"
                ),
                "Примітка": st.column_config.TextColumn("Деталі"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key=f"inc_editor_{selected_date}",
            disabled=not can_edit,
        )

        # Вывод итогов СТРОГО ПОД таблицей (как в старом коде)
        subtotal_inc = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: 800; font-size: 16px; color: #2e7d32; margin-top: 4px;'>Загалом надходжень: {subtotal_inc} грн</p>",
            unsafe_allow_html=True,
        )

    with col_t2:
        st.subheader("📉 Витрати")
        exp_df = prepare_df(
            st.session_state["exp_data"], ["Категорія", "Сума", "Примітка"]
        )

        edited_exp_df = st.data_editor(
            exp_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn(
                    "Стаття витрат",
                    options=SHORT_EXPENSE_CHOICES,
                    required=False,
                ),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1, format="%d грн"
                ),
                "Примітка": st.column_config.TextColumn("Деталі"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key=f"exp_editor_{selected_date}",
            disabled=not can_edit,
        )

        # Вывод итогов СТРОГО ПОД таблицей
        subtotal_exp = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: 800; font-size: 16px; color: #c62828; margin-top: 4px;'>Загалом витрат: {subtotal_exp} грн</p>",
            unsafe_allow_html=True,
        )

    st.divider()

    # --- 3. АВАНСЫ И ФАКТ ---
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.subheader("💸 Аванси")
        adv_df = prepare_df(
            st.session_state["adv_data"],
            ["Співробітник", "Сума", "Примітка"],
        )

        edited_adv_df = st.data_editor(
            adv_df,
            column_config={
                "Співробітник": st.column_config.TextColumn("Співробітник"),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1, format="%d грн"
                ),
                "Примітка": st.column_config.TextColumn("Деталі"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key=f"adv_editor_{selected_date}",
            disabled=not can_edit,
        )

        subtotal_adv = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: 800; font-size: 16px; color: #ef6c00; margin-top: 4px;'>Загалом авансів: {subtotal_adv} грн</p>",
            unsafe_allow_html=True,
        )

    with col_b2:
        st.subheader("💰 Факт")
        m_coins = get_int(
            st.text_input(
                "Монети (загальна сума):",
                placeholder="0",
                key=f"coins_live_{selected_date}",
                disabled=not can_edit,
            )
        )

        def cash_row(label, mult):
            c1, c2 = st.columns([1, 4])
            with c1:
                st.markdown(
                    f"<div style='margin-top:8px;font-weight:bold;'>{label}</div>",
                    unsafe_allow_html=True,
                )
            with c2:
                qty = get_int(
                    st.text_input(
                        f"q{label}",
                        label_visibility="collapsed",
                        placeholder="0",
                        key=f"qty_{label}_{selected_date}",
                        disabled=not can_edit,
                    )
                )
            return qty, qty * mult

        q_20, v_20 = cash_row("20", 20)
        q_50, v_50 = cash_row("50", 50)
        q_100, v_100 = cash_row("100", 100)
        q_200, v_200 = cash_row("200", 200)
        q_500, v_500 = cash_row("500", 500)
        q_1000, v_1000 = cash_row("1000", 1000)

        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.markdown(
            f"<h3 style='margin-top: 12px;'>💵 Разом в касі: {cash_pure} грн</h3>",
            unsafe_allow_html=True,
        )

    st.divider()

    # --- 4. ИТОГИ ---
    calculated_end = start_balance + subtotal_inc - subtotal_exp
    total_actual = cash_pure + subtotal_adv
    discrepancy = total_actual - calculated_end

    st.subheader("🏁 Підсумки зміни")
    res_c1, res_c2, res_c3 = st.columns(3)
    res_c1.metric("Розрахунок", f"{calculated_end} грн")
    res_c2.metric("Факт", f"{total_actual} грн")

    if discrepancy == 0:
        res_c3.success("Зійшлася!")
    elif discrepancy > 0:
        res_c3.warning(f"+{discrepancy} грн")
    else:
        res_c3.error(f"{discrepancy} грн")

    # --- 5. СОХРАНЕНИЕ ---
    exp_df_full = edited_exp_df.copy()
    if "Категорія" in exp_df_full.columns:
        exp_df_full["Категорія"] = exp_df_full["Категорія"].map(
            lambda x: EXPENSE_SHORT_TO_FULL.get(
                str(x).strip(), str(x).strip()
            )
        )

    st.session_state["kassa_current_payload"] = {
        "edited_inc_df": edited_inc_df,
        "edited_exp_df": exp_df_full,
        "edited_adv_df": edited_adv_df,
        "m_coins": m_coins,
        "q_dict": {
            "20": q_20,
            "50": q_50,
            "100": q_100,
            "200": q_200,
            "500": q_500,
            "1000": q_1000,
        },
    }

    if can_edit:
        if st.button(
            "🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Стерилізація та відправка звіту..."):
                payload = {
                    "inc": sanitize_df(edited_inc_df),
                    "exp": sanitize_df(exp_df_full),
                    "adv": sanitize_df(edited_adv_df),
                    "cash": {
                        "coins": m_coins,
                        "20": q_20,
                        "50": q_50,
                        "100": q_100,
                        "200": q_200,
                        "500": q_500,
                        "1000": q_1000,
                    },
                }

                check_draft = requests.get(
                    f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}",
                    headers=headers,
                ).json()
                if isinstance(check_draft, list) and len(check_draft) > 0:
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}",
                        headers=headers,
                        json={"payload": payload},
                    )
                else:
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/drafts",
                        headers=headers,
                        json={"date": selected_date, "payload": payload},
                    )

                st.session_state["drafts_cache"][selected_date] = payload
                st.cache_data.clear()

                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}",
                    headers=headers,
                )
                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}",
                    headers=headers,
                )
                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}",
                    headers=headers,
                )

                res_shift = requests.post(
                    f"{SUPABASE_URL}/rest/v1/shifts",
                    headers=headers,
                    json={
                        "date": selected_date,
                        "start_balance": str(start_balance),
                        "calculated_end": str(calculated_end),
                        "actual_end": str(total_actual),
                    },
                )

                if res_shift.status_code in [200, 201]:
                    log_audit(
                        "Збережено фінальний звіт", f"Дата: {selected_date}"
                    )
                    st.success("🎉 Звіт успішно збережено в хмарі!")
                else:
                    st.error(f"❌ Помилка: {res_shift.text}")
