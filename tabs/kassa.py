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
    """Извлекает подкатегорию после стрелки ➔ или ->."""
    if not cat_str or pd.isna(cat_str):
        return ""
    cat_str = str(cat_str).strip()
    if "➔" in cat_str:
        return cat_str.split("➔")[-1].strip()
    elif "->" in cat_str:
        return cat_str.split("->")[-1].strip()
    return cat_str


# --- АВТОМАППИНГ КАТЕГОРИЙ ---
EXPENSE_SHORT_TO_FULL = {}
SHORT_EXPENSE_CHOICES = [""]

for full_cat in EXPENSE_CHOICES:
    short_cat = get_short_cat(full_cat)
    if short_cat and short_cat not in SHORT_EXPENSE_CHOICES:
        SHORT_EXPENSE_CHOICES.append(short_cat)
        EXPENSE_SHORT_TO_FULL[short_cat] = full_cat

EXPENSE_FULL_TO_SHORT = {v: k for k, v in EXPENSE_SHORT_TO_FULL.items()}
INCOME_CHOICES = [""] + [c for c in INCOME_CATEGORIES if c]


def clean_df_for_editor(df):
    """Безопасная очистка DataFrame от 'None' и 'nan'."""
    df = df.copy()
    for col in df.columns:
        if col == "Сума":
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = (
                df[col]
                .fillna("")
                .astype(str)
                .replace(["None", "nan", "NaN", "<NA>", "NoneType", "none"], "")
            )
    return df


