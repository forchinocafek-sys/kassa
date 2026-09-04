import time
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, headers, SUPPLIES_CATEGORIES
from utils import log_audit, get_int, sanitize_df, auto_assign_category


def render_supplies_tab(selected_date, can_edit):
    st.subheader(f"🧹 Закупка ({selected_date})")

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, просмотр в режиме «Только чтение»."
        )

    draft_key = f"supplies_draft_qty_{selected_date}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = {}

    catalog_items = []
    try:
        res_cat = requests.get(
            f"{SUPABASE_URL}/rest/v1/supplies_catalog?select=*&order=id.asc",
            headers=headers,
        )
        if res_cat.status_code == 200 and isinstance(res_cat.json(), list):
            catalog_items = res_cat.json()
    except Exception:
        pass

    if not catalog_items and "supplies_catalog" in st.session_state:
        catalog_items = st.session_state["supplies_catalog"]

    st.markdown("### 1. Формирование заказа")

    if not catalog_items:
        st.info(
            "ℹ️ Справочник товаров пуст. Добавьте позиции ниже в блоке **3. Обновление справочника**."
        )
        order_items = pd.DataFrame()
    else:
        catalog_df = pd.DataFrame(catalog_items)

        if "sku" not in catalog_df.columns:
            catalog_df["sku"] = ""
        catalog_df["sku"] = catalog_df["sku"].fillna("")

        if "supplier" not in catalog_df.columns:
            catalog_df["supplier"] = ""
        catalog_df["supplier"] = catalog_df["supplier"].fillna("")

        if "category" not in catalog_df.columns:
            catalog_df["category"] = ""

        catalog_df["category"] = catalog_df.apply(
            lambda r: auto_assign_category(r["name"], r.get("category", "")), axis=1
        )

        catalog_df["qty"] = catalog_df["id"].map(
            lambda item_id: st.session_state[draft_key].get(item_id, 0)
        )

        total_selected = sum(1 for q in st.session_state[draft_key].values() if q > 0)

        col_dr1, col_dr2, col_dr3 = st.columns([2, 2, 3])
        with col_dr1:
            if st.button("💾 Сохранить черновик", type="primary", use_container_width=True, disabled=not can_edit):
                st.toast("✅ Черновик заказа сохранен!", icon="💾")
                log_audit("Сохранен черновик закупки", f"Дата: {selected_date}")
        with col_dr2:
            if st.button("🗑️ Очистить ввод", use_container_width=True, disabled=not can_edit):
                st.session_state[draft_key] = {}
                st.rerun()
        with col_dr3:
            st.markdown(f"**Всего выбрано позиций:** `{total_selected}`")

        st.write("")

        for cat_idx, category_name in enumerate(SUPPLIES_CATEGORIES):
            cat_df = catalog_df[catalog_df["category"] == category_name].copy()
            if cat_df.empty:
                continue

            filled_in_cat = sum(1 for _, r in cat_df.iterrows() if st.session_state[draft_key].get(r["id"], 0) > 0)
            badge = f"🟢 [Заказано: {filled_in_cat}]" if filled_in_cat > 0 else f"({len(cat_df)} поз.)"

            with st.expander(f"**{category_name}** {badge}", expanded=(filled_in_cat > 0)):
                edited_cat = st.data_editor(
                    cat_df[["id", "sku", "name", "qty", "unit", "supplier"]],
                    column_config={
                        "id": None,
                        "sku": None,
                        "name": st.column_config.TextColumn("Наименование", disabled=True),
                        "qty": st.column_config.NumberColumn(
                            "Количество", min_value=0, step=1, required=True
                        ),
                        "unit": st.column_config.TextColumn("Ед. изм.", disabled=True, width="small"),
                        "supplier": st.column_config.TextColumn("Поставщик", disabled=True),
                    },
                    column_order=["name", "qty", "unit", "supplier"],
                    hide_index=True,
                    use_container_width=True,
                    key=f"supplies_cat_editor_{cat_idx}_{selected_date}",
                    disabled=not can_edit,
                )

                for _, row in edited_cat.iterrows():
                    item_id = row["id"]
                    val = get_int(row["qty"])
                    st.session_state[draft_key][item_id] = val
                    catalog_df.loc[catalog_df["id"] == item_id, "qty"] = val

        catalog_df["qty"] = catalog_df["id"].map(lambda x: st.session_state[draft_key].get(x, 0))
        order_items = catalog_df[catalog_df["qty"] > 0].copy()

    st.divider()

    st.markdown("### 2. Заказы")

    if order_items.empty:
        st.info(
            "ℹ️ Укажите количество позиций к закупке в блоках категорий выше."
        )
    else:
        suppliers = order_items["supplier"].unique()

        for sup in suppliers:
            st.markdown(f"#### 🚚 Поставщик: **{sup}**")
            sup_df = order_items[order_items["supplier"] == sup].copy()

            has_sku = (sup_df["sku"].astype(str).str.strip() != "").any()

            table_cols = []
            col_rename = {
                "sku": "Артикул",
                "name": "Наименование",
                "qty": "Количество",
                "unit": "Единица Измерения",
            }

            if has_sku:
                table_cols.append("sku")

            table_cols.extend(["name", "qty", "unit"])

            col_table, col_code = st.columns([1.2, 1])

            with col_table:
                st.dataframe(
                    sup_df[table_cols].rename(columns=col_rename),
                    hide_index=True,
                    use_container_width=True,
                )

            with col_code:
                msg_lines = [
                    f"Привет! Заказ для Cafe Forchino ({selected_date}):"
                ]
                for _, r in sup_df.iterrows():
                    sku_str = str(r["sku"]).strip()
                    if sku_str:
                        msg_lines.append(
                            f"• [{sku_str}] {r['name']} — {int(r['qty'])}"
                            f" {r['unit']}"
                        )
                    else:
                        msg_lines.append(
                            f"• {r['name']} — {int(r['qty'])} {r['unit']}"
                        )
                msg_lines.append("\nСпасибо!")

                full_msg = "\n".join(msg_lines)
                st.code(full_msg, language="markdown")

    st.divider()

    col_save, col_history = st.columns([1, 1])

    with col_save:
        if can_edit and not order_items.empty:
            if st.button(
                "🚀 Фиксировать и отправлять закупку в историю",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("Сохранение закупки в облаке..."):
                    order_records = sanitize_df(
                        order_items[
                            ["sku", "name", "qty", "unit", "supplier", "category"]
                        ]
                    )

                    order_payload = {
                        "date": selected_date,
                        "created_by": st.session_state["user_name"],
                        "items": order_records,
                    }

                    res_order = requests.post(
                        f"{SUPABASE_URL}/rest/v1/supplies_orders",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "payload": order_payload,
                            "created_at": (
                                datetime.utcnow() + timedelta(hours=3)
                            ).isoformat(),
                        },
                    )

                    log_audit(
                        "Сформирован заказ хозов",
                        f"Дата: {selected_date}, Позиций: {len(order_records)}",
                    )
                    st.success("🎉 Закупка успешно зафиксирована в истории!")

    with col_history:
        with st.popover("📜 Просмотреть историю прошлых закупок"):
            st.markdown("#### Последние закупки")
            try:
                res_hist = requests.get(
                    f"{SUPABASE_URL}/rest/v1/supplies_orders?order=created_at.desc&limit=5",
                    headers=headers,
                ).json()
                if isinstance(res_hist, list) and len(res_hist) > 0:
                    for h in res_hist:
                        p = h.get("payload", {})
                        st.markdown(
                            f"**Дата:** {h.get('date')} | **Кто:**"
                            f" {p.get('created_by', 'Н/Д')}"
                        )
                        items_str = ", ".join([
                            f"{it['name']} — {it['qty']} {it['unit']}"
                            for it in p.get("items", [])
                        ])
                        st.caption(f"Товары: {items_str}")
                        st.write("---")
                else:
                    st.info("История закупок пока пуста.")
            except Exception:
                st.info("Не удалось загрузить историю.")

    st.divider()

    st.markdown("### 3. Обновление справочника")
    st.caption("Добавление новых позиций и удаление устаревших из базы товаров")

    if can_edit:
        with st.form(key="add_supplies_item_form", clear_on_submit=True):
            col_sku, col_name, col_cat, col_unit, col_sup = st.columns([1.5, 3, 2.5, 1.2, 2])

            with col_sku:
                new_sku = st.text_input(
                    "Артикул (необязательно)", placeholder="например, PKG-001"
                )
            with col_name:
                new_name = st.text_input(
                    "Наименование *", placeholder="например, Пакет крафт 28х15х32"
                )
            with col_cat:
                new_cat = st.selectbox(
                    "Категория *",
                    options=SUPPLIES_CATEGORIES,
                    index=8
                )
            with col_unit:
                new_unit = st.text_input(
                    "Ед. изм. *", placeholder="шт/рул/уп"
                )
            with col_sup:
                new_sup = st.text_input(
                    "Поставщик *", placeholder="например, Альфа-Пак"
                )

            btn_add = st.form_submit_button(
                "➕ Добавить в справочник",
                use_container_width=True,
                type="primary",
            )

            if btn_add:
                if (
                    not new_name.strip()
                    or not new_unit.strip()
                    or not new_sup.strip()
                ):
                    st.error(
                        "❌ Пожалуйста, заполните обязательные поля: Наименование,"
                        " Ед. изм. и Поставщик."
                    )
                else:
                    new_item = {
                        "sku": new_sku.strip(),
                        "name": new_name.strip(),
                        "category": new_cat.strip(),
                        "unit": new_unit.strip(),
                        "supplier": new_sup.strip(),
                    }

                    try:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/supplies_catalog",
                            headers=headers,
                            json=new_item,
                        )
                    except Exception:
                        pass

                    if "supplies_catalog" not in st.session_state:
                        st.session_state["supplies_catalog"] = []
                    st.session_state["supplies_catalog"].append(new_item)

                    log_audit(
                        "Добавлено товар в справочник",
                        f"Товар: {new_name}, Категория: {new_cat}, Поставщик: {new_sup}",
                    )
                    st.success(
                        f"✅ Товар **{new_name}** успешно добавлен в справочник!"
                    )
                    time.sleep(1)
                    st.rerun()

        if catalog_items:
            with st.expander("🗑️ Удалить позицию из справочника"):
                st.caption("Выберите позицию, которую необходимо безвозвратно удалить из Supabase:")

                item_map = {}
                for it in catalog_items:
                    item_id = it.get("id")
                    if item_id:
                        sku_label = f"[{it.get('sku')}] " if it.get('sku') else ""
                        label = f"{sku_label}{it.get('name')} | {it.get('supplier')} (ID: {item_id})"
                        item_map[label] = item_id

                if item_map:
                    col_del_select, col_del_btn = st.columns([3, 1])
                    with col_del_select:
                        selected_to_delete = st.selectbox(
                            "Выбор товара к удалению",
                            options=list(item_map.keys()),
                            key="del_item_selectbox",
                            label_visibility="collapsed"
                        )
                    with col_del_btn:
                        if st.button("🗑️ Удалить", type="primary", use_container_width=True):
                            target_id = item_map[selected_to_delete]
                            res_del = requests.delete(
                                f"{SUPABASE_URL}/rest/v1/supplies_catalog?id=eq.{target_id}",
                                headers=headers,
                            )
                            if res_del.status_code in [200, 204]:
                                log_audit(
                                    "Удален товар из справочника",
                                    f"Удален: {selected_to_delete}"
                                )
                                st.success("✅ Товар успешно удален!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Ошибка удаления: {res_del.text}")

    if catalog_items:
        with st.expander("📋 Просмотреть текущий справочник товаров"):
            df_cat_show = pd.DataFrame(catalog_items)
            cols_to_show = [c for c in ["sku", "name", "category", "unit", "supplier"] if c in df_cat_show.columns]

            df_cat_show = (
                df_cat_show[cols_to_show]
                .fillna("")
                .rename(
                    columns={
                        "sku": "Артикул",
                        "name": "Наименование",
                        "category": "Категория",
                        "unit": "Ед. изм.",
                        "supplier": "Поставщик",
                    }
                )
            )
            st.dataframe(df_cat_show, hide_index=True, use_container_width=True)
