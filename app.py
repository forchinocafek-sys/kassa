import streamlit as st
from datetime import datetime
import requests
import pandas as pd
import time  # Импортируем для организации UX-паузы

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
        if isinstance(res, list) and len(res) > 0:
            return get_int(res[0].get('calculated_end', 0))
    except Exception:
        pass
    return 0

def get_previous_advances(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            last_date = res[0].get('date')
            if last_date:
                url_adv = f"{SUPABASE_URL}/rest/v1/advances?date=eq.{last_date}"
                res_adv = requests.get(url_adv, headers=headers).json()
                if isinstance(res_adv, list):
                    return [{"Співробітник": item.get('employee', ''), "Сума": get_int(item.get('amount', 0))} for item in res_adv]
    except Exception:
        pass
    return []

# Функция-callback: теперь только сигнализирует системе, что дата изменилась
def on_date_change():
    st.session_state["current_loaded_date"] = st.session_state["form_date"].strftime('%Y-%m-%d')
    # Сбрасываем старые таблицы, чтобы вынудить систему переинициализировать их для новой даты
    if "inc_df" in st.session_state: del st.session_state["inc_df"]
    if "exp_df" in st.session_state: del st.session_state["exp_df"]
    if "adv_df" in st.session_state: del st.session_state["adv_df"]

# --- Інтерфейс програми ---
st.set_page_config(layout="wide")

st.title("Cafe Forchino")
st.caption("🌐 Хмарна синхронізація | Реактивна версія 4.2 (Фінальний Еталон)")

tab1, tab2 = st.tabs(["📝 Введення даних за день", "🔎 Архів минулих днів"])

with tab1:
    # 1. Контроль выбранной даты
    if "form_date" in st.session_state:
        selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
    else:
        selected_date = datetime.today().strftime('%Y-%m-%d')
        st.session_state["current_loaded_date"] = selected_date

    # 2. Инпут даты (Связан с callback-ом)
    col1, col2 = st.columns(2)
    with col1:
        selected_date_raw = st.date_input("Дата", datetime.today(), format="DD/MM/YYYY", key="form_date", on_change=on_date_change)
        selected_date = selected_date_raw.strftime('%Y-%m-%d')
    with col2:
        db_start = get_start_balance(selected_date)
        start_balance_raw = st.text_input("Залишок на початок дня:", value=str(db_start), key=f"start_balance_{selected_date}")
        start_balance = get_int(start_balance_raw)

    st.divider()

    # 3. Централизованная инициализация таблиц (СТРОГО после фиксации selected_date)
    if "inc_df" not in st.session_state:
        st.session_state["inc_df"] = pd.DataFrame([{"Опис": "", "Сума": 0}])
    if "exp_df" not in st.session_state:
        st.session_state["exp_df"] = pd.DataFrame([{"Опис": "", "Сума": 0}])
    if "adv_df" not in st.session_state:
        # Сетевой запрос выполняется ровно один раз для конкретной даты
        prev_adv = get_previous_advances(selected_date)
        if prev_adv:
            st.session_state["adv_df"] = pd.DataFrame(prev_adv)
        else:
            st.session_state["adv_df"] = pd.DataFrame([{"Співробітник": "", "Сума": 0}])

    st.markdown("<p style='color: #888888; font-size: 13px;'>💡 <b>Крок 1:</b> Внесіть дані в таблиці. Рядки додаються кнопкою <b>+ Add row</b> внизу кожної таблиці. Дані зберігаються автоматично.</p>", unsafe_allow_html=True)
    
    # ТАБЛИЦЫ РУХУ КОШТІВ
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("Надходження:")
        edited_inc_df = st.data_editor(st.session_state["inc_df"], num_rows="dynamic", use_container_width=True, key="inc_editor")
    with col_t2:
    st.divider()

    # Створюємо дві колонки: зліва Аванси, справа Каса
    col_b1, col_b2 = st.columns(2)

    with col_b1:
        st.subheader("Аванси співробітникам:")
        edited_adv_df = st.data_editor(st.session_state["adv_df"], num_rows="dynamic", use_container_width=True, key="adv_editor")

    with col_b2:
        st.markdown("<p style='color: #0066cc; font-size: 14px; font-weight: bold;'>💰 Крок 2: Рахунок готівки в касі</p>", unsafe_allow_html=True)
        m_coins = get_int(st.text_input("Монети (загальна сума в грн):", value="0", key=f"coins_live_{selected_date}"))
        
        def cash_row_live(label, multiplier):
            rc1, rc2 = st.columns([1, 1])
            with rc1:
                qty = get_int(st.text_input(f"{label} грн (кількість):", value="0", key=f"qty_{label}_{selected_date}"))
            with rc2:
                subtotal = qty * multiplier
                st.markdown(f"<div style='padding-top: 32px; font-weight: bold; color: #0066cc;'>= {subtotal} грн</div>", unsafe_allow_html=True)
            return subtotal

        # Виводимо купюри вертикально, щоб не ламати верстку колонок
        v_20 = cash_row_live("20", 20)
        v_50 = cash_row_live("50", 50)
        v_100 = cash_row_live("100", 100)
        v_200 = cash_row_live("200", 200)
        v_500 = cash_row_live("500", 500)
        v_1000 = cash_row_live("1000", 1000)
        
        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.markdown(f"## 💵 Разом готівки в касі: {cash_pure} грн")

    # Синхронизация состояния таблиц для защиты от реранов калькулятора купюр
    st.session_state["inc_df"] = edited_inc_df
    st.session_state["exp_df"] = edited_exp_df
    st.session_state["adv_df"] = edited_adv_df

    # Парсинг строк
    inc_rows = []
    for _, row in edited_inc_df.iterrows():
        amt = get_int(row.get("Сума", 0))
        desc = str(row.get("Опис", "")).strip()
        if amt != 0 or desc: inc_rows.append({"date": selected_date, "type": "income", "description": desc, "amount": str(amt)})

    exp_rows = []
    for _, row in edited_exp_df.iterrows():
        amt = get_int(row.get("Сума", 0))
        desc = str(row.get("Опис", "")).strip()
        if amt != 0 or desc: exp_rows.append({"date": selected_date, "type": "expense", "description": desc, "amount": str(amt)})

    adv_rows = []
    for _, row in edited_adv_df.iterrows():
        amt = get_int(row.get("Сума", 0))
        emp = str(row.get("Співробітник", "")).strip()
        if amt != 0 or emp: adv_rows.append({"date": selected_date, "employee": emp, "amount": str(amt)})

    total_income = sum(get_int(item["amount"]) for item in inc_rows)
    total_expense = sum(get_int(item["amount"]) for item in exp_rows)
    total_advances = sum(get_int(item["amount"]) for item in adv_rows)

    # 5. ИТОГИ И СИНХРОНИЗАЦИЯ С БАЗОЙ
    st.divider()
    calculated_end = start_balance + total_income - total_expense
    total_actual = cash_pure + total_advances
    discrepancy = total_actual - calculated_end

    st.subheader("🏁 Підсумки зміни")
    res_c1, res_c2, res_c3 = st.columns(3)
    res_c1.metric("Розрахунковий залишок", f"{calculated_end} грн")
    res_c2.metric("Фактичний залишок (Каса + Аванси)", f"{total_actual} грн")
    
    if discrepancy == 0: res_c3.success("Каса зійшлася!")
    elif discrepancy > 0: res_c3.warning(f"Надлишок: +{discrepancy} грн")
    else: res_c3.error(f"Недостача: {discrepancy} грн")

    save_report = st.button("🚀 ЗБЕРЕГТИ ГОТОВИЙ ЗВІТ В ХМАРУ", type="primary", use_container_width=True)

    if save_report:
        with st.spinner("Очищення старих даних та синхронізація..."):
            try:
                # Очищаем логи за этот день перед чистой записью
                requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
                requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
                requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
                
                # Записываем новые данные
                res_shift = requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json={
                    "date": selected_date, "start_balance": str(start_balance), 
                    "calculated_end": str(calculated_end), "actual_end": str(total_actual)
                })
                
                if res_shift.status_code in [200, 201]:
                    if inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=inc_rows)
                    if exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=exp_rows)
                    if adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=adv_rows)
                    
                    # Фикс №2: Показываем плашку успеха и замираем на 1.5 секунды для комфорта кассира
                    st.success(f"🎉 Звіт за {selected_date_raw.strftime('%d/%m/%Y')} успішно та безпечно записано в систему!")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error(f"❌ Помилка сервера бази даних: {res_shift.status_code}. Спробуйте ще раз.")
            except Exception as e:
                st.error(f"💥 Помилка мережі: {e}. Перевірте інтернет-з'єднання.")

