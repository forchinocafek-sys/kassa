import time
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, headers
from utils import log_audit, get_int, sanitize_df


def render_tableware_tab(selected_date, can_edit):
    st.subheader("🍽️ Переучет и учет потерь посуды")

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, перегляд у режимі «Тільки читання»."
        )

    tab_inv, tab_fin = st.tabs(
        ["📋 1. Інвентаризація номенклатури", "💰 2. Фінансовий облік втрат за місяць"]
    )

    # -------------------------------------------------------------------
    # ВЕК 1: ИНВЕНТАРИЗАЦИЯ НОМЕНКЛАТУРЫ
    # -------------------------------------------------------------------
    with tab_inv:
        # Выбор даты инвентаризации
        default_date_obj = (
            datetime.strptime(selected_date, "%Y-%m-%d").date()
            if isinstance(selected_date, str)
            else selected_date
        )

        col_date, _ = st.columns([1, 2])
        with col_date:
            inv_date = st.date_input(
                "📅 Дата проведення інвентаризації:",
                value=default_date_obj,
                format="DD/MM/YYYY",
                key="tableware_inv_date_picker",
            )
            inv_date_str = inv_date.strftime("%Y-%m-%d")

        draft_session_key = f"tableware_inv_draft_{inv_date_str}"
        supabase_draft_date = f"tableware_{inv_date_str}"

        # Загрузка черновика из Supabase при выборе даты
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

            # Привязка значений к черновику (Фактичний залишок по умолчанию 0)
            for field in ["arrived", "broken", "fact_qty"]:
                df[field] = df["id"].map(
                    lambda item_id: st.session_state[draft_session_key]
                    .get(item_id, {})
                    .get(field, 0)
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

            # Кнопки управления черновиком
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
                        st.toast(f"✅ Черновик сохранен на {inv_date_str}!", icon="💾")
                    except Exception as e:
                        st.error(f"Помилка збереження чернетки: {e}")

            with c_dr2:
                if st.button("🗑️ Очистить ввод", use_container_width=True, disabled=not can_edit):
                    st.session_state[draft_session_key] = {}
                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                        headers=headers,
                    )
                    st.rerun()

            with c_dr3:
                filled_count = sum(
                    1 for v in st.session_state[draft_session_key].values() if v.get("fact_qty", 0) > 0
                )
                st.markdown(f"**Заполнено позиций:** `{filled_count} из {len(df)}`")

            st.write("")

            # Таблица инвентаризации
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
                    "arrived": st.column_config.NumberColumn("Приїхало", min_value=0, step=1, required=True, width="small"),
                    "broken": st.column_config.NumberColumn("Розбилося", min_value=0, step=1, required=True, width="small"),
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

            # Запись изменений в сессию
            for _, r in edited_df.iterrows():
                item_id = r["id"]
                st.session_state[draft_session_key][item_id] = {
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

                    # Обновление остатков на следующий месяц в справочнике
                    for _, r in edited_df.iterrows():
                        requests.patch(
                            f"{SUPABASE_URL}/rest/v1/tableware_catalog?id=eq.{r['id']}",
                            headers=headers,
                            json={"prev_month_qty": get_int(r["fact_qty"])},
                        )

                    # Очищаем черновик после сохранения
                    requests.delete(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{supabase_draft_date}",
                        headers=headers,
                    )
                    st.session_state[draft_session_key] = {}

                    log_audit("Збережено фінальну інвентаризацію посуду", f"Дата: {inv_date_str}")
                    st.success(f"🎉 Інвентаризацію за {inv_date_str} успішно збережено!")
                    time.sleep(1)
                    st.rerun()

    # -------------------------------------------------------------------
    # ВЕК 2: ФИНАНСОВЫЙ УЧЕТ ПОТЕРЬ ЗА МЕСЯЦ
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
    # ВЕК 3: УПРАВЛЕНИЕ СПРАВОЧНИКОМ ПОСУДЫ
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
