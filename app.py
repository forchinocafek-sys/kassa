import streamlit as st
import psycopg2
from datetime import datetime

# Наша секретная облачная база
OBLACHNAYA_BAZA = "postgresql://postgres.ajkprfhuypcamnybqusr:cafe_Forchino@aws-1-eu-central-1.pooler.supabase.com:6543/postgres?pgbouncer=true"

def get_db_connection():
    return psycopg2.connect(OBLACHNAYA_BAZA)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS shifts (
                    date TEXT PRIMARY KEY, start_balance TEXT, calculated_end TEXT, actual_end TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY, date TEXT, type TEXT, description TEXT, amount TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS advances (
                    id SERIAL PRIMARY KEY, date TEXT, employee TEXT, amount TEXT)''')
    conn.commit()
    conn.close()

try:
    init_db()
except Exception:
    pass

def get_start_balance(date_str):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT actual_end FROM shifts WHERE date < %s ORDER BY date DESC LIMIT 1", (date_str,))
        res = c.fetchone()
        conn.close()
        return float(res[0]) if res else 0.0
    except Exception:
        return 0.0

def get_previous_advances(date_str):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT date FROM shifts WHERE date < %s ORDER BY date DESC LIMIT 1", (date_str,))
        last_date = c.fetchone()
        if last_date:
            c.execute("SELECT employee, amount FROM advances WHERE date = %s", (last_date[0],))
            advances = c.fetchall()
            conn.close()
            return [(emp, float(amt)) for emp, amt in advances]
        conn.close()
    except Exception:
        pass
    return []

# --- Інтерфейс програми ---
st.set_page_config(layout="wide")
st.title("Cafe Forchino")

tab1, tab2 = st.tabs(["📝 Введення даних за день", "🔎 Архів минулих днів"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        selected_date = st.date_input("Дата", datetime.today()).strftime('%Y-%m-%d')
    with col2:
        start_balance = st.number_input("Залишок на початок дня:", value=get_start_balance(selected_date), step=100.0)

    st.divider()
    col_inc, col_exp = st.columns(2)

    with col_inc:
        st.subheader("Надходження:")
        if "inc_count" not in st.session_state:
            st.session_state.inc_count = 1
            
        inc_rows = []
        for i in range(st.session_state.inc_count):
            c1, c2 = st.columns([3, 1])
            with c1: desc = st.text_input("Опис приходу", key=f"inc_desc_{i}", label_visibility="collapsed", placeholder="Опис надходження")
            with c2: amt = st.number_input("Сума приходу", min_value=0.0, step=50.0, key=f"inc_amt_{i}", label_visibility="collapsed")
            if amt > 0 or desc: inc_rows.append((desc, amt))
                
        if st.button("➕ Додати рядок надходження"):
            st.session_state.inc_count += 1
            st.rerun()
            
        total_income = sum(item[1] for item in inc_rows)
        st.markdown(f"### Загалом прихід: {total_income} грн")

    with col_exp:
        st.subheader("Витрати:")
        if "exp_count" not in st.session_state:
            st.session_state.exp_count = 1
            
        exp_rows = []
        for i in range(st.session_state.exp_count):
            c1, c2 = st.columns([3, 1])
            with c1: desc = st.text_input("Опис витрати", key=f"exp_desc_{i}", label_visibility="collapsed", placeholder="Опис витрати")
            with c2: amt = st.number_input("Сума витрати", min_value=0.0, step=50.0, key=f"exp_amt_{i}", label_visibility="collapsed")
            if amt > 0 or desc: exp_rows.append((desc, amt))
                
        if st.button("➕ Додати рядок витрати"):
            st.session_state.exp_count += 1
            st.rerun()
            
        total_expense = sum(item[1] for item in exp_rows)
        st.markdown(f"### Загалом витрати: {total_expense} грн")

    st.divider()
    col_adv, col_fact = st.columns(2)

    with col_adv:
        st.subheader("Аванси:")
        if f"adv_initialized_{selected_date}" not in st.session_state:
            prev_advances = get_previous_advances(selected_date)
            st.session_state[f"adv_initialized_{selected_date}"] = True
            st.session_state.adv_count = max(len(prev_advances), 1)
            for idx, (emp, amt) in enumerate(prev_advances):
                st.session_state[f"emp_{idx}"] = emp
                st.session_state[f"adv_amt_{idx}"] = float(amt)
        
        adv_rows = []
        for i in range(st.session_state.adv_count):
            c1, c2 = st.columns([3, 1])
            with c1: emp = st.text_input("Співробітник", key=f"emp_{i}", label_visibility="collapsed", placeholder="Ім'я співробітника")
            with c2: amt = st.number_input("Сума авансу", min_value=0.0, step=50.0, key=f"adv_amt_{i}", label_visibility="collapsed")
            if amt > 0 or emp: adv_rows.append((emp, amt))
                
        if st.button("➕ Додати рядок авансу"):
            st.session_state.adv_count += 1
            st.rerun()
            
        total_advances = sum(item[1] for item in adv_rows)
        st.markdown(f"### Загалом авансів: {total_advances} грн")

    with col_fact:
        st.subheader("Фактичний залишок:")
        fc1, fc2 = st.columns(2)
        with fc1:
            m_coins = st.number_input("Монети (сума):", min_value=0.0, step=1.0)
            k_20 = st.number_input("20 грн (кількість):", min_value=0, step=1) * 20
            k_50 = st.number_input("50 грн (кількість):", min_value=0, step=1) * 50
            k_100 = st.number_input("100 грн (кількість):", min_value=0, step=1) * 100
        with fc2:
            k_200 = st.number_input("200 грн (кількість):", min_value=0, step=1) * 200
            k_500 = st.number_input("500 грн (кількість):", min_value=0, step=1) * 500
            k_1000 = st.number_input("1000 грн (кількість):", min_value=0, step=1) * 1000
            
        cash_pure = m_coins + k_20 + k_50 + k_100 + k_200 + k_500 + k_1000
        st.markdown(f"**Готівка в касі:** {cash_pure} грн")

    st.divider()
    
    calculated_end = start_balance + total_income - total_expense
    total_actual = cash_pure + total_advances
    discrepancy = total_actual - calculated_end

    st.subheader("Підсумки зміни")
    res_c1, res_c2, res_c3 = st.columns(3)
    res_c1.metric("Розрахунковий залишок на кінець дня", f"{calculated_end} грн")
    res_c2.metric("Фактичний залишок (Каса + Аванси)", f"{total_actual} грн")
    
    if discrepancy == 0: res_c3.success("Каса зійшлася!")
    elif discrepancy > 0: res_c3.warning(f"Надлишок: +{discrepancy} грн")
    else: res_c3.error(f"Недостача: {discrepancy} грн")

    if st.button("Зберегти звіт за день", type="primary"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM shifts WHERE date = %s", (selected_date,))
        c.execute("DELETE FROM transactions WHERE date = %s", (selected_date,))
        c.execute("DELETE FROM advances WHERE date = %s", (selected_date,))
        
        c.execute("INSERT INTO shifts VALUES (%s, %s, %s, %s)", (selected_date, str(start_balance), str(calculated_end), str(total_actual)))
        
        for desc, amt in inc_rows: 
            if desc or amt > 0: c.execute("INSERT INTO transactions (date, type, description, amount) VALUES (%s, 'income', %s, %s)", (selected_date, desc, str(amt)))
        for desc, amt in exp_rows: 
            if desc or amt > 0: c.execute("INSERT INTO transactions (date, type, description, amount) VALUES (%s, 'expense', %s, %s)", (selected_date, desc, str(amt)))
        for emp, amt in adv_rows: 
            if emp or amt > 0: c.execute("INSERT INTO advances (date, employee, amount) VALUES (%s, %s, %s)", (selected_date, emp, str(amt)))
                
        conn.commit()
        conn.close()
        st.success(f"Звіт за {selected_date} успішно збережено в Облако!")
        st.rerun()

# --- Архів ---
with tab2:
    st.subheader("🔎 Перегляд історії")
    search_date = st.date_input("Оберіть дату для перевірки", datetime.today(), key="search").strftime('%Y-%m-%d')
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM shifts WHERE date = %s", (search_date,))
    shift = c.fetchone()
    
    if shift:
        st.info(f"**Залишок на початок:** {float(shift[1])} rрн | **Розрахунковий кінець:** {float(shift[2])} грн | **Фактичний залишок (Каса+Аванси):** {float(shift[3])} грн")
        
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            st.markdown("**Надходження:**")
            c.execute("SELECT description, amount FROM transactions WHERE date = %s AND type = 'income'", (search_date,))
            for d, a in c.fetchall(): st.write(f"• {d if d else 'Без опису'}: {float(a)} грн")
                
        with ac2:
            st.markdown("**Витрати:**")
            c.execute("SELECT description, amount FROM transactions WHERE date = %s AND type = 'expense'", (search_date,))
            for d, a in c.fetchall(): st.write(f"• {d if d else 'Без опису'}: {float(a)} грн")
                
        with ac3:
            st.markdown("**Аванси:**")
            c.execute("SELECT employee, amount FROM advances WHERE date = %s", (search_date,))
            for e, a in c.fetchall(): st.write(f"• {e if e else 'Без імені'}: {float(a)} грн")
    else:
        st.warning("За цей день звітів не знайдено в облаку.")
    conn.close()