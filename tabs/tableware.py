import time
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, headers
from utils import log_audit, get_int, sanitize_df


def render_tableware_tab(selected_date, can_edit):
    st.subheader("🍽️ Управление посудой и инвентарем")

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, перегляд у режимі «Тільки читання»."
        )

    tab_inv, tab_ops, tab_fin = st.tabs(
        [
            "📋 1. Зведена інвентаризація",
            "⚡ 2. Прихід, Бой та Борги",
            "💰 3. Фінансовий облік втрат",
        ]
    )

    # Загрузка справочника посуды
    catalog_items = []
    catalog_dict = {}
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/tableware_catalog?select=*&order=name.asc",
            headers=headers,
        )
        if res.status_code == 200 and isinstance(res.json(), list):
            catalog_items = res.json()
            catalog_dict = {it["id"]: it["name"] for it in catalog_items}
    except Exception:
        pass

    # -------------------------------------------------------------------
    # ВЕК 1: СВЕДЕННАЯ ИНВЕНТАРИЗАЦИЯ
    # -------------------------------------------------------------------
    with tab_inv:
        default_date_obj = (
            datetime.strptime(selected_date, "%Y-%m-%d").date()
            if isinstance(selected_date, str)
            else selected_date
        )

        col_date, _ = st.columns([1, 2])
        with col_date:
            inv_date = st.date_input(
                "📅 Дата інвентаризації:",
                value=default_date_obj,
                format="DD/MM/YYYY",
                key="tableware_inv_date_picker",
            )
            inv_date_str = inv_date.strftime("%Y-%m-%d")

        draft_session_key = f"tableware_inv_draft_{inv_date_str}"
        supabase_draft_date = f"tableware_{inv_date_str}"

        # Загрузка черновика фактических остатков
        if draft_session_key not in st.session_state:
            st.session_state[draft_session_key] = {}
            try:
                res_draft = requests.get(
                    f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                    headers=headers,
                ).json()
                if isinstance(res_draft, list) and len(res_draft) > 0:
                    saved_payload = res_draft[0].get("payload", {})
                    st.session_state[draft_session_key] = {
                        int(k): v for k, v in saved_payload.items() if str(k).isdigit()
                    }
            except Exception:
                pass

        # Загрузка приходов и боев из журнала операций
        events_summary = {}
        try:
            res_ev = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?select=*",
                headers=headers,
            ).json()
            if isinstance(res_ev, list):
                for ev in res_ev:
                    item_id = ev.get("item_id")
                    if item_id not in events_summary:
                        events_summary[item_id] = {"arrived": 0, "broken": 0}
                    if ev.get("event_type") == "delivery":
                        events_summary[item_id]["arrived"] += get_int(ev.get("qty", 0))
                    elif ev.get("event_type") == "breakage":
                        events_summary[item_id]["broken"] += get_int(ev.get("qty", 0))
        except Exception:
            pass

        if not catalog_items:
            st.info("ℹ️ Справочник посуды пуст. Добавьте позиции внизу страницы.")
        else:
            df = pd.DataFrame(catalog_items)
            df["cost_price"] = df["cost_price"].apply(get_int)
            df["prev_month_qty"] = df["prev_month_qty"].apply(get_int)

            # Автоматические столбцы Приїхало и Розбилося
            df["arrived"] = df["id"].map(lambda x: events_summary.get(x, {}).get("arrived", 0))
            df["broken"] = df["id"].map(lambda x: events_summary.get(x, {}).get("broken", 0))

            # Фактический остаток из черновика
            df["fact_qty"] = df["id"].map(
                lambda x: st.session_state[draft_session_key].get(x, 0)
            )

            # Расчетные поля
            df["calc_qty"] = df["prev_month_qty"] + df["arrived"] - df["broken"]
            df["diff"] = df["fact_qty"] - df["calc_qty"]
            df["shortage_uah"] = df.apply(
                lambda r: abs(r["diff"]) * r["cost_price"] if r["diff"] < 0 else 0, axis=1
            )
            df["surplus_uah"] = df.apply(
                lambda r: r["diff"] * r["cost_price"] if r["diff"] > 0 else 0, axis=1
            )

            c_dr1, c_dr2, c_dr3 = st.columns([2, 2, 3])
            with c_dr1:
                if st.button("💾 Сохранить черновик", type="primary", use_container_width=True, disabled=not can_edit):
                    try:
                        draft_payload = {
                            str(k): v for k, v in st.session_state[draft_session_key].items()
                        }
                        check_draft = requests.get(
                            f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                            headers=headers,
                        ).json()

                        if isinstance(check_draft, list) and len(check_draft) > 0:
                            requests.patch(
                                f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                                headers=headers,
                                json={"payload": draft_payload},
                            )
                        else:
                            requests.post(
                                f"{SUPABASE_URL}/rest/v1/drafts",
                                headers=headers,
                                json={"date": supabase_draft_date, "payload": draft_payload},
                            )
                        log_audit("Збережено чернетку посуду", f"Дата: {inv_date_str}")
                        st.toast("✅ Черновик сохранен в облаке!", icon="💾")
                    except Exception as e:
                        st.error(f"Ошибка сохранения: {e}")

            with c_dr2:
                if st.button("🗑️ Очистить ввод", use_container_width=True, disabled=not can_edit):
                    st.session_state[draft_session_key] = {}
                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                        headers=headers,
                    )
                    st.rerun()

            with c_dr3:
                filled_count = sum(1 for v in st.session_state[draft_session_key].values() if v > 0)
                st.markdown(f"**Введено позиций:** `{filled_count} из {len(df)}`")

            st.write("")

            edited_df = st.data_editor(
                df[
                    [
                        "id",
                        "name",
                        "cost_price",
                        "prev_month_qty",
                        "arrived",
                        "broken",
                        "calc_qty",
                        "fact_qty",
                        "diff",
                        "shortage_uah",
                        "surplus_uah",
                    ]
                ],
                column_config={
                    "id": None,
                    "name": st.column_config.TextColumn("Найменування", disabled=True, width="large"),
                    "cost_price": st.column_config.NumberColumn("Ціна", disabled=True, width="small"),
                    "prev_month_qty": st.column_config.NumberColumn("Минулий", disabled=True, width="small"),
                    "arrived": st.column_config.NumberColumn("Приїхало (авто)", disabled=True, width="small"),
                    "broken": st.column_config.NumberColumn("Розбилося (авто)", disabled=True, width="small"),
                    "calc_qty": st.column_config.NumberColumn("Розрахунок", disabled=True, width="small"),
                    "fact_qty": st.column_config.NumberColumn("Факт (шт)", min_value=0, step=1, required=True, width="small"),
                    "diff": st.column_config.NumberColumn("Різниця", disabled=True, width="small"),
                    "shortage_uah": st.column_config.NumberColumn("Минус (грн)", disabled=True, width="small"),
                    "surplus_uah": st.column_config.NumberColumn("Плюс (грн)", disabled=True, width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key=f"tableware_editor_{inv_date_str}",
                disabled=not can_edit,
            )

            for _, r in edited_df.iterrows():
                st.session_state[draft_session_key][r["id"]] = get_int(r["fact_qty"])

            tot_shortage = edited_df["shortage_uah"].sum()
            tot_surplus = edited_df["surplus_uah"].sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("Всього позицій", len(edited_df))
            m2.metric("Сума недостачі", f"{tot_shortage} грн")
            m3.metric("Сума надлишків", f"{tot_surplus} грн")

            st.write("")
            if can_edit:
                if st.button("🚀 Зберегти фінальну інвентаризацію", type="primary", use_container_width=True):
                    payload_data = sanitize_df(edited_df)
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_inventories",
                        headers=headers,
                        json={
                            "date": inv_date_str,
                            "created_by": st.session_state["user_name"],
                            "payload": payload_data,
                            "total_shortage_uah": int(tot_shortage),
                            "total_surplus_uah": int(tot_surplus),
                        },
                    )

                    for _, r in edited_df.iterrows():
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{r['id']}",
                            headers=headers,
                            json={"prev_month_qty": get_int(r["fact_qty"])},
                        )

                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                        headers=headers,
                    )
                    st.session_state[draft_session_key] = {}

                    log_audit("Збережено фінальну інвентаризацію посуду", f"Дата: {inv_date_str}")
                    st.success("🎉 Інвентаризацію успішно збережено!")
                    time.sleep(1)
                    st.rerun()

    # -------------------------------------------------------------------
    # ВЕК 2: ЖУРНАЛ ОПЕРАЦИЙ (ПРИХОД / БОЙ / ДОЛГИ)
    # -------------------------------------------------------------------
    with tab_ops:
        st.markdown("### ⚡ Оформление операций")

        # Загрузка списка персонала
        staff_list = []
        try:
            res_w = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_waiters?select=*&order=name.asc",
                headers=headers,
            ).json()
            if isinstance(res_w, list):
                staff_list = [w["name"] for w in res_w]
        except Exception:
            pass

        col_op1, col_op2 = st.columns(2)

        # --- 1. ПРИХОД ПОСУДЫ ---
        with col_op1:
            st.markdown("#### 📦 1. Приход посуды (Поставка)")
            if catalog_items and can_edit:
                item_map = {f"{it['name']} (сейчас: {it['cost_price']} грн)": it for it in catalog_items}
                sel_item_label = st.selectbox("Выберите позицию", options=list(item_map.keys()), key="arr_item_sel")
                target_item = item_map[sel_item_label]

                arr_qty = st.number_input("Количество приехало (шт)", min_value=1, step=1, value=1, key="arr_qty_input")
                new_price = st.number_input("Актуальная цена за шт (грн)", min_value=0, step=1, value=target_item["cost_price"], key="arr_price_input")

                if st.button("➕ Оформить приход", type="primary", use_container_width=True):
                    tot_amount = arr_qty * new_price
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_events",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "item_id": target_item["id"],
                            "event_type": "delivery",
                            "qty": arr_qty,
                            "unit_price": new_price,
                            "total_amount": tot_amount,
                        },
                    )
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{target_item['id']}",
                        headers=headers,
                        json={"cost_price": new_price},
                    )
                    log_audit("Оформлено приход посуды", f"{target_item['name']} - {arr_qty} шт по {new_price} грн")
                    st.success("✅ Приход оформлен, цена в справочнике обновлена!")
                    time.sleep(1)
                    st.rerun()

        # --- 2. ФИКСАЦИЯ БОЯ ---
        with col_op2:
            st.markdown("#### 💥 2. Фиксация боя / скола")
            if catalog_items and can_edit:
                item_map_br = {f"{it['name']} ({it['cost_price']} грн/шт)": it for it in catalog_items}
                sel_br_label = st.selectbox("Выберите позицию", options=list(item_map_br.keys()), key="br_item_sel")
                br_item = item_map_br[sel_br_label]

                br_qty = st.number_input("Количество разбито (шт)", min_value=1, step=1, value=1, key="br_qty_input")
                resp_type = st.radio("Кто разбил / Причина:", options=["Персонал", "Гость", "Случайный скол"], horizontal=True)

                staff_name = ""
                if resp_type == "Персонал":
                    if not staff_list:
                        st.warning("⚠️ Справочник персонала пуст. Добавьте сотрудника ниже!")
                    else:
                        staff_name = st.selectbox("Выберите сотрудника", options=staff_list)

                if st.button("💥 Зафиксировать бой", type="primary", use_container_width=True):
                    unit_p = br_item["cost_price"]
                    tot_val = br_qty * unit_p

                    w_debt = 0
                    paid_val = 0
                    unpaid_val = 0

                    if resp_type == "Персонал":
                        w_debt = int(tot_val * 0.5)  # 50% персонал
                        unpaid_val = int(tot_val * 0.5)  # 50% заведение
                    elif resp_type == "Гость":
                        paid_val = tot_val  # 100% гость
                    else:  # Случайный скол
                        unpaid_val = tot_val  # 100% заведение

                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_events",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "item_id": br_item["id"],
                            "event_type": "breakage",
                            "qty": br_qty,
                            "unit_price": unit_p,
                            "total_amount": tot_val,
                            "responsible_type": resp_type,
                            "waiter_name": staff_name,
                            "waiter_debt": w_debt,
                            "paid_amount": paid_val,
                            "unpaid_amount": unpaid_val,
                        },
                    )
                    log_audit("Зафиксирован бой посуды", f"{br_item['name']} x{br_qty} ({resp_type})")
                    st.success("✅ Бой зафиксирован!")
                    time.sleep(1)
                    st.rerun()

        st.divider()

        # --- 3. ОБЩАЯ ВЕДОМОСТЬ БОЯ ЗА МЕСЯЦ ---
        st.markdown("### 📋 Общая ведомость боя за месяц")

        months = {
            "Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4,
            "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8,
            "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12,
        }
        col_m1, col_y1 = st.columns(2)
        sel_m_name = col_m1.selectbox("Выберите месяц для отчета", list(months.keys()), index=st.session_state["form_date"].month - 1)
        sel_y_num = col_y1.selectbox("Выберите год", [2025, 2026, 2027], index=1, key="rep_year_sel")

        m_idx = months[sel_m_name]
        start_d = f"{sel_y_num}-{m_idx:02d}-01"
        end_d = f"{sel_y_num+1}-01-01" if m_idx == 12 else f"{sel_y_num}-{m_idx+1:02d}-01"

        try:
            res_breakage = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?event_type=eq.breakage&date=gte.{start_d}&date=lt.{end_d}&order=date.desc",
                headers=headers,
            ).json()

            if isinstance(res_breakage, list) and len(res_breakage) > 0:
                rows = []
                tot_pcs = 0
                tot_sum = 0
                tot_guest = 0
                tot_staff_debt = 0
                tot_venue_loss = 0

                for b in res_breakage:
                    item_name = catalog_dict.get(b.get("item_id"), "Удаленная позиция")
                    qty = get_int(b.get("qty", 0))
                    u_price = get_int(b.get("unit_price", 0))
                    tot = get_int(b.get("total_amount", 0))
                    resp = str(b.get("responsible_type", ""))
                    person = str(b.get("waiter_name", "")) if b.get("waiter_name") else "-"
                    p_guest = get_int(b.get("paid_amount", 0))
                    d_staff = get_int(b.get("waiter_debt", 0))
                    unpaid = get_int(b.get("unpaid_amount", 0))

                    tot_pcs += qty
                    tot_sum += tot
                    tot_guest += p_guest
                    tot_staff_debt += d_staff
                    tot_venue_loss += unpaid

                    rows.append({
                        "Дата": b.get("date"),
                        "Посуда": item_name,
                        "К-во (шт)": qty,
                        "Цена (грн)": u_price,
                        "Сумма (грн)": tot,
                        "Причина / Кто": resp,
                        "Сотрудник": person,
                        "Оплачено гостем": p_guest,
                        "Долг персонала": d_staff,
                        "Списано на заведение": unpaid,
                    })

                df_br_report = pd.DataFrame(rows)

                m_b1, m_b2, m_b3, m_b4 = st.columns(4)
                m_b1.metric("Всего разбито", f"{tot_pcs} шт ({tot_sum} грн)")
                m_b2.metric("Оплачено гостями", f"{tot_guest} грн")
                m_b3.metric("Долг персонала (50%)", f"{tot_staff_debt} грн")
                m_b4.metric("Потери заведения", f"{tot_venue_loss} грн")

                st.dataframe(df_br_report, hide_index=True, use_container_width=True)
            else:
                st.info(f"ℹ️ В {sel_m_name} {sel_y_num} г. случаев боя не зафиксировано.")
        except Exception as e:
            st.error(f" Ошибка загрузки отчета: {e}")

        st.divider()

        # --- 4. ДОЛГИ ПЕРСОНАЛА И УПРАВЛЕНИЕ СОСТАВОМ ---
        col_w1, col_w2 = st.columns([2, 1])

        with col_w1:
            st.markdown("#### 🧾 Ведомость долгов персонала за бой (50%)")
            try:
                res_debts = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_events?event_type=eq.breakage&waiter_debt=gt.0",
                    headers=headers,
                ).json()
                if isinstance(res_debts, list) and len(res_debts) > 0:
                    df_debts = pd.DataFrame(res_debts)
                    summary_debts = df_debts.groupby("waiter_name")["waiter_debt"].sum().reset_index()
                    summary_debts.columns = ["Сотрудник", "Сумма долга (грн)"]
                    st.dataframe(summary_debts, hide_index=True, use_container_width=True)
                else:
                    st.info("🎉 Действующих долгов персонала нет!")
            except Exception:
                pass

        with col_w2:
            st.markdown("#### 👤 Персонал")
            if can_edit:
                with st.form("add_waiter_form", clear_on_submit=True):
                    new_w_name = st.text_input("Имя сотрудника")
                    if st.form_submit_button("➕ Добавить"):
                        if new_w_name.strip():
                            requests.post(
                                f"{SUPABASE_URL}/rest/v1/tableware_waiters",
                                headers=headers,
                                json={"name": new_w_name.strip()},
                            )
                            st.success("Добавлено!")
                            time.sleep(1)
                            st.rerun()

    import time
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, headers
from utils import log_audit, get_int, sanitize_df