# ============================================================
# РЕНДЕР КАССЫ (ИЗОЛИРОВАННЫЙ ФРАГМЕНТ — БЕЗ МЕРЦАНИЯ)
# ============================================================
@st.fragment
def render_kassa_tab(selected_date, can_edit):
    # Современные стабильные стили (БЕЗ ломающих layout отступов)
    st.markdown(
        """
        <style>
            /* Скрываем служебные маркдаун-контейнеры со стилями */
            div[data-testid="stElementContainer"]:has(> div > style) {
                display: none !important;
            }
            
            /* 1. УМЕНЬШАЕМ ВЕРХНИЙ ОТСТУП ВНУТРИ КАРТОЧЕК */
            div[data-testid="stVerticalBlockBorderWrapper"] {
                padding-top: 10px !important;
                padding-bottom: 10px !important;
            }

            /* 2. ПОДТЯГИВАЕМ ЗАГОЛОВОК К ВЕРХУ И ТАБЛИЦУ К ЗАГОЛОВКУ */
            div[data-testid="stElementContainer"]:has(h4) {
                margin-top: -4px !important;
                margin-bottom: -12px !important;
            }

            /* 3. ПОДТЯГИВАЕМ ПЛАШКИ ВПРИТЫК К ТАБЛИЦАМ */
            div[data-testid="stElementContainer"]:has(.subtotal-inc),
            div[data-testid="stElementContainer"]:has(.subtotal-exp),
            div[data-testid="stElementContainer"]:has(.subtotal-adv) {
                margin-top: -16px !important;
            }

            /* 4. ОТСТУП ДЛЯ ФАКТА КАССЫ */
            div[data-testid="stElementContainer"]:has(.subtotal-cash) {
                margin-top: 6px !important;
            }

            /* Премиальная карточка кассы (шапка) */
            .kassa-card-header {
                background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                padding: 14px 20px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                box-shadow: 0 4px 12px rgba(15, 23, 42, 0.03);
                margin-bottom: 16px;
            }

            /* ОБЩИЕ СТИЛИ ПЛАШЕК ИТОГОВ */
            .subtotal-badge {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 8px 14px;
                border-radius: 10px;
                font-size: 14px;
                font-weight: 700;
            }
            .subtotal-inc { background-color: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
            .subtotal-exp { background-color: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
            .subtotal-adv { background-color: #fff7ed; color: #c2410c; border: 1px solid #ffedd5; }
            .subtotal-cash { background-color: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; }

            /* Кнопка сохранения */
            div[data-testid="stButton"] > button {
                background: #1E3557 !important;
                border: none !important;
                border-radius: 12px !important;
                padding: 0.8rem 1.2rem !important;
                box-shadow: 0 4px 14px rgba(30, 53, 87, 0.25) !important;
                transition: all 0.2s ease-in-out !important;
            }
            div[data-testid="stButton"] > button * {
                color: #ffffff !important;
                font-weight: 800 !important;
                font-size: 15px !important;
                letter-spacing: 0.4px !important;
            }
            div[data-testid="stButton"] > button:hover {
                background: #14243b !important;
                transform: translateY(-1px);
                box-shadow: 0 6px 18px rgba(30, 53, 87, 0.35) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, ви переглядаєте цей день в режимі «Тільки читання»."
        )

    start_balance = get_int(get_start_balance(selected_date))

    # --- КЭШИРОВАНИЕ ДАТАФРЕЙМОВ (Защита от пересоздания таблиц) ---
    cache_key = f"kassa_dfs_{selected_date}"
    if cache_key not in st.session_state:
        inc_init = clean_df_for_editor(
            prepare_df(
                st.session_state.get("inc_data", []),
                ["Категорія", "Сума", "Примітка"],
            )
        )
        exp_init = clean_df_for_editor(
            prepare_df(
                st.session_state.get("exp_data", []),
                ["Категорія", "Сума", "Примітка"],
            )
        )
        if "Категорія" in exp_init.columns:
            exp_init["Категорія"] = exp_init["Категорія"].map(
                lambda x: EXPENSE_FULL_TO_SHORT.get(
                    str(x).strip(), get_short_cat(x)
                )
            )
        adv_init = clean_df_for_editor(
            prepare_df(
                st.session_state.get("adv_data", []),
                ["Співробітник", "Сума", "Примітка"],
            )
        )

        st.session_state[cache_key] = {
            "inc": inc_init,
            "exp": exp_init,
            "adv": adv_init,
        }

    dfs = st.session_state[cache_key]

    # --- 1. ШАПКА КАССЫ ---
    st.markdown(
        f"""
        <div class="kassa-card-header">
            <span style="font-size: 18px; font-weight: 700; color: #1e293b;">🏦 Каса на початок дня</span>
            <span style="font-size: 22px; font-weight: 800; color: #0f172a;">{start_balance:,} грн</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- 2. СЕКЦИЯ: НАДХОДЖЕННЯ И ВИТРАТИ ---
    c_inc, c_exp = st.columns(2)

    with c_inc:
        with st.container(border=True):
            st.markdown(
                "<h4 style='margin:0 0 10px 0; color:#166534;'>📈 Надходження</h4>",
                unsafe_allow_html=True,
            )
            edited_inc_df = st.data_editor(
                dfs["inc"],
                column_config={
                    "Категорія": st.column_config.SelectboxColumn(
                        "Стаття", options=INCOME_CHOICES, required=False
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
            subtotal_inc = sum(
                get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows()
            )
            st.markdown(
                f"""
                <div class="subtotal-badge subtotal-inc">
                    <span>Загалом надходжень:</span>
                    <span>{subtotal_inc:,} грн</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with c_exp:
        with st.container(border=True):
            st.markdown(
                "<h4 style='margin:0 0 10px 0; color:#991b1b;'>📉 Витрати</h4>",
                unsafe_allow_html=True,
            )
            edited_exp_df = st.data_editor(
                dfs["exp"],
                column_config={
                    "Категорія": st.column_config.SelectboxColumn(
                        "Стаття", options=SHORT_EXPENSE_CHOICES, required=False
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
            subtotal_exp = sum(
                get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows()
            )
            st.markdown(
                f"""
                <div class="subtotal-badge subtotal-exp">
                    <span>Загалом витрат:</span>
                    <span>{subtotal_exp:,} грн</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # --- 3. СЕКЦИЯ: АВАНСЫ И ФАКТ КАССЫ ---
    c_adv, c_fact = st.columns(2)

    with c_adv:
        with st.container(border=True):
            st.markdown(
                "<h4 style='margin:0 0 10px 0; color:#9a3412;'>💸 Аванси</h4>",
                unsafe_allow_html=True,
            )
            edited_adv_df = st.data_editor(
                dfs["adv"],
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
                f"""
                <div class="subtotal-badge subtotal-adv">
                    <span>Загалом авансів:</span>
                    <span>{subtotal_adv:,} грн</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with c_fact:
        with st.container(border=True):
            st.markdown(
                "<h4 style='margin:0 0 10px 0; color:#075985;'>💰 Факт каси (купюри)</h4>",
                unsafe_allow_html=True,
            )
            fc1, fc2 = st.columns(2)
            with fc1:
                m_coins = get_int(
                    st.text_input(
                        "🪙 Монети",
                        placeholder="0",
                        key=f"coins_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_20 = get_int(
                    st.text_input(
                        "💵 20 грн",
                        placeholder="0",
                        key=f"q20_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_50 = get_int(
                    st.text_input(
                        "💵 50 грн",
                        placeholder="0",
                        key=f"q50_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_100 = get_int(
                    st.text_input(
                        "💵 100 грн",
                        placeholder="0",
                        key=f"q100_{selected_date}",
                        disabled=not can_edit,
                    )
                )

            with fc2:
                q_200 = get_int(
                    st.text_input(
                        "💵 200 грн",
                        placeholder="0",
                        key=f"q200_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_500 = get_int(
                    st.text_input(
                        "💵 500 грн",
                        placeholder="0",
                        key=f"q500_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_1000 = get_int(
                    st.text_input(
                        "💵 1000 грн",
                        placeholder="0",
                        key=f"q1000_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_2000 = get_int(
                    st.text_input(
                        "💵 2000 грн",
                        placeholder="0",
                        key=f"q2000_{selected_date}",
                        disabled=not can_edit,
                    )
                )

            cash_pure = (
                m_coins
                + q_20 * 20
                + q_50 * 50
                + q_100 * 100
                + q_200 * 200
                + q_500 * 500
                + q_1000 * 1000
                + q_2000 * 2000
            )
            st.markdown(
                f"""
                <div class="subtotal-badge subtotal-cash">
                    <span>Разом готівки:</span>
                    <span>{cash_pure:,} грн</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # --- 4. СЕКЦИЯ: ИТОГИ ЗМЕНИ ---
    calculated_end = start_balance + subtotal_inc - subtotal_exp
    total_actual = cash_pure + subtotal_adv
    discrepancy = total_actual - calculated_end

    if discrepancy == 0:
        disc_color, disc_bg, disc_title, disc_val = (
            "#15803d",
            "#f0fdf4",
            "Зійшлася",
            "0 грн",
        )
    elif discrepancy > 0:
        disc_color, disc_bg, disc_title, disc_val = (
            "#c2410c",
            "#fff7ed",
            "Надлишок",
            f"+{discrepancy:,} грн",
        )
    else:
        disc_color, disc_bg, disc_title, disc_val = (
            "#b91c1c",
            "#fef2f2",
            "Різниця (нестача)",
            f"{discrepancy:,} грн",
        )

    with st.container(border=True):
        st.markdown(
            "<h4 style='margin:0 0 12px 0; color:#0f172a;'>🏁 Підсумки зміни</h4>",
            unsafe_allow_html=True,
        )
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.markdown(
                f"""
                <div style="background:#f8fafc; padding:12px 16px; border-radius:10px; border:1px solid #e2e8f0;">
                    <div style="font-size:12px; font-weight:600; color:#64748b;">Розрахунок</div>
                    <div style="font-size:22px; font-weight:800; color:#0f172a;">{calculated_end:,} грн</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with rc2:
            st.markdown(
                f"""
                <div style="background:#f8fafc; padding:12px 16px; border-radius:10px; border:1px solid #e2e8f0;">
                    <div style="font-size:12px; font-weight:600; color:#64748b;">Факт (готівка + аванси)</div>
                    <div style="font-size:22px; font-weight:800; color:#0f172a;">{total_actual:,} грн</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with rc3:
            st.markdown(
                f"""
                <div style="background:{disc_bg}; padding:12px 16px; border-radius:10px; border:1px solid {disc_color};">
                    <div style="font-size:12px; font-weight:700; color:{disc_color};">{disc_title}</div>
                    <div style="font-size:22px; font-weight:800; color:{disc_color};">{disc_val}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # --- 5. КНОПКА СОХРАНЕНИЯ ---
    if can_edit:
        st.write("")
        if st.button(
            "🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ",
            type="primary",
            use_container_width=True,
        ):
            exp_df_full = edited_exp_df.copy()
            if "Категорія" in exp_df_full.columns:
                exp_df_full["Категорія"] = exp_df_full["Категорія"].map(
                    lambda x: EXPENSE_SHORT_TO_FULL.get(
                        str(x).strip(), str(x).strip()
                    )
                )

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
                        "2000": q_2000,
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

                st.session_state.pop(cache_key, None)

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
                    inc_rows = []
                    for _, r in edited_inc_df.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        cat = str(r.get("Категорія", "")).strip()
                        note = str(r.get("Примітка", "")).strip()
                        if amt or cat:
                            inc_rows.append({
                                "date": selected_date,
                                "type": "income",
                                "description": f"{cat} | {note}"
                                if note
                                else cat,
                                "amount": str(amt),
                            })

                    exp_rows = []
                    for _, r in exp_df_full.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        cat = str(r.get("Категорія", "")).strip()
                        note = str(r.get("Примітка", "")).strip()
                        if amt or cat:
                            exp_rows.append({
                                "date": selected_date,
                                "type": "expense",
                                "description": f"{cat} | {note}"
                                if note
                                else cat,
                                "amount": str(amt),
                            })

                    adv_rows = []
                    for _, r in edited_adv_df.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        emp = str(r.get("Співробітник", "")).strip()
                        raw_note = r.get("Примітка", "")
                        safe_note = (
                            str(raw_note).strip()
                            if pd.notna(raw_note)
                            and str(raw_note).lower() != "nan"
                            else ""
                        )
                        if amt or emp:
                            adv_rows.append({
                                "date": selected_date,
                                "employee": emp,
                                "amount": str(amt),
                                "note": safe_note,
                            })

                    if inc_rows:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/transactions",
                            headers=headers,
                            json=inc_rows,
                        )
                    if exp_rows:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/transactions",
                            headers=headers,
                            json=exp_rows,
                        )
                    if adv_rows:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/advances",
                            headers=headers,
                            json=adv_rows,
                        )

                    log_audit(
                        "Збережено фінальний звіт", f"Дата: {selected_date}"
                    )
                    st.success("🎉 Звіт успішно збережено в хмарі!")
                else:
                    st.error(f"❌ Помилка: {res_shift.text}")
