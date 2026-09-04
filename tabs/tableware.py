# -------------------------------------------------------------------
    # ВЕК 3: ФИНАНСОВЫЙ УЧЕТ ПОТЕРЬ
    # -------------------------------------------------------------------
    with tab_fin:
        st.markdown("##### 📊 Финансовый итог и расчет чистого минуса заведение")

        months_fin = {
            "Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4,
            "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8,
            "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12,
        }
        c_m, c_y = st.columns(2)
        sel_m = c_m.selectbox("Місяць", list(months_fin.keys()), index=st.session_state["form_date"].month - 1, key="fin_month_sel")
        sel_y = c_y.selectbox("Рік", [2025, 2026, 2027], index=1, key="fin_year_sel")

        month_key = f"{sel_y}-{months_fin[sel_m]:02d}"
        m_num = months_fin[sel_m]
        start_d = f"{sel_y}-{m_num:02d}-01"
        end_d = f"{sel_y+1}-01-01" if m_num == 12 else f"{sel_y}-{m_num+1:02d}-01"

        # 1. Автоматический расчет стоимости по справочнику и инвентаризациям
        v_start = sum(get_int(it.get("prev_month_qty", 0)) * get_int(it.get("cost_price", 0)) for it in catalog_items)
        
        v_deliv = 0
        m_guest_auto = 0
        m_staff_debt_auto = 0

        try:
            res_m_events = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_events?date=gte.{start_d}&date=lt.{end_d}",
                headers=headers,
            ).json()
            if isinstance(res_m_events, list):
                for ev in res_m_events:
                    if ev.get("event_type") == "delivery":
                        v_deliv += get_int(ev.get("total_amount", 0))
                    elif ev.get("event_type") == "breakage":
                        m_guest_auto += get_int(ev.get("paid_amount", 0))
                        m_staff_debt_auto += get_int(ev.get("waiter_debt", 0))
        except Exception:
            pass

        # Загрузка последней проведенной инвентаризации за месяц
        v_fact = 0
        has_inv = False
        try:
            res_inv = requests.get(
                f"{SUPABASE_URL}/rest/v1/tableware_inventories?date=gte.{start_d}&date=lt.{end_d}&order=date.desc&limit=1",
                headers=headers,
            ).json()
            if isinstance(res_inv, list) and len(res_inv) > 0:
                has_inv = True
                inv_items = res_inv[0].get("payload", [])
                v_fact = sum(get_int(row.get("fact_qty", 0)) * get_int(row.get("cost_price", 0)) for row in inv_items)
        except Exception:
            pass

        # Валовая недостача
        gross_shortage = (v_start + v_deliv) - v_fact if has_inv else 0

        st.markdown("###### **1. Баланс стоимости имущества в базе:**")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Старт месяца", f"{v_start} грн")
        f2.metric("Приходы (+)", f"{v_deliv} грн")
        f3.metric("Факт инвентаризации", f"{v_fact} грн" if has_inv else "Не проведена")
        f4.metric("Валовый минус", f"{gross_shortage} грн" if has_inv else "0 грн")

        st.divider()
        st.markdown("###### **2. Удержание с персонала и компенсации:**")

        # Загрузка сохраненных ручных удержаний за месяц
        loss_record = {"actual_staff_deduction": m_staff_debt_auto, "guest_payments": m_guest_auto}
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
                m_staff_actual = st.number_input(
                    "Фактически удержано из ЗП персонала (грн):",
                    min_value=0,
                    value=get_int(loss_record.get("actual_staff_deduction", m_staff_debt_auto)),
                    disabled=not can_edit,
                    help=f"Начислено по журналу боев (50%): {m_staff_debt_auto} грн"
                )
            with col_l2:
                m_guest_actual = st.number_input(
                    "Оплачено гостями за месяц (грн):",
                    min_value=0,
                    value=get_int(loss_record.get("guest_payments", m_guest_auto)),
                    disabled=not can_edit,
                )

            # Чистый минус
            net_loss = gross_shortage - (m_staff_actual + m_guest_actual)

            st.markdown(f"### 📉 Чистый минус заведения за месяц: **{net_loss} грн**")

            if can_edit:
                if st.form_submit_button("💾 Сохранить удержания за месяц", type="primary", use_container_width=True):
                    payload = {
                        "month_year": month_key,
                        "actual_staff_deduction": m_staff_actual,
                        "guest_payments": m_guest_actual,
                        "total_net_shortage": net_loss,
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

                    log_audit("Обновлены финансовые удержания посуды", f"Месяц: {month_key}")
                    st.success("✅ Данные удержаний сохранены!")
