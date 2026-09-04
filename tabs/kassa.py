import json
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


def render_kassa_tab(selected_date, can_edit):
    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, ви переглядаєте цей день в режимі «Тільки читання»."
        )

    start_balance = get_int(get_start_balance(selected_date))
    st.text_input(
        "Залишок на початок дня (автоматично):",
        value=str(start_balance),
        disabled=True,
    )

    st.divider()
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("📈Надходження:")
        inc_df = prepare_df(
            st.session_state["inc_data"], ["Категорія", "Сума", "Примітка"]
        )
        edited_inc_df = st.data_editor(
            inc_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn(
                    "Стаття надходження",
                    options=INCOME_CATEGORIES,
                    required=True,
                ),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1
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
            f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {subtotal_inc} грн</p>",
            unsafe_allow_html=True,
        )

    with col_t2:
        st.subheader("📉Витрати:")
        exp_df = prepare_df(
            st.session_state["exp_data"], ["Категорія", "Сума", "Примітка"]
        )
        edited_exp_df = st.data_editor(
            exp_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn(
                    "Стаття витрат", options=EXPENSE_CHOICES, required=True
                ),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1
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
            f"<p style='font-weight: bold; color: #c62828;'>Загалом: {subtotal_exp} грн</p>",
            unsafe_allow_html=True,
        )

    st.divider()
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.subheader("💸Аванси:")
        adv_df = prepare_df(
            st.session_state["adv_data"],
            ["Співробітник", "Сума", "Примітка"],
        )
        edited_adv_df = st.data_editor(
            adv_df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"adv_editor_{selected_date}",
            disabled=not can_edit,
        )
        subtotal_adv = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {subtotal_adv} грн</p>",
            unsafe_allow_html=True,
        )

    with col_b2:
        st.subheader("💰Факт")
        m_coins = get_int(
            st.text_input(
                "Монети (загальна сума):",
                placeholder="0",
                key=f"coins_live_{selected_date}",
                disabled=not can_edit,
            )
        )
        st.markdown('<div class="fact-block">', unsafe_allow_html=True)

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
        st.markdown("</div>", unsafe_allow_html=True)

        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.markdown(f"## 💵Разом в касі: {cash_pure} грн")

    st.divider()
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

    st.write("")

    # Сохраняем текущее состояние для кнопки сохранения плавающего меню
    st.session_state["kassa_current_payload"] = {
        "edited_inc_df": edited_inc_df,
        "edited_exp_df": edited_exp_df,
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
                    "exp": sanitize_df(edited_exp_df),
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
                    for _, r in edited_exp_df.iterrows():
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