def render_tableware_tab(selected_date, can_edit):
    st.subheader("🍽️ Управление посудой и инвентарем")

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, перегляд у режимі «Тільки читання»."
        )

    tab_inv, tab_ops, tab_fin = st.tabs(
        [
            "📋 1. Зведена інвентаризація",
            "⚡ 2. Прихід, Бой та Борги",
            "💰 3. Фінансовий облік втрат",
        ]
    )

    # Загрузка справочника посуды
    catalog_items = []
    catalog_dict = {}
    try:
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/tableware_catalog?select=*&order=name.asc",
            headers=headers,
        )
        if res.status_code == 200 and isinstance(res.json(), list):
            catalog_items = res.json()
            catalog_dict = {it["id"]: it["name"] for it in catalog_items}
    except Exception:
        pass

    # -------------------------------------------------------------------
    # ВЕК 1: СВЕДЕННАЯ ИНВЕНТАРИЗАЦИЯ
    # -------------------------------------------------------------------
    with tab_inv:
        default_date_obj = (
            datetime.strptime(selected_date, "%Y-%m-%d").date()
            if isinstance(selected_date, str)
            else selected_date
        )

        col_date, _ = st.columns([1, 2])
        with col_date:
            inv_date = st.date_input(
                "📅 Дата інвентаризації:",
                value=default_date_obj,
                format="DD/MM/YYYY",
                key="tableware_inv_date_picker",
            )
            inv_date_str = inv_date.strftime("%Y-%m-%d")

        draft_session_key = f"tableware_inv_draft_{inv_date_str}"
        supabase_draft_date = f"tableware_{inv_date_str}"

        # Загрузка черновика фактических остатков
        if draft_session_key not in st.session_state:
            st.session_state[draft_session_key] = {}
            try:
                res_draft = requests.get(
                    f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                    headers=headers,
                ).json()
                if isinstance(res_draft, list) and len(res_draft) > 0:
                    saved_payload = res_draft[0].get("payload", {})
                    st.session_state[draft_session_key] = {
                        int(k): v for k, v in saved_payload.items() if str(k).isdigit()
                    }
            except Exception:
                pass

        # Загрузка приходов и боев из журнала операций
        events_summary = {}
        try:
            res_ev = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?select=*",
                headers=headers,
            ).json()
            if isinstance(res_ev, list):
                for ev in res_ev:
                    item_id = ev.get("item_id")
                    if item_id not in events_summary:
                        events_summary[item_id] = {"arrived": 0, "broken": 0}
                    if ev.get("event_type") == "delivery":
                        events_summary[item_id]["arrived"] += get_int(ev.get("qty", 0))
                    elif ev.get("event_type") == "breakage":
                        events_summary[item_id]["broken"] += get_int(ev.get("qty", 0))
        except Exception:
            pass

        if not catalog_items:
            st.info("ℹ️ Справочник посуды пуст. Добавьте позиции внизу страницы.")
        else:
            df = pd.DataFrame(catalog_items)
            df["cost_price"] = df["cost_price"].apply(get_int)
            df["prev_month_qty"] = df["prev_month_qty"].apply(get_int)

            # Автоматические столбцы Приїхало и Розбилося
            df["arrived"] = df["id"].map(lambda x: events_summary.get(x, {}).get("arrived", 0))
            df["broken"] = df["id"].map(lambda x: events_summary.get(x, {}).get("broken", 0))

            # Фактический остаток из черновика
            df["fact_qty"] = df["id"].map(
                lambda x: st.session_state[draft_session_key].get(x, 0)
            )

            # Расчетные поля
            df["calc_qty"] = df["prev_month_qty"] + df["arrived"] - df["broken"]
            df["diff"] = df["fact_qty"] - df["calc_qty"]
            df["shortage_uah"] = df.apply(
                lambda r: abs(r["diff"]) * r["cost_price"] if r["diff"] < 0 else 0, axis=1
            )
            df["surplus_uah"] = df.apply(
                lambda r: r["diff"] * r["cost_price"] if r["diff"] > 0 else 0, axis=1
            )

            c_dr1, c_dr2, c_dr3 = st.columns([2, 2, 3])
            with c_dr1:
                if st.button("💾 Сохранить черновик", type="primary", use_container_width=True, disabled=not can_edit):
                    try:
                        draft_payload = {
                            str(k): v for k, v in st.session_state[draft_session_key].items()
                        }
                        check_draft = requests.get(
                            f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                            headers=headers,
                        ).json()

                        if isinstance(check_draft, list) and len(check_draft) > 0:
                            requests.patch(
                                f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                                headers=headers,
                                json={"payload": draft_payload},
                            )
                        else:
                            requests.post(
                                f"{SUPABASE_URL}/rest/v1/drafts",
                                headers=headers,
                                json={"date": supabase_draft_date, "payload": draft_payload},
                            )
                        log_audit("Збережено чернетку посуду", f"Дата: {inv_date_str}")
                        st.toast("✅ Черновик сохранен в облаке!", icon="💾")
                    except Exception as e:
                        st.error(f"Ошибка сохранения: {e}")

            with c_dr2:
                if st.button("🗑️ Очистить ввод", use_container_width=True, disabled=not can_edit):
                    st.session_state[draft_session_key] = {}
                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                        headers=headers,
                    )
                    st.rerun()

            with c_dr3:
                filled_count = sum(1 for v in st.session_state[draft_session_key].values() if v > 0)
                st.markdown(f"**Введено позиций:** `{filled_count} из {len(df)}`")

            st.write("")

            edited_df = st.data_editor(
                df[
                    [
                        "id",
                        "name",
                        "cost_price",
                        "prev_month_qty",
                        "arrived",
                        "broken",
                        "calc_qty",
                        "fact_qty",
                        "diff",
                        "shortage_uah",
                        "surplus_uah",
                    ]
                ],
                column_config={
                    "id": None,
                    "name": st.column_config.TextColumn("Найменування", disabled=True, width="large"),
                    "cost_price": st.column_config.NumberColumn("Ціна", disabled=True, width="small"),
                    "prev_month_qty": st.column_config.NumberColumn("Минулий", disabled=True, width="small"),
                    "arrived": st.column_config.NumberColumn("Приїхало (авто)", disabled=True, width="small"),
                    "broken": st.column_config.NumberColumn("Розбилося (авто)", disabled=True, width="small"),
                    "calc_qty": st.column_config.NumberColumn("Розрахунок", disabled=True, width="small"),
                    "fact_qty": st.column_config.NumberColumn("Факт (шт)", min_value=0, step=1, required=True, width="small"),
                    "diff": st.column_config.NumberColumn("Різниця", disabled=True, width="small"),
                    "shortage_uah": st.column_config.NumberColumn("Минус (грн)", disabled=True, width="small"),
                    "surplus_uah": st.column_config.NumberColumn("Плюс (грн)", disabled=True, width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key=f"tableware_editor_{inv_date_str}",
                disabled=not can_edit,
            )

            for _, r in edited_df.iterrows():
                st.session_state[draft_session_key][r["id"]] = get_int(r["fact_qty"])

            tot_shortage = edited_df["shortage_uah"].sum()
            tot_surplus = edited_df["surplus_uah"].sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("Всього позицій", len(edited_df))
            m2.metric("Сума недостачі", f"{tot_shortage} грн")
            m3.metric("Сума надлишків", f"{tot_surplus} грн")

            st.write("")
            if can_edit:
                if st.button("🚀 Зберегти фінальну інвентаризацію", type="primary", use_container_width=True):
                    payload_data = sanitize_df(edited_df)
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_inventories",
                        headers=headers,
                        json={
                            "date": inv_date_str,
                            "created_by": st.session_state["user_name"],
                            "payload": payload_data,
                            "total_shortage_uah": int(tot_shortage),
                            "total_surplus_uah": int(tot_surplus),
                        },
                    )

                    for _, r in edited_df.iterrows():
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{r['id']}",
                            headers=headers,
                            json={"prev_month_qty": get_int(r["fact_qty"])},
                        )

                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                        headers=headers,
                    )
                    st.session_state[draft_session_key] = {}

                    log_audit("Збережено фінальну інвентаризацію посуду", f"Дата: {inv_date_str}")
                    st.success("🎉 Інвентаризацію успішно збережено!")
                    time.sleep(1)
                    st.rerun()

    # -------------------------------------------------------------------
    # ВЕК 2: ЖУРНАЛ ОПЕРАЦИЙ (ПРИХОД / БОЙ / ДОЛГИ)
    # -------------------------------------------------------------------
    with tab_ops:
        st.markdown("### ⚡ Оформление операций")

        # Загрузка списка персонала
        staff_list = []
        try:
            res_w = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_waiters?select=*&order=name.asc",
                headers=headers,
            ).json()
            if isinstance(res_w, list):
                staff_list = [w["name"] for w in res_w]
        except Exception:
            pass

        col_op1, col_op2 = st.columns(2)

        # --- 1. ПРИХОД ПОСУДЫ ---
        with col_op1:
            st.markdown("#### 📦 1. Приход посуды (Поставка)")
            if catalog_items and can_edit:
                item_map = {f"{it['name']} (сейчас: {it['cost_price']} грн)": it for it in catalog_items}
                sel_item_label = st.selectbox("Выберите позицию", options=list(item_map.keys()), key="arr_item_sel")
                target_item = item_map[sel_item_label]

                arr_qty = st.number_input("Количество приехало (шт)", min_value=1, step=1, value=1, key="arr_qty_input")
                new_price = st.number_input("Актуальная цена за шт (грн)", min_value=0, step=1, value=target_item["cost_price"], key="arr_price_input")

                if st.button("➕ Оформить приход", type="primary", use_container_width=True):
                    tot_amount = arr_qty * new_price
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_events",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "item_id": target_item["id"],
                            "event_type": "delivery",
                            "qty": arr_qty,
                            "unit_price": new_price,
                            "total_amount": tot_amount,
                        },
                    )
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{target_item['id']}",
                        headers=headers,
                        json={"cost_price": new_price},
                    )
                    log_audit("Оформлено приход посуды", f"{target_item['name']} - {arr_qty} шт по {new_price} грн")
                    st.success("✅ Приход оформлен, цена в справочнике обновлена!")
                    time.sleep(1)
                    st.rerun()

        # --- 2. ФИКСАЦИЯ БОЯ ---
        with col_op2:
            st.markdown("#### 💥 2. Фиксация боя / скола")
            if catalog_items and can_edit:
                item_map_br = {f"{it['name']} ({it['cost_price']} грн/шт)": it for it in catalog_items}
                sel_br_label = st.selectbox("Выберите позицию", options=list(item_map_br.keys()), key="br_item_sel")
                br_item = item_map_br[sel_br_label]

                br_qty = st.number_input("Количество разбито (шт)", min_value=1, step=1, value=1, key="br_qty_input")
                resp_type = st.radio("Кто разбил / Причина:", options=["Персонал", "Гость", "Случайный скол"], horizontal=True)

                staff_name = ""
                if resp_type == "Персонал":
                    if not staff_list:
                        st.warning("⚠️ Справочник персонала пуст. Добавьте сотрудника ниже!")
                    else:
                        staff_name = st.selectbox("Выберите сотрудника", options=staff_list)

                if st.button("💥 Зафиксировать бой", type="primary", use_container_width=True):
                    unit_p = br_item["cost_price"]
                    tot_val = br_qty * unit_p

                    w_debt = 0
                    paid_val = 0
                    unpaid_val = 0

                    if resp_type == "Персонал":
                        w_debt = int(tot_val * 0.5)  # 50% персонал
                        unpaid_val = int(tot_val * 0.5)  # 50% заведение
                    elif resp_type == "Гость":
                        paid_val = tot_val  # 100% гость
                    else:  # Случайный скол
                        unpaid_val = tot_val  # 100% заведение

                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_events",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "item_id": br_item["id"],
                            "event_type": "breakage",
                            "qty": br_qty,
                            "unit_price": unit_p,
                            "total_amount": tot_val,
                            "responsible_type": resp_type,
                            "waiter_name": staff_name,
                            "waiter_debt": w_debt,
                            "paid_amount": paid_val,
                            "unpaid_amount": unpaid_val,
                        },
                    )
                    log_audit("Зафиксирован бой посуды", f"{br_item['name']} x{br_qty} ({resp_type})")
                    st.success("✅ Бой зафиксирован!")
                    time.sleep(1)
                    st.rerun()

        st.divider()

        # --- 3. ОБЩАЯ ВЕДОМОСТЬ БОЯ ЗА МЕСЯЦ ---
        st.markdown("### 📋 Общая ведомость боя за месяц")

        months = {
            "Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4,
            "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8,
            "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12,
        }
        col_m1, col_y1 = st.columns(2)
        sel_m_name = col_m1.selectbox("Выберите месяц для отчета", list(months.keys()), index=st.session_state["form_date"].month - 1)
        sel_y_num = col_y1.selectbox("Выберите год", [2025, 2026, 2027], index=1, key="rep_year_sel")

        m_idx = months[sel_m_name]
        start_d = f"{sel_y_num}-{m_idx:02d}-01"
        end_d = f"{sel_y_num+1}-01-01" if m_idx == 12 else f"{sel_y_num}-{m_idx+1:02d}-01"

        try:
            res_breakage = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?event_type=eq.breakage&date=gte.{start_d}&date=lt.{end_d}&order=date.desc",
                headers=headers,
            ).json()

            if isinstance(res_breakage, list) and len(res_breakage) > 0:
                rows = []
                tot_pcs = 0
                tot_sum = 0
                tot_guest = 0
                tot_staff_debt = 0
                tot_venue_loss = 0

                for b in res_breakage:
                    item_name = catalog_dict.get(b.get("item_id"), "Удаленная позиция")
                    qty = get_int(b.get("qty", 0))
                    u_price = get_int(b.get("unit_price", 0))
                    tot = get_int(b.get("total_amount", 0))
                    resp = str(b.get("responsible_type", ""))
                    person = str(b.get("waiter_name", "")) if b.get("waiter_name") else "-"
                    p_guest = get_int(b.get("paid_amount", 0))
                    d_staff = get_int(b.get("waiter_debt", 0))
                    unpaid = get_int(b.get("unpaid_amount", 0))

                    tot_pcs += qty
                    tot_sum += tot
                    tot_guest += p_guest
                    tot_staff_debt += d_staff
                    tot_venue_loss += unpaid

                    rows.append({
                        "Дата": b.get("date"),
                        "Посуда": item_name,
                        "К-во (шт)": qty,
                        "Цена (грн)": u_price,
                        "Сумма (грн)": tot,
                        "Причина / Кто": resp,
                        "Сотрудник": person,
                        "Оплачено гостем": p_guest,
                        "Долг персонала": d_staff,
                        "Списано на заведение": unpaid,
                    })

                df_br_report = pd.DataFrame(rows)

                m_b1, m_b2, m_b3, m_b4 = st.columns(4)
                m_b1.metric("Всего разбито", f"{tot_pcs} шт ({tot_sum} грн)")
                m_b2.metric("Оплачено гостями", f"{tot_guest} грн")
                m_b3.metric("Долг персонала (50%)", f"{tot_staff_debt} грн")
                m_b4.metric("Потери заведения", f"{tot_venue_loss} грн")

                st.dataframe(df_br_report, hide_index=True, use_container_width=True)
            else:
                st.info(f"ℹ️ В {sel_m_name} {sel_y_num} г. случаев боя не зафиксировано.")
        except Exception as e:
            st.error(f" Ошибка загрузки отчета: {e}")

        st.divider()

        # --- 4. ДОЛГИ ПЕРСОНАЛА И УПРАВЛЕНИЕ СОСТАВОМ ---
        col_w1, col_w2 = st.columns([2, 1])

        with col_w1:
            st.markdown("#### 🧾 Ведомость долгов персонала за бой (50%)")
            try:
                res_debts = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_events?event_type=eq.breakage&waiter_debt=gt.0",
                    headers=headers,
                ).json()
                if isinstance(res_debts, list) and len(res_debts) > 0:
                    df_debts = pd.DataFrame(res_debts)
                    summary_debts = df_debts.groupby("waiter_name")["waiter_debt"].sum().reset_index()
                    summary_debts.columns = ["Сотрудник", "Сумма долга (грн)"]
                    st.dataframe(summary_debts, hide_index=True, use_container_width=True)
                else:
                    st.info("🎉 Действующих долгов персонала нет!")
            except Exception:
                pass

        with col_w2:
            st.markdown("#### 👤 Персонал")
            if can_edit:
                with st.form("add_waiter_form", clear_on_submit=True):
                    new_w_name = st.text_input("Имя сотрудника")
                    if st.form_submit_button("➕ Добавить"):
                        if new_w_name.strip():
                            requests.post(
                                f"{SUPABASE_URL}/rest/v1/tableware_waiters",
                                headers=headers,
                                json={"name": new_w_name.strip()},
                            )
                            st.success("Добавлено!")
                            time.sleep(1)
                            st.rerun()

    # -------------------------------------------------------------------
    # ВЕК 3: ФИНАНСОВЫЙ УЧЕТ ПОТЕРЬ
    # -------------------------------------------------------------------
    with tab_fin:
        st.markdown("##### 📊 Итоговый финансовый баланс за месяц")

        months_fin = {
            "Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4,
            "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8,
            "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12,
        }
        c_m, c_y = st.columns(2)
        sel_m = c_m.selectbox("Місяць", list(months_fin.keys()), index=st.session_state["form_date"].month - 1, key="fin_month_sel")
        sel_y = c_y.selectbox("Рік", [2025, 2026, 2027], index=1, key="fin_year_sel")

        m_num = months_fin[sel_m]
        start_d = f"{sel_y}-{m_num:02d}-01"
        end_d = f"{sel_y+1}-01-01" if m_num == 12 else f"{sel_y}-{m_num+1:02d}-01"

        auto_paid_breakage = 0
        auto_unpaid_breakage = 0

        try:
            res_m_events = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?date=gte.{start_d}&date=lt.{end_d}&event_type=eq.breakage",
                headers=headers,
            ).json()
            if isinstance(res_m_events, list):
                for ev in res_m_events:
                    auto_paid_breakage += get_int(ev.get("paid_amount", 0)) + get_int(ev.get("waiter_debt", 0))
                    auto_unpaid_breakage += get_int(ev.get("unpaid_amount", 0))
        except Exception:
            pass

        m_calc1, m_calc2 = st.columns(2)
        m_calc1.metric("Бой (Оплачено / Удержано)", f"{auto_paid_breakage} грн")
        m_calc2.metric("Бой (Не оплачено / За счет заведения)", f"{auto_unpaid_breakage} грн")

    # -------------------------------------------------------------------
    # УПРАВЛЕНИЕ СПРАВОЧНИКОМ
    # -------------------------------------------------------------------
    st.divider()
    st.markdown("### ⚙️ Управление справочником посуды")

    if can_edit:
        with st.form("add_tableware_item_form", clear_on_submit=True):
            col_n, col_p, col_q = st.columns([3, 1.5, 1.5])
            with col_n:
                new_name = st.text_input("Наименование номенклатуры *", placeholder="например, Бокал Riedel 450мл")
            with col_p:
                new_price = st.number_input("Цена за шт (грн) *", min_value=0, step=1, value=150)
            with col_q:
                new_qty = st.number_input("Остаток на начало (шт) *", min_value=0, step=1, value=20)

            if st.form_submit_button("➕ Добавить в справочник", type="primary", use_container_width=True):
                if not new_name.strip():
                    st.error("❌ Введите наименование.")
                else:
                    item_payload = {
                        "name": new_name.strip(),
                        "cost_price": int(new_price),
                        "prev_month_qty": int(new_qty),
                    }
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_catalog",
                        headers=headers,
                        json=item_payload,
                    )
                    log_audit("Добавлена посуда в справочник", new_name)
                    st.success(f"✅ Позиция {new_name} успешно добавлена!")
                    time.sleep(1)
                    st.rerun()

        if catalog_items:
            with st.expander("🗑️ Удалить позицию из справочника"):
                del_map = {f"{it['name']} ({it['cost_price']} грн)": it["id"] for it in catalog_items}
                sel_del = st.selectbox("Выберите позицию для удаления", options=list(del_map.keys()))
                if st.button("Удалить позицию", type="primary"):
                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{del_map[sel_del]}",
                        headers=headers,
                    )
                    log_audit("Удалена посуда из справочника", sel_del)
                    st.success("Удалено!")
                    time.sleep(1)
                    st.rerun()