# --- Архів ---
with tab2:
    st.subheader("🔎 Перегляд історії")
    search_date_raw = st.date_input("Оберіть дату для перевірки", datetime.today(), key="search", format="DD/MM/YYYY")
    search_date = search_date_raw.strftime('%Y-%m-%d')
    
    url_shift = f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{search_date}"
    shift_res = requests.get(url_shift, headers=headers).json()
    
    if isinstance(shift_res, list) and len(shift_res) > 0:
        shift = shift_res[0]
        st.info(f"**Залишок на початок:** {get_int(shift.get('start_balance'))} грн | **Розрахунковий кінець:** {get_int(shift.get('calculated_end'))} грн | **Фактичний залишок (Каса+Аванси):** {get_int(shift.get('actual_end'))} грн")
        
        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            st.markdown("**Надходження:**")
            inc_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.income", headers=headers).json()
            if isinstance(inc_res, list):
                for item in inc_res: st.write(f"• {item.get('description', 'Без опису')}: {get_int(item.get('amount'))} грн")
        with ac2:
            st.markdown("**Витрати:**")
            exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.expense", headers=headers).json()
            if isinstance(exp_res, list):
                for item in exp_res: st.write(f"• {item.get('description', 'Без опису')}: {get_int(item.get('amount'))} грн")
        with ac3:
            st.markdown("**Аванси:**")
            adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{search_date}", headers=headers).json()
            if isinstance(adv_res, list):
                for item in adv_res: st.write(f"• {item.get('employee', 'Без імені')}: {get_int(item.get('amount'))} грн")
    else:
        st.warning("За цей день звітів не знайдено в хмарі.")
