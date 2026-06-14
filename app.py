    # 3. ТАБЛИЦЫ ДВИЖЕНИЯ СРЕДСТВ И АВАНСЫ (ГОРИЗОНТАЛЬНО)
    col_t1, col_t2 = st.columns(2)
    
    with col_t1:
        st.subheader("Надходження:")
        edited_inc_df = st.data_editor(st.session_state["inc_df"], num_rows="dynamic", use_container_width=True, key="inc_editor")
        
        st.subheader("Аванси співробітникам:")
        edited_adv_df = st.data_editor(st.session_state["adv_df"], num_rows="dynamic", use_container_width=True, key="adv_editor")
        
    with col_t2:
        st.subheader("Витрати:")
        edited_exp_df = st.data_editor(st.session_state["exp_df"], num_rows="dynamic", use_container_width=True, key="exp_editor")

        # --- КРОК 2: РАХУНОК ГОТІВКИ В КАСІ (ПЕРЕНЕСЕН В ПРАВУЮ КОЛОНКУ) ---
        st.markdown("<p style='color: #0066cc; font-size: 14px; font-weight: bold;'>💰 Крок 2: Рахунок готівки в касі</p>", unsafe_allow_html=True)
        
        m_coins = get_int(st.text_input("Монети (загальна сума в грн):", value="0", key=f"coins_live_{selected_date}"))
        
        def cash_row_live(label, multiplier):
            rc1, rc2 = st.columns([1, 1])
            with rc1:
                qty = get_int(st.text_input(f"{label} грн:", value="0", key=f"qty_{label}_{selected_date}"))
            with rc2:
                subtotal = qty * multiplier
                st.markdown(f"<div style='padding-top: 32px; font-weight: bold; color: #0066cc;'>= {subtotal} грн</div>", unsafe_allow_html=True)
            return subtotal

        # Компактный вывод купюр
        v_20 = cash_row_live("20", 20)
        v_50 = cash_row_live("50", 50)
        v_100 = cash_row_live("100", 100)
        v_200 = cash_row_live("200", 200)
        v_500 = cash_row_live("500", 500)
        v_1000 = cash_row_live("1000", 1000)
        
        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.markdown(f"### 💵 Разом готівки: {cash_pure} грн")

    # Синхронизация состояния (после закрытия колонок)
    st.session_state["inc_df"] = edited_inc_df
    st.session_state["exp_df"] = edited_exp_df
    st.session_state["adv_df"] = edited_adv_df
