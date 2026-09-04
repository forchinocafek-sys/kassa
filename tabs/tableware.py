import calendar
import time
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, headers
from utils import log_audit, get_int, sanitize_df


def render_tableware_tab(selected_date, can_edit):
    st.subheader(f"🍽️ Переучет и учет потерь посуды ({selected_date})")

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, перегляд у режимі «Тільки читання»."
        )

    tab_inv, tab_fin = st.tabs(
        ["📋 1. Інвентаризація номенклатури", "💰 2. Фінансовий облік втрат за місяць"]
    )

    # -------------------------------------------------------------------
    # ВЕ do 1: ИНВЕНТАРИЗАЦИЯ НОМЕНКЛАТУРЫ
    # -------------------------------------------------------------------
    with tab_inv:
        draft_key = f"tableware_inv_draft_{selected_date}"
        if draft_key not in st.session_state:
            st.session_state[draft_key] = {}

        catalog_items = []
        try:
            res = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_catalog?select=*&order=name.asc",
                headers=headers,
            )
            if res.status_code == 200 and isinstance(res.json(), list):
                catalog_items = res.json()
        except Exception:
            pass

        if not catalog_items:
            st.info("ℹ️ Справочник посуды пуст. Добавьте позиции внизу страницы.")
        else:
            df = pd.DataFrame(catalog_items)
            df["cost_price"] = df["cost_price"].apply(get_int)
            df["prev_month_qty"] = df["prev_month_qty"].apply(get_int)

            # Инициализация динамических полей
            for field in ["arrived", "broken", "fact_qty"]:
                df[field] = df["id"].map(
                    lambda item_id: st.session_state[draft_key]
                    .get(item_id, {})
                    .get(field, df.loc[df["id"] == item_id, "prev_month_qty"].values[0] if field == "fact_qty" else 0)
                )

            # Расчетные столбцы
            df["calc_qty"] = df["prev_month_qty"] + df["arrived"] - df["broken"]
            df["diff"] = df["fact_qty"] - df["calc_qty"]
            df["shortage_uah"] = df.apply(
                lambda r: abs(r["diff"]) * r["cost_price"] if r["diff"] < 0 else 0, axis=1
            )
            df["surplus_uah"] = df.apply(
                lambda r: r["diff"] * r["cost_price"] if r["diff"] > 0 else 0, axis=1
            )

            st.markdown("##### 📝 Таблица переучета")
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
                    "name": st.column_config.TextColumn("Найменування", disabled=True),
                    "cost_price": st.column_config.NumberColumn("Ціна (грн)", disabled=True, width="small"),
                    "prev_month_qty": st.column_config.NumberColumn("К-сть (минулий міс)", disabled=True, width="small"),
                    "arrived": st.column_config.NumberColumn("Приїхало (шт)", min_value=0, step=1, required=True),
                    "broken": st.column_config.NumberColumn("Розбилося (шт)", min_value=0, step=1, required=True),
                    "calc_qty": st.column_config.NumberColumn("Розрахунковий залишок", disabled=True, width="small"),
                    "fact_qty": st.column_config.NumberColumn("Фактичний залишок", min_value=0, step=1, required=True),
                    "diff": st.column_config.NumberColumn("Різниця (шт)", disabled=True, width="small"),
                    "shortage_uah": st.column_config.NumberColumn("Недостача (грн)", disabled=True, width="small"),
                    "surplus_uah": st.column_config.NumberColumn("Надлишок (грн)", disabled=True, width="small"),
                },
                hide_index=True,
                use_container_width=True,
                key=f"tableware_editor_{selected_date}",
                disabled=not can_edit,
            )

            # Сохранение текущих значений редактора в сессию
            for _, r in edited_df.iterrows():
                item_id = r["id"]
                st.session_state[draft_key][item_id] = {
                    "arrived": get_int(r["arrived"]),
                    "broken": get_int(r["broken"]),
                    "fact_qty": get_int(r["fact_qty"]),
                }

            # Итоговые метрики
            tot_shortage = edited_df["shortage_uah"].sum()
            tot_surplus = edited_df["surplus_uah"].sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("Всього позицій", len(edited_df))
            m2.metric("Сума недостачі", f"{tot_shortage} грн")
            m3.metric("Сума надлишків", f"{tot_surplus} грн")

            st.write("")
            if can_edit:
                if st.button("🚀 Зберегти інвентаризацію", type="primary", use_container_width=True):
                    payload_data = sanitize_df(edited_df)
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/tableware_inventories",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "created_by": st.session_state["user_name"],
                            "payload": payload_data,
                            "total_shortage_uah": int(tot_shortage),
                            "total_surplus_uah": int(tot_surplus),
                        },
                    )

                    # Обновление остатков на следующий месяц в справочнике
                    for _, r in edited_df.iterrows():
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{r['id']}",
                            headers=headers,
                            json={"prev_month_qty": get_int(r["fact_qty"])},
                        )

                    log_audit("Збережено інвентаризацію посуду", f"Дата: {selected_date}")
                    st.success("🎉 Інвентаризацію успішно збережено!")
                    time.sleep(1)
                    st.rerun()

    # -------------------------------------------------------------------
    # ВЕ do 2: ФИНАНСОВЫЙ УЧЕТ ПОТЕРЬ ЗА МЕСЯЦ
    # -------------------------------------------------------------------
    with tab_fin:
        st.markdown("##### 📊 Підсумковий баланс втрат за місяць")

        months = {
            "Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4,
            "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8,
            "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12,
        }
        c_m, c_y = st.columns(2)
        sel_m = c_m.selectbox("Місяць", list(months.keys()), index=st.session_state["form_date"].month - 1)
        sel_y = c_y.selectbox("Рік", [2025, 2026, 2027], index=1)

        month_key = f"{sel_y}-{months[sel_m]:02d}"

        # Загрузка записи потерь за выбранный месяц
        loss_record = {"broken_paid": 0, "broken_unpaid": 0, "lost": 0, "found": 0}
        try:
            res_loss = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_monthly_losses?month_year=eq.{month_key}",
                headers=headers,
            ).json()
            if isinstance(res_loss, list) and len(res_loss) > 0:
                loss_record = res_loss[0]
        except Exception:
            pass

        with st.form("monthly_loss_form"):
            col_l1, col_l2 = st.columns(2)
            with col_l1:
                b_paid = st.number_input(
                    "Бой (Оплачено официантами/гостями), грн",
                    min_value=0,
                    value=get_int(loss_record.get("broken_paid", 0)),
                    disabled=not can_edit,
                )
                b_unpaid = st.number_input(
                    "Бой (Не оплачено / за счет заведения), грн",
                    min_value=0,
                    value=get_int(loss_record.get("broken_unpaid", 0)),
                    disabled=not can_edit,
                )
            with col_l2:
                v_lost = st.number_input(
                    "Утеряно (недостача), грн",
                    min_value=0,
                    value=get_int(loss_record.get("lost", 0)),
                    disabled=not can_edit,
                )
                v_found = st.number_input(
                    "Найдено (излишки), грн",
                    min_value=0,
                    value=get_int(loss_record.get("found", 0)),
                    disabled=not can_edit,
                )

            # Чистый убыток заведения = Неоплаченный бой + Утеряно - Найдено
            total_net_shortage = b_unpaid + v_lost - v_found

            st.markdown(
                f"### 📉 Всего чистая недостача за месяц: **{total_net_shortage} грн**"
            )

            if can_edit:
                if st.form_submit_button("💾 Зберегти фінансовий підсумок", type="primary", use_container_width=True):
                    payload = {
                        "month_year": month_key,
                        "broken_paid": b_paid,
                        "broken_unpaid": b_unpaid,
                        "lost": v_lost,
                        "found": v_found,
                        "total_net_shortage": total_net_shortage,
                        "updated_at": (datetime.utcnow() + timedelta(hours=3)).isoformat(),
                    }

                    if loss_record.get("id"):
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/tableware_monthly_losses?id=eq.{loss_record['id']}",
                            headers=headers,
                            json=payload,
                        )
                    else:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/tableware_monthly_losses",
                            headers=headers,
                            json=payload,
                        )

                    log_audit("Оновлено фінансовий підсумок посуду", f"Місяць: {month_key}")
                    st.success("✅ Підсумок успішно збережено!")

    # -------------------------------------------------------------------
    # ВЕ do 3: УПРАВЛЕНИЕ СПРАВОЧНИКОМ ПОСУДЫ
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
