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
        editor_key = f"tableware_editor_{inv_date_str}"

        if draft_session_key not in st.session_state:
            st.session_state[draft_session_key] = {}
            loaded_data = False

            try:
                res_draft = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_drafts?date=eq.{inv_date_str}",
                    headers=headers,
                ).json()
                if isinstance(res_draft, list) and len(res_draft) > 0:
                    saved_payload = res_draft[0].get("payload", {})
                    st.session_state[draft_session_key] = {
                        int(k): get_int(v) for k, v in saved_payload.items() if str(k).isdigit()
                    }
                    loaded_data = True
            except Exception:
                pass

            if not loaded_data:
                try:
                    res_inv = requests.get(
                        f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=eq.{inv_date_str}&order=id.desc&limit=1",
                        headers=headers,
                    ).json()
                    if isinstance(res_inv, list) and len(res_inv) > 0:
                        inv_payload = res_inv[0].get("payload", [])
                        if isinstance(inv_payload, list):
                            st.session_state[draft_session_key] = {
                                get_int(item.get("id")): get_int(item.get("fact_qty", 0))
                                for item in inv_payload if "id" in item
                            }
                except Exception:
                    pass

        if editor_key in st.session_state and "edited_rows" in st.session_state[editor_key]:
            edited_rows = st.session_state[editor_key]["edited_rows"]
            for row_idx_str, changes in edited_rows.items():
                row_idx = int(row_idx_str)
                if "fact_qty" in changes and row_idx < len(catalog_items):
                    item_id = catalog_items[row_idx]["id"]
                    st.session_state[draft_session_key][item_id] = get_int(changes["fact_qty"])

        last_inv_date = None
        try:
            res_prev_inv = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=lt.{inv_date_str}&order=date.desc&limit=1",
                headers=headers,
            ).json()
            if isinstance(res_prev_inv, list) and len(res_prev_inv) > 0:
                last_inv_date = res_prev_inv[0].get("date")
        except Exception:
            pass

        inv_year_num = inv_date.year
        inv_month_num = inv_date.month
        inv_month_start = f"{inv_year_num}-{inv_month_num:02d}-01"

        events_query = f"{SUPABASE_URL}/rest/v1/tableware_events?date=lt.{inv_date_str}"
        if last_inv_date:
            events_query += f"&date=gte.{last_inv_date}"
        else:
            events_query += f"&date=gte.{inv_month_start}"

        events_summary = {}
        try:
            res_ev = requests.get(events_query, headers=headers).json()
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

            df["arrived"] = df["id"].map(lambda x: events_summary.get(x, {}).get("arrived", 0))
            df["broken"] = df["id"].map(lambda x: events_summary.get(x, {}).get("broken", 0))

            df["fact_qty"] = df["id"].map(
                lambda x: get_int(st.session_state[draft_session_key].get(x, 0))
            )

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
                        upsert_headers = {**headers, "Prefer": "resolution=merge-duplicates"}
                        res_post = requests.post(
                            f"{SUPABASE_URL}/rest/v1/tableware_drafts?on_conflict=date",
                            headers=upsert_headers,
                            json={
                                "date": inv_date_str,
                                "payload": draft_payload,
                                "updated_at": (datetime.utcnow() + timedelta(hours=3)).isoformat(),
                            },
                        )
                        res_post.raise_for_status()

                        log_audit("Збережено чернетку посуду", f"Дата: {inv_date_str}")
                        st.toast("✅ Черновик сохранен в облаке!", icon="💾")
                    except Exception as e:
                        st.error(f"❌ Ошибка сохранения черновика: {e}")

            with c_dr2:
                if st.button("🗑️ Очистить ввод", use_container_width=True, disabled=not can_edit):
                    st.session_state[draft_session_key] = {}
                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/tableware_drafts?date=eq.{inv_date_str}",
                        headers=headers,
                    )
                    st.rerun()

            with c_dr3:
                filled_count = sum(1 for v in st.session_state[draft_session_key].values() if get_int(v) > 0)
                st.markdown(f"**Заполнено позиций:** `{filled_count} из {len(df)}`")

            st.write("")

            disabled_columns = [
                "name",
                "cost_price",
                "prev_month_qty",
                "arrived",
                "broken",
                "calc_qty",
                "diff",
                "shortage_uah",
                "surplus_uah",
            ] if can_edit else True

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
                    "name": st.column_config.TextColumn("Найменування", width="large"),
                    "cost_price": st.column_config.NumberColumn("Ціна", width="small"),
                    "prev_month_qty": st.column_config.NumberColumn("Минулий", width="small"),
                    "arrived": st.column_config.NumberColumn("Приїхало (авто)", width="small"),
                    "broken": st.column_config.NumberColumn("Розбилося (авто)", width="small"),
                    "calc_qty": st.column_config.NumberColumn("Розрахунок", width="small"),
                    "fact_qty": st.column_config.NumberColumn("Факт (шт)", min_value=0, step=1, required=True, width="small"),
                    "diff": st.column_config.NumberColumn("Різниця", width="small"),
                    "shortage_uah": st.column_config.NumberColumn("Минус (грн)", width="small"),
                    "surplus_uah": st.column_config.NumberColumn("Плюс (грн)", width="small"),
                },
                disabled=disabled_columns,
                hide_index=True,
                use_container_width=True,
                key=editor_key,
            )

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
                    
                    upsert_inv_headers = {**headers, "Prefer": "resolution=merge-duplicates"}
                    res_inv_post = requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_inventories?on_conflict=date",
                        headers=upsert_inv_headers,
                        json={
                            "date": inv_date_str,
                            "created_by": st.session_state["user_name"],
                            "payload": payload_data,
                            "total_shortage_uah": int(tot_shortage),
                            "total_surplus_uah": int(tot_surplus),
                        },
                    )
                    res_inv_post.raise_for_status()

                    for _, r in edited_df.iterrows():
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{r['id']}",
                            headers=headers,
                            json={"prev_month_qty": get_int(r["fact_qty"])},
                        )

                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/tableware_drafts?date=eq.{inv_date_str}",
                        headers=headers,
                    )
                    st.session_state[draft_session_key] = {}

                    log_audit("Збережено фінальну інвентаризацію посуду", f"Дата: {inv_date_str}")
                    st.success("🎉 Інвентаризацію успішно збережено!")
                    time.sleep(1)
                    st.rerun()

    # -------------------------------------------------------------------
    # ВЕК 2: ЖУРНАЛ ОПЕРАЦИЙ (ПРИХОД / БОЙ / ДОЛГИ ТА УДЕРЖАНИЯ)
    # -------------------------------------------------------------------
    with tab_ops:
        st.markdown("### ⚡ Оформление операций")

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

                arr_qty = st.number_input("Количество приехать (шт)", min_value=1, step=1, value=1, key="arr_qty_input")
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
                        w_debt = int(tot_val * 0.5)
                        unpaid_val = int(tot_val * 0.5)
                    elif resp_type == "Гость":
                        paid_val = tot_val
                    else:
                        unpaid_val = tot_val

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

        # --- МОДУЛЬ ВЫБОРА ДИАПАЗОНА ПЕРЕУЧЕТА ---
        st.markdown("### 📊 Выбор периода переучета")

        inv_list = []
        try:
            res_all_inv = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_inventories?select=date,created_by&order=date.desc",
                headers=headers,
            ).json()
            if isinstance(res_all_inv, list) and len(res_all_inv) > 0:
                inv_list = res_all_inv
        except Exception:
            pass

        latest_inv_date = inv_list[0]["date"] if inv_list else None
        CURRENT_PERIOD = "⚡ Текущий незавершенный период (оперативные данные)"

        inv_options = {CURRENT_PERIOD: "CURRENT"}
        for inv in inv_list:
            inv_options[f"📅 Переучет от {inv['date']} (автор: {inv.get('created_by', '—')})"] = inv["date"]

        sel_period_label = st.selectbox(
            "Выберите период для расчета и ведомости:",
            options=list(inv_options.keys()),
            key="ops_inv_selector",
        )
        sel_period_val = inv_options[sel_period_label]

        if sel_period_val == "CURRENT":
            start_d = latest_inv_date if latest_inv_date else f"{selected_date[:7]}-01"
            end_d = selected_date
            events_query = f"date=gte.{start_d}&date=lte.{end_d}"
            period_text = f"с `{start_d}` (утро) по `{end_d}` (текущий момент)"
            save_month_key = selected_date[:7]
        else:
            sel_inv_date = sel_period_val
            prev_inv_date = None
            try:
                res_prev = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=lt.{sel_inv_date}&order=date.desc&limit=1",
                    headers=headers,
                ).json()
                if isinstance(res_prev, list) and len(res_prev) > 0:
                    prev_inv_date = res_prev[0].get("date")
            except Exception:
                pass

            start_d = prev_inv_date if prev_inv_date else f"{sel_inv_date[:7]}-01"
            end_d = sel_inv_date
            events_query = f"date=gte.{start_d}&date=lt.{end_d}"
            period_text = f"с `{start_d}` (утро) по `{end_d}` (утро)"
            save_month_key = sel_inv_date

        st.caption(f"ℹ️ **Выбранный диапазон:** {period_text}")

        # --- 3. УДЕРЖАНИЯ С ПЕРСОНАЛА И КОМПЕНСАЦИИ ЗА ПЕРИОД ---
        st.divider()
        st.markdown("### 💰 Удержания с персонала и компенсации за период")

        loss_record = {}
        try:
            res_loss = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_monthly_losses?month_year=eq.{save_month_key}",
                headers=headers,
            ).json()
            if isinstance(res_loss, list) and len(res_loss) > 0:
                loss_record = res_loss[0]
        except Exception:
            pass

        col_w1, col_w2 = st.columns([2, 1])

        with col_w1:
            st.markdown("#### 🧾 Расчет удержаний с персонала")
            calculated_debt_sum = 0
            try:
                res_debts = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_events?event_type=eq.breakage&waiter_debt=gt.0&{events_query}",
                    headers=headers,
                ).json()
                if isinstance(res_debts, list) and len(res_debts) > 0:
                    df_debts = pd.DataFrame(res_debts)
                    summary_debts = df_debts.groupby("waiter_name")["waiter_debt"].sum().reset_index()
                    summary_debts.columns = ["Сотрудник", "Начислено 50% боя (грн)"]
                    calculated_debt_sum = int(summary_debts["Начислено 50% боя (грн)"].sum())
                    st.dataframe(summary_debts, hide_index=True, use_container_width=True)
                    st.caption(f"💥 **Итого 50% личного боя за период:** `{calculated_debt_sum} грн`")
                else:
                    st.info("🎉 В этом периоде начислений по личному бою персонала не зафиксировано.")
            except Exception:
                pass

            saved_total = get_int(loss_record.get("actual_staff_deduction", 0))
            default_manual_val = max(0, saved_total - calculated_debt_sum) if saved_total > 0 else 0

            with st.form("save_monthly_deductions_form"):
                manual_val = st.number_input(
                    "Дополнительный / фиксированный сбор с персонала (грн):",
                    min_value=0,
                    value=default_manual_val,
                    step=50,
                    disabled=not can_edit,
                    help="Укажите базовый сбор (например, 2100). К нему автоматически прибавится 50% от личного боя за выбранный период."
                )

                total_staff_val = manual_val + calculated_debt_sum

                st.markdown("---")
                st.markdown(
                    f"### 🎯 **Итого к удержанию за период:** `{total_staff_val} грн`\n"
                    f"* **Ваш фиксированный сбор:** `{manual_val} грн`\n"
                    f"* **+ 50% личного боя (авто):** `{calculated_debt_sum} грн`"
                )

                if can_edit:
                    if st.form_submit_button("💾 Сохранить сумму удержаний", type="primary", use_container_width=True):
                        try:
                            payload = {
                                "month_year": save_month_key,
                                "actual_staff_deduction": total_staff_val,
                                "guest_payments": get_int(loss_record.get("guest_payments", 0)),
                                "updated_at": (datetime.utcnow() + timedelta(hours=3)).isoformat(),
                            }
                            
                            upsert_h = {**headers, "Prefer": "resolution=merge-duplicates"}
                            res_post = requests.post(
                                f"{SUPABASE_URL}/rest/v1/tableware_monthly_losses?on_conflict=month_year",
                                headers=upsert_h,
                                json=payload,
                            )
                            res_post.raise_for_status()

                            log_audit("Сохранены удержания с персонала", f"Период: {save_month_key}, Итого: {total_staff_val} грн")
                            st.success(f"✅ Удержание за период сохранено: {total_staff_val} грн!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as ex:
                            st.error(f"❌ Ошибка сохранения в Supabase: {ex}")

        with col_w2:
            st.markdown("#### 👤 Справочник персонала")
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

        # --- 4. ОБЩАЯ ВЕДОМОСТЬ БОЯ ЗА ПЕРИОД ---
        st.divider()
        st.markdown("### 📋 Общая ведомость боя за выбранный период")

        try:
            res_breakage = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?event_type=eq.breakage&{events_query}&order=date.desc",
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
                st.info("ℹ️ За выбранный период случаев боя не зафиксировано.")
        except Exception as e:
            st.error(f"Ошибка загрузки отчета: {e}")

    # -------------------------------------------------------------------
    # ВЕК 3: ФИНАНСОВЫЙ УЧЕТ ПОТЕРЬ
    # -------------------------------------------------------------------
    with tab_fin:
        st.markdown("##### 📊 Расчет чистого минуса казны заведения")

        inv_list = []
        try:
            res_all_inv = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_inventories?select=date,created_by,total_shortage_uah&order=date.desc",
                headers=headers,
            ).json()
            if isinstance(res_all_inv, list) and len(res_all_inv) > 0:
                inv_list = res_all_inv
        except Exception:
            pass

        latest_inv_date = inv_list[0]["date"] if inv_list else None
        CURRENT_FIN_PERIOD = "⚡ Текущий незавершенный период (оперативный расчет)"

        fin_options = {CURRENT_FIN_PERIOD: "CURRENT"}
        for inv in inv_list:
            fin_options[f"📅 Переучет от {inv['date']} (автор: {inv.get('created_by', '—')})"] = inv["date"]

        sel_fin_label = st.selectbox(
            "Выберите конкретную инвентаризацию для финансового отчета:",
            options=list(fin_options.keys()),
            key="fin_inv_selector",
        )
        sel_fin_val = fin_options[sel_fin_label]

        if sel_fin_val == "CURRENT":
            start_d = latest_inv_date if latest_inv_date else f"{selected_date[:7]}-01"
            end_d = selected_date

            # V_прошлый из последнего сохраненного переучета или из справочника
            v_start = 0
            if inv_list:
                try:
                    res_latest_inv = requests.get(
                        f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=eq.{latest_inv_date}",
                        headers=headers,
                    ).json()
                    if isinstance(res_latest_inv, list) and len(res_latest_inv) > 0:
                        payload = res_latest_inv[0].get("payload", [])
                        v_start = sum(get_int(row.get("fact_qty", 0)) * get_int(row.get("cost_price", 0)) for row in payload)
                except Exception:
                    pass
            if v_start == 0:
                v_start = sum(get_int(it.get("prev_month_qty", 0)) * get_int(it.get("cost_price", 0)) for it in catalog_items)

            # V_нынешний из текщей Черновики / Справочника
            v_fact = sum(get_int(it.get("prev_month_qty", 0)) * get_int(it.get("cost_price", 0)) for it in catalog_items)

            events_query = f"{SUPABASE_URL}/rest/v1/tableware_events?date=gte.{start_d}&date=lte.{end_d}"
            period_text = f"с `{start_d}` (утро) по `{end_d}` (текущий момент)"
            save_month_key = selected_date[:7]
        else:
            sel_inv_date = sel_fin_val
            curr_inv_data = None
            prev_inv_data = None
            prev_inv_date = None

            try:
                res_curr = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=eq.{sel_inv_date}",
                    headers=headers,
                ).json()
                if isinstance(res_curr, list) and len(res_curr) > 0:
                    curr_inv_data = res_curr[0]
            except Exception:
                pass

            try:
                res_prev = requests.get(
                    f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=lt.{sel_inv_date}&order=date.desc&limit=1",
                    headers=headers,
                ).json()
                if isinstance(res_prev, list) and len(res_prev) > 0:
                    prev_inv_data = res_prev[0]
                    prev_inv_date = prev_inv_data.get("date")
            except Exception:
                pass

            curr_payload = curr_inv_data.get("payload", []) if curr_inv_data else []
            v_fact = sum(get_int(row.get("fact_qty", 0)) * get_int(row.get("cost_price", 0)) for row in curr_payload)

            if prev_inv_data:
                prev_payload = prev_inv_data.get("payload", [])
                v_start = sum(get_int(row.get("fact_qty", 0)) * get_int(row.get("cost_price", 0)) for row in prev_payload)
            else:
                v_start = sum(get_int(row.get("prev_month_qty", 0)) * get_int(row.get("cost_price", 0)) for row in curr_payload)

            start_d = prev_inv_date if prev_inv_date else f"{sel_inv_date[:7]}-01"
            end_d = sel_inv_date
            events_query = f"{SUPABASE_URL}/rest/v1/tableware_events?date=gte.{start_d}&date=lt.{end_d}"
            period_text = f"с `{start_d}` (утро) по `{end_d}` (утро)"
            save_month_key = sel_inv_date

        v_deliv = 0
        m_guest_auto = 0
        try:
            res_events = requests.get(events_query, headers=headers).json()
            if isinstance(res_events, list):
                for ev in res_events:
                    if ev.get("event_type") == "delivery":
                        v_deliv += get_int(ev.get("total_amount", 0))
                    elif ev.get("event_type") == "breakage":
                        m_guest_auto += get_int(ev.get("paid_amount", 0))
        except Exception:
            pass

        m_staff_actual = 0
        try:
            res_loss = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_monthly_losses?month_year=eq.{save_month_key}",
                headers=headers,
            ).json()
            if isinstance(res_loss, list) and len(res_loss) > 0:
                m_staff_actual = get_int(res_loss[0].get("actual_staff_deduction", 0))
        except Exception:
            pass

        gross_shortage = (v_start + v_deliv) - v_fact
        total_compensations = m_staff_actual + m_guest_auto
        net_loss_kazna = gross_shortage - total_compensations

        st.caption(f"ℹ️ **Период отчета:** {period_text}")

        st.markdown("###### **1. Стоимость имущества на балансе:**")
        f1, f2, f3 = st.columns(3)
        f1.metric("Сумма на прошлый период (V_прошлый)", f"{v_start} грн")
        f2.metric("Сумма приходов (V_приход)", f"{v_deliv} грн")
        f3.metric("Сумма на нынешний период (V_нынешний)", f"{v_fact} грн")

        st.divider()

        st.markdown("###### **2. Компенсации и удержания:**")
        k1, k2, k3 = st.columns(3)
        k1.metric("Удержано с персонала (M_персонал)", f"{m_staff_actual} грн")
        k2.metric("Оплачено гостями (M_гости)", f"{m_guest_auto} грн")
        k3.metric("Всего компенсаций", f"{total_compensations} грн")

        st.divider()

        st.markdown("###### **3. Итоговый финансовый результат:**")
        r1, r2 = st.columns(2)
        r1.metric("Валовая физическая недостача", f"{gross_shortage} грн")
        r2.metric("📉 ЧИСТЫЙ МИНУС КАЗНЫ", f"{net_loss_kazna} грн")

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
