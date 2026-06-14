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

    # --- ФАКТИЧНИЙ ЗАЛИШОК (ГАРАНТОВАНА СТРОКА НА ТЕЛЕФОНАХ) ---
    with col_fact:
        st.subheader("Фактичний залишок:")
        
        # Инпут монет
        mc1, mc2 = st.columns([1, 3])
        with mc1:
            st.markdown("<div style='padding-top: 5px; font-weight: bold;'>Монети:</div>", unsafe_allow_html=True)
        with mc2:
            m_coins = get_int(st.text_input("Сума монет", value="0", label_visibility="collapsed", key="coins_input"))
            
        st.write("") 

        # Жесткая верстка таблицы, которая никогда не перенесет элементы на новую строку
        def cash_row_fixed(label, multiplier):
            # Создаем стандартный скрытый инпут, чтобы Streamlit зафиксировал значение
            qty_val = st.text_input(f"скрытый_{label}", value="0", label_visibility="collapsed", key=f"cash_qty_{label}")
            qty = get_int(qty_val)
            subtotal = qty * multiplier
            
            # Рендерим красивую и компактную строку таблицы
            st.markdown(
                f"""
                <table style='width:100%; border:none; margin-bottom:-10px; background:transparent;'>
                    <tr style='border:none; background:transparent;'>
                        <td style='width:25%; border:none; font-weight:bold; vertical-align:middle; padding:5px 0;'>{label} грн</td>
                        <td style='width:40%; border:none; vertical-align:middle; padding:5px 0; color:#888;'>штук: {qty}</td>
                        <td style='width:35%; border:none; font-weight:500; text-align:right; vertical-align:middle; padding:5px 0;'>= {subtotal} грн</td>
                    </tr>
                </table>
                """, 
                unsafe_allow_html=True
            )
            return subtotal

        # Вывод номиналов
        v_20 = cash_row_fixed("20", 20)
        v_50 = cash_row_fixed("50", 50)
        v_100 = cash_row_fixed("100", 100)
        v_200 = cash_row_fixed("200", 200)
        v_500 = cash_row_fixed("500", 500)
        v_1000 = cash_row_fixed("1000", 1000)
            
        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.divider()
        st.markdown(f"### Загалом в касі: {cash_pure} грн")

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
        if inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=inc_rows)
        if exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=exp_rows)
        if adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=adv_rows)
                
        st.success(f"Звіт за {selected_date_raw.strftime('%d/%m/%Y')} успішно збережено!")
        st.rerun()

# --- Архів ---
with tab2:
    st.subheader("🔎 Перегляд історії")
    search_date_raw = st.date_input("Оберіть дату для перевірки", datetime.today(), key="search", format="DD/MM/YYYY")
    search_date = search_date_raw.strftime('%Y-%m-%d')
    
    url_shift = f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{search_date}"
    shift_res = requests.get(url_shift, headers=headers).json()
    
    if shift_res and isinstance(shift_res, list) and len(shift_res) > 0:
        shift = shift_res[0]
        st.info(f"**Залишок на початок:** {get_int(shift['start_balance'])} грн | **Розрахунковий кінець:** {get_int(shift['calculated_end'])} грн | **Фактичний залишок (Каса+Аванси):** {get_int(shift['actual_end'])} грн")
        
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            st.markdown("**Надходження:**")
            inc_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.income", headers=headers).json()
            for item in inc_res: st.write(f"• {item['description'] if item['description'] else 'Без опису'}: {get_int(item['amount'])} грн")
        with ac2:
            st.markdown("**Витрати:**")
            exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.expense", headers=headers).json()
            for item in exp_res: st.write(f"• {item['description'] if item['description'] else 'Без опису'}: {get_int(item['amount'])} грн")
        with ac3:
            st.markdown("**Аванси:**")
            adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{search_date}", headers=headers).json()
            for item in adv_res: st.write(f"• {item['employee'] if item['employee'] else 'Без імені'}: {get_int(item['amount'])} грн")
    else:
        st.warning("За цей день звітів не знайдено в хмарі.")
