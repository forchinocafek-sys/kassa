import streamlit as st
from datetime import datetime
import requests

# Настройки облачного веб-доступа к Supabase
SUPABASE_URL = "https://ajkprfhuypcamnybqusr.supabase.co"
SUPABASE_KEY = "sb_publishable_JMxxH6oo3cwsjS09gDe91A_uHL5C90E"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def get_start_balance(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        return float(res[0]['actual_end']) if res else 0.0
    except Exception:
        return 0.0

def get_previous_advances(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if res:
            last_date = res[0]['date']
            url_adv = f"{SUPABASE_URL}/rest/v1/advances?date=eq.{last_date}"
            res_adv = requests.get(url_adv, headers=headers).json()
            return [(item['employee'], float(item['amount'])) for item in res_adv]
    except Exception:
        pass
    return []

# --- Інтерфейс програми ---
st.set_page_config(layout="wide")
st.title("Cafe Forchino")
st.caption("🌐 Хмарна синхронізація (Всі пристрої)")

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
        if "inc_count" not in st.session_state: st.session_state.inc_count = 1
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
        if "exp_count" not in st.session_state: st.session_state.exp_count = 1
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
        requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
        requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
        requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
        
        requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json={"date": selected_date, "start_balance": str(start_balance), "calculated_end": str(calculated_end), "actual_end": str(total_actual)})
        for desc, amt in inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json={"date": selected_date, "type": "income", "description": desc, "amount": str(amt)})
        for desc, amt in exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json={"date": selected_date, "type": "expense", "description": desc, "amount": str(amt)})
        for emp, amt in adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json={"date": selected_date, "employee": emp, "amount": str(amt)})
                
        st.success(f"Звіт за {selected_date} успішно збережено в Хмару!")
        st.rerun()

# --- Архів ---
with tab2:
    st.subheader("🔎 Перегляд історії")
    search_date = st.date_input("Оберіть дату для перевірки", datetime.today(), key="search").strftime('%Y-%m-%d')
    
    url_shift = f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{search_date}"
    shift_res = requests.get(url_shift, headers=headers).json()
    
    if shift_res and isinstance(shift_res, list) and len(shift_res) > 0:
        shift = shift_res[0]
        st.info(f"**Залишок на початок:** {float(shift['start_balance'])} грн | **Розрахунковий кінець:** {float(shift['calculated_end'])} грн | **Фактичний залишок (Каса+Аванси):** {float(shift['actual_end'])} грн")
        
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            st.markdown("**Надходження:**")
            inc_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.income", headers=headers).json()
            for item in inc_res: st.write(f"• {item['description'] if item['description'] else 'Без опису'}: {float(item['amount'])} грн")
        with ac2:
            st.markdown("**Витрати:**")
            exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.expense", headers=headers).json()
            for item in exp_res: st.write(f"• {item['description'] if item['description'] else 'Без опису'}: {float(item['amount'])} грн")
        with ac3:
            st.markdown("**Аванси:**")
            adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{search_date}", headers=headers).json()
            for item in adv_res: st.write(f"• {item['employee'] if item['employee'] else 'Без імені'}: {float(item['amount'])} грн")
    else:
        st.warning("За цей день звітів не знайдено в хмарі.")
