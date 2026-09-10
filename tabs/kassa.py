import json
import textwrap
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, headers, INCOME_CATEGORIES, EXPENSE_CHOICES
from utils import (
    log_audit,
    get_start_balance,
    get_int,
    sanitize_df,
    prepare_df,
    save_kassa_draft_to_supabase,
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
SHORT_EXPENSE_CHOICES = [""]  # Начинаем с пустой строки для чистых ячеек

for full_cat in EXPENSE_CHOICES:
    short_cat = get_short_cat(full_cat)
    if short_cat and short_cat not in SHORT_EXPENSE_CHOICES:
        SHORT_EXPENSE_CHOICES.append(short_cat)
        EXPENSE_SHORT_TO_FULL[short_cat] = full_cat

EXPENSE_FULL_TO_SHORT = {v: k for k, v in EXPENSE_SHORT_TO_FULL.items()}

INCOME_CHOICES = [""] + [c for c in INCOME_CATEGORIES if c]


def clean_df_for_editor(df):
    """Безопасная очистка DataFrame от 'None' и 'nan' без ошибок типов в pandas."""
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


def render_kassa_tab(selected_date, can_edit):
    # CSS для превращения контейнеров в воздушные мягкие карточки
    st.markdown(
        textwrap.dedent("""
        <style>
            /* Белые карточки на бежевом фоне */
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background-color: #ffffff !important;
                border-radius: 16px !important;
                border: 1px solid #eaeaea !important;
                padding: 18px 22px !important;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02) !important;
                margin-bottom: 12px !important;
            }
            /* Мягкая рамка вокруг внутренних таблиц */
            div[data-testid="stDataEditor"] {
                border-radius: 10px !important;
                border: 1px solid #f3f4f6 !important;
                box-shadow: none !important;
            }
        </style>
        """),
        unsafe_allow_html=True,
    )

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, ви переглядаєте цей день в режимі «Тільки читання»."
        )

    start_balance = get_int(get_start_balance(selected_date))

    # --- 1. БЛОК: "НА ПОЧАТОК ДНЯ" ---
    st.markdown(
        textwrap.dedent(f"""
        <div style="display: flex; align-items: center; gap: 12px; margin-top: 4px; margin-bottom: 16px;">
            <span style="font-size: 20px; font-weight: 700; color: #111827;">🏦 На початок дня:</span>
            <span style="
                background-color: #ffffff; 
                padding: 6px 18px; 
                border-radius: 10px; 
                border: 1px solid #eaeaea; 
                font-size: 20px; 
                font-weight: 800; 
                color: #111827; 
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
            ">
                {start_balance} грн
            </span>
        </div>
        """),
        unsafe_allow_html=True,
    )

    # --- 2. БЛОКИ: НАДХОДЖЕННЯ ТА ВИ ТРАТИ ---
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        with st.container(border=True):
            inc_header = st.empty()
            inc_df = prepare_df(
                st.session_state["inc_data"], ["Категорія", "Сума", "Примітка"]
            )
            inc_df = clean_df_for_editor(inc_df)

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
            subtotal_inc = sum(
                get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows()
            )
            inc_header.markdown(
                textwrap.dedent(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span style="font-size: 19px; font-weight: 700; color: #111827;">📈 Надходження</span>
                    <span style="background-color: #e8f5e9; color: #2e7d32; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 14px;">
                        {subtotal_inc} грн
                    </span>
                </div>
                """),
                unsafe_allow_html=True,
            )

    with col_t2:
        with st.container(border=True):
            exp_header = st.empty()
            exp_df = prepare_df(
                st.session_state["exp_data"], ["Категорія", "Сума", "Примітка"]
            )
            exp_df = clean_df_for_editor(exp_df)

            if "Категорія" in exp_df.columns:
                exp_df["Категорія"] = exp_df["Категорія"].map(
                    lambda x: EXPENSE_FULL_TO_SHORT.get(str(x).strip(), get_short_cat(x))
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
            subtotal_exp = sum(
                get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows()
            )
            exp_header.markdown(
                textwrap.dedent(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span style="font-size: 19px; font-weight: 700; color: #111827;">📉 Витрати</span>
                    <span style="background-color: #ffebee; color: #c62828; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 14px;">
                        {subtotal_exp} грн
                    </span>
                </div>
                """),
                unsafe_allow_html=True,
            )

    # --- 3. БЛОКИ: АВАНСИ ТА ФАКТ ---
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        with st.container(border=True):
            adv_header = st.empty()
            adv_df = prepare_df(
                st.session_state["adv_data"],
                ["Співробітник", "Сума", "Примітка"],
            )
            adv_df = clean_df_for_editor(adv_df)

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
            adv_header.markdown(
                textwrap.dedent(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span style="font-size: 19px; font-weight: 700; color: #111827;">💸 Аванси</span>
                    <span style="background-color: #fff3e0; color: #ef6c00; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 14px;">
                        {subtotal_adv} грн
                    </span>
                </div>
                """),
                unsafe_allow_html=True,
            )

    with col_b2:
        with st.container(border=True):
            fact_header = st.empty()

            fc1, fc2 = st.columns(2)

            with fc1:
                m_coins = get_int(
                    st.text_input(
                        "🪙 Монети (сума)",
                        placeholder="0",
                        key=f"coins_live_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_20 = get_int(
                    st.text_input(
                        "💵 20 грн",
                        placeholder="0",
                        key=f"qty_20_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_50 = get_int(
                    st.text_input(
                        "💵 50 грн",
                        placeholder="0",
                        key=f"qty_50_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_100 = get_int(
                    st.text_input(
                        "💵 100 грн",
                        placeholder="0",
                        key=f"qty_100_{selected_date}",
                        disabled=not can_edit,
                    )
                )

            with fc2:
                q_200 = get_int(
                    st.text_input(
                        "💵 200 грн",
                        placeholder="0",
                        key=f"qty_200_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_500 = get_int(
                    st.text_input(
                        "💵 500 грн",
                        placeholder="0",
                        key=f"qty_500_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_1000 = get_int(
                    st.text_input(
                        "💵 1000 грн",
                        placeholder="0",
                        key=f"qty_1000_{selected_date}",
                        disabled=not can_edit,
                    )
                )
                q_2000 = get_int(
                    st.text_input(
                        "💵 2000 грн",
                        placeholder="0",
                        key=f"qty_2000_{selected_date}",
                        disabled=not can_edit,
                    )
                )

            v_20 = q_20 * 20
            v_50 = q_50 * 50
            v_100 = q_100 * 100
            v_200 = q_200 * 200
            v_500 = q_500 * 500
            v_1000 = q_1000 * 1000
            v_2000 = q_2000 * 2000

            cash_pure = (
                m_coins
                + v_20
                + v_50
                + v_100
                + v_200
                + v_500
                + v_1000
                + v_2000
            )

            fact_header.markdown(
                textwrap.dedent(f"""
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span style="font-size: 19px; font-weight: 700; color: #111827;">💰 Факт</span>
                    <span style="background-color: #e8f5e9; color: #2e7d32; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 14px;">
                        {cash_pure} грн
                    </span>
                </div>
                """),
                unsafe_allow_html=True,
            )

    # --- 4. БЛОК: ПІДСУМКИ ЗМІНИ ---
    calculated_end = start_balance + subtotal_inc - subtotal_exp
    total_actual = cash_pure + subtotal_adv
    discrepancy = total_actual - calculated_end

    if discrepancy == 0:
        disc_color = "#2e7d32"  # Зеленый
        disc_bg = "#e8f5e9"
        disc_border = "#c8e6c9"
        disc_title = "Зійшлася"
        disc_val = "0 грн"
    elif discrepancy > 0:
        disc_color = "#ef6c00"  # Оранжевый
        disc_bg = "#fff3e0"
        disc_border = "#ffe0b2"
        disc_title = "Надлишок"
        disc_val = f"+{discrepancy} грн"
    else:
        disc_color = "#c62828"  # Красный
        disc_bg = "#ffebee"
        disc_border = "#ffcdd2"
        disc_title = "Різниця (нестача)"
        disc_val = f"{discrepancy} грн"

    with st.container(border=True):
        st.markdown(
            '<div style="font-size: 19px; font-weight: 700; color: #111827; margin-bottom: 14px;">🏁 Підсумки зміни</div>',
            unsafe_allow_html=True,
        )

        res_c1, res_c2, res_c3 = st.columns(3)

        with res_c1:
            st.markdown(
                textwrap.dedent(f"""
                <div style="background-color: #fafafa; padding: 12px 16px; border-radius: 12px; border: 1px solid #e5e7eb;">
                    <div style="font-size: 13px; font-weight: 600; color: #6b7280; margin-bottom: 4px;">Розрахунок</div>
                    <div style="font-size: 24px; font-weight: 800; color: #111827;">{calculated_end} грн</div>
                </div>
                """),
                unsafe_allow_html=True,
            )

        with res_c2:
            st.markdown(
                textwrap.dedent(f"""
                <div style="background-color: #fafafa; padding: 12px 16px; border-radius: 12px; border: 1px solid #e5e7eb;">
                    <div style="font-size: 13px; font-weight: 600; color: #6b7280; margin-bottom: 4px;">Факт</div>
                    <div style="font-size: 24px; font-weight: 800; color: #111827;">{total_actual} грн</div>
                </div>
                """),
                unsafe_allow_html=True,
            )

        with res_c3:
            st.markdown(
                textwrap.dedent(f"""
                <div style="background-color: {disc_bg}; padding: 12px 16px; border-radius: 12px; border: 1px solid {disc_border};">
                    <div style="font-size: 13px; font-weight: 700; color: {disc_color}; margin-bottom: 4px;">{disc_title}</div>
                    <div style="font-size: 24px; font-weight: 800; color: {disc_color};">{disc_val}</div>
                </div>
                """),
                unsafe_allow_html=True,
            )

    # Перевод коротких наименований обратно в полные категории перед сохранением
    exp_df_full = edited_exp_df.copy()
    if "Категорія" in exp_df_full.columns:
        exp_df_full["Категорія"] = exp_df_full["Категорія"].map(
            lambda x: EXPENSE_SHORT_TO_FULL.get(str(x).strip(), str(x).strip())
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
            "2000": q_2000,
        },
    }

    # --- 5. КНОПКА ЗБЕРЕЖЕННЯ ---
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
                        "2000": q_2000,
                    },
                }
                try:
                    json.dumps(payload)
                except Exception as e:
                    st.error(f"❌ Помилка символів: {e}")
                    st.stop()

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
