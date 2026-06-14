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
    "Content-Profile": "public",
    "Accept-Profile": "public",
    "Prefer": "return=representation"
}

# Функция безопасного перевода текста в целое число (без копеек)
def get_int(val):
    try:
        if not val: return 0
        clean_val = str(val).strip().replace(" ", "")
        return int(float(clean_val))
    except Exception:
        return 0

def get_start_balance(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        return get_int(res[0]['calculated_end']) if res else 0
    except Exception:
        return 0

def get_previous_advances(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if res:
            last_date = res[0]['date']
            url_adv = f"{SUPABASE_URL}/rest/v1/advances?date=eq.{last_date}"
            res_adv = requests.get(url_adv, headers=headers).json()
            return [(item['employee'], get_int(item['amount'])) for item in res_adv]
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
        selected_date_raw = st.date_input("Дата", datetime.today(), format="DD/MM/YYYY")
        selected_date = selected_date_raw.strftime('%Y-%m-%d')
    with col2:
        db_start = get_start_balance(selected_date)
        start_balance_raw = st.text_input("Залишок на початок дня:", value=str(db_start))
        start_balance = get_int(start_balance_raw)

    st.divider()
    col_inc, col_exp = st.columns(2)

    # --- НАДХОДЖЕННЯ ---
    with col_inc:
        st.subheader("Надходження:")
        if "inc_count" not in st.session_state: st.session_state.inc_count = 1
        inc_rows = []
        for i in range(st.session_state.inc_count):
            c1, c2 = st.columns([3, 1])
            with c1: desc = st.text_input("Опис приходу", key=f"inc_desc_{i}", label_visibility="collapsed", placeholder="Опис надходження")
            with c2: amt_raw = st.text_input("Сума приходу", key=f"inc_amt_{i}", label_visibility="collapsed", value="0")
            amt = get_int(amt_raw)
            if amt != 0 or desc: inc_rows.append({"date": selected_date, "type": "income", "description": desc, "amount": str(amt)})
        if st.button("➕ Додати рядок надходження"):
            st.session_state.inc_count += 1
            st.rerun()
        total_income = sum(get_int(item["amount"]) for item in inc_rows)
        st.markdown(f"### Загалом прихід: {total_income} грн")

    # --- ВИТРАТИ ---
    with col_exp:
        st.subheader("Витрати:")
        if "exp_count" not in st.session_state: st.session_state.exp_count = 1
        exp_rows = []
        for i in range(st.session_state.exp_count):
            c1, c2 = st.columns([3, 1])
            with c1: desc = st.text_input("Опис витрати", key=f"exp_desc_{i}", label_visibility="collapsed", placeholder="Опис витрати")
            with c2: amt_raw = st.text_input("Сума витрати", key=f"exp_amt_{i}", label_visibility="collapsed", value="0")
            amt = get_int(amt_raw)
            if amt != 0 or desc: exp_rows.append({"date": selected_date, "type": "expense", "description": desc, "amount": str(amt)})
        if st.button("➕ Додати рядок витрати"):
            st.session_state.exp_count += 1
            st.rerun()
        total_expense = sum(get_int(item["amount"]) for item in exp_rows)
        st.markdown(f"### Загалом витрати: {total_expense} грн")

    st.divider()
    col_adv, col_fact = st.columns(2)

    # --- АВАНСИ ---
    with col_adv:
        st.subheader("Аванси:")
        if f"adv_initialized_{selected_date}" not in st.session_state:
            prev_advances = get_previous_advances(selected_date)
            st.session_state[f"adv_initialized_{selected_date}"] = True
            st.session_state.adv_count = max(len(prev_advances), 1)
            for idx, (emp, amt) in enumerate(prev_advances):
                st.session_state[f"emp_{idx}"] = emp
                st.session_state[f"adv_amt_{idx}"] = str(get_int(amt))
        
        adv_rows = []
        for i in range(st.session_state.adv_count):
            c1, c2 = st.columns([3, 1])
            with c1: emp = st.text_input("Співробітник", key=f"emp_{i}", label_visibility="collapsed", placeholder="Ім'я співробітника")
            with c2: amt_raw = st.text_input("Сума авансу", key=f"adv_amt_{i}", label_visibility="collapsed", value="0")
            amt = get_int(amt_raw)
            if amt != 0 or emp: adv_rows.append({"date": selected_date, "employee": emp, "amount": str(amt)})
        if st.button("➕ Додати рядок авансу"):
            st.session_state.adv_count += 1
            st.rerun()
        total_advances = sum(get_int(item["amount"]) for item in adv_rows)
        st.markdown(f"### Загалом авансів: {total_advances} грн")

    # --- ФАКТИЧНИЙ ЗАЛИШОК (ПОСТРОЧНЫЙ ВВОД С АВТОСУММОЙ) ---
    with col_fact:
        st.subheader("Фактичний залишок:")
        
        # Монеты в 1 строку
        m_coins = get_int(st.text_input("Монети (загальна сума):", value="0"))
        
        # Вспомогательная функция для генерации аккуратной строки купюры
        def cash_row(label, multiplier):
            rc1, rc2 = st.columns([2, 1])
            with rc1:
                qty = get_int(st.text_input(f"{label} грн (кількість):", value="0", key=f"cash_qty_{label}"))
            with rc2:
                subtotal = qty * multiplier
                st.markdown(f"<div style='padding-top: 28px; font-weight: 500;'>= {subtotal} грн</div>", unsafe_allow_html=True)
            return subtotal

        # Купюры строго построчно друг за другом
        v_20 = cash_row("20", 20)
        v_50 = cash_
