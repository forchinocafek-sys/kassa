import streamlit as st
from datetime import datetime
import requests
import pandas as pd
import time

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

# --- ДОПОМІЖНА ФУНКЦІЯ ДЛЯ СТАБІЛІЗАЦІЇ ТАБЛИЦЬ ---
def prepare_df(data_list, columns):
    if not data_list:
        data_list = [{col: (0 if col == "Сума" else "") for col in columns}]
    df = pd.DataFrame(data_list)
    for col in columns:
        if col not in df.columns:
            df[col] = 0 if col == "Сума" else ""
    if "Сума" in df.columns:
        df["Сума"] = pd.to_numeric(df["Сума"], errors='coerce').fillna(0).astype(int)
    return df[columns]

# --- Инициализация данных и загрузка черновиков ---
def load_draft_or_init(date_str):
    coins_key = f"coins_live_{date_str}"
    try:
        url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}"
        draft_res = requests.get(url_draft, headers=headers).json()
        if isinstance(draft_res, list) and len(draft_res) > 0:
            payload = draft_res[0].get('payload', {})
            st.session_state["inc_data"] = payload.get('inc', [{"Опис": "", "Сума": 0}])
            st.session_state["exp_data"] = payload.get('exp', [{"Опис": "", "Сума": 0}])
            st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": 0}])
            cash_data = payload.get('cash', {})
            st.session_state[coins_key] = str(cash_data.get('coins', 0))
            for k in [20, 50, 100, 200, 500, 1000]:
                st.session_state[f"qty_{k}_{date_str}"] = str(cash_data.get(str(k), 0))
            return
    except Exception:
        pass
    st.session_state["inc_data"] = [{"Опис": "", "Сума": 0}]
    st.session_state["exp_data"] = [{"Опис": "", "Сума": 0}]
    prev_adv = get_previous_advances(date_str)
    st.session_state["adv_data"] = prev_adv if prev_adv else [{"Співробітник": "", "Сума": 0}]
    st.session_state[coins_key] = "0"
    for k in [20, 50, 100, 200, 500, 1000]:
        st.session_state[f"qty_{k}_{date_str}"] = "0"

def on_date_change():
    new_date = st.session_state["form_date"].strftime('%Y-%m-%d')
    st.session_state["current_loaded_date"] = new_date
    load_draft_or_init(new_date)

# --- Инициализация ---
if "form_date" in st.session_state:
    selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
else:
    selected_date = datetime.today().strftime('%Y-%m-%d')

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date

# --- Інтерфейс програми ---
st.set_page_config(layout="wide")

# --- CSS ДЛЯ СТАБІЛЬНОЇ ВЕРСТКИ ---
st.markdown("""
<style>
    /* Примусово виставляємо колонки в стовпчик на екранах до 1024px */
    @media (max-width: 1024px) {
        div[data-testid="column"] {
            width: 100% !important;
            flex: 1 1 100% !important;
        }
    }
    .cash-sum { font-weight: bold; color: #0066cc; font-size: 16px; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)

st.title("Cafe Forchino")
st.caption("🌐 Хмарна синхронізація | Stable 1.2.2 pop-corn")

tab1, tab2 = st.tabs(["📝 Введення даних за день", "🔎 Архів минулих днів"])

with tab1:
    if st.query_params.get("edit_auth") == "1":
        st.session_state["edit_ok"] = True

    if not st.session_state.get("edit_ok", False):
        st.info("🔒 Будь ласка, введіть пароль для доступу до форми введення даних.")
        passwd_edit = st.text_input("🔑 Пароль:", type="password", key="pwd_edit")
        if st.button("Увійти", key="btn_login_edit"):
            if passwd_edit == "2000":
                st.session_state["edit_ok"] = True
                st.query_params["edit_auth"] = "1"
                st.rerun()
            elif passwd_edit != "":
                st.error("❌ Невірний пароль для редагування!")
        st.stop() 

    c_lock, _ = st.columns([1, 5])
    if c_lock.button("🔒 Заблокувати касу"):
        st.session_state["edit_ok"] = False
        if "edit_auth" in st.query_params:
            del st.query_params["edit_auth"]
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        selected_date_raw = st.date_input("Дата", datetime.today(), format="DD/MM/YYYY", key="form_date", on_change=on_date_change)
        selected_date = selected_date_raw.strftime('%Y-%m-%d')
    with col2:
        db_start = get_start_balance(selected_date)
        start_balance_raw = st.text_input("Залишок на початок дня:", value=str(db_start), key=f"start_balance_{selected_date}")
        start_balance = get_int(start_balance_raw)

    st.divider()
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("Надходження:")
        inc_df = prepare_df(st.session_state["inc_data"], ["Опис", "Сума"])
        edited_inc_df = st.data_editor(inc_df, column_order=["Опис", "Сума"], num_rows="dynamic", use_container_width=True, key=f"inc_editor_{selected_date}")
        subtotal_inc = sum(get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; font-size: 15px; color: #2e7d32;'>Загалом: {subtotal_inc} грн</p>", unsafe_allow_html=True)
    with col_t2:
        st.subheader("Витрати:")
        exp_df = prepare_df(st.session_state["exp_data"], ["Опис", "Сума"])
        edited_exp_df = st.data_editor(exp_df, column_order=["Опис", "Сума"], num_rows="dynamic", use_container_width=True, key=f"exp_editor_{selected_date}")
        subtotal_exp = sum(get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; font-size: 15px; color: #c62828;'>Загалом: {subtotal_exp} грн</p>", unsafe_allow_html=True)

    st.divider()

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.subheader("Аванси:")
        adv_df = prepare_df(st.session_state["adv_data"], ["Співробітник", "Сума"])
        edited_adv_df = st.data_editor(adv_df, column_order=["Співробітник", "Сума"], num_rows="dynamic", use_container_width=True, key=f"adv_editor_{selected_date}")
        subtotal_adv = sum(get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; font-size: 15px; color: #ef6c00;'>Загалом: {subtotal_adv} грн</p>", unsafe_allow_html=True)
    with col_b2:
        st.subheader("💰 | Факт")
        m_coins = get_int(st.text_input("Монети (загальна сума в грн):", key=f"coins_live_{selected_date}"))
        def cash_row_live(label, multiplier):
            rc1, rc2 = st.columns([3, 2])
            with rc1:
                qty = get_int(st.text_input(f"{label} грн (шт):", key=f"qty_{label}_{selected_date}"))
            with rc2:
                subtotal = qty * multiplier
                st.markdown(f"<div class='cash-sum' style='padding-top: 30px;'>= {subtotal} грн</div>", unsafe_allow_html=True)
            return qty, subtotal
        q_20, v_20 = cash_row_live("20", 20)
        q_50, v_50 = cash_row_live("50", 50)
        q_100, v_100 = cash_row_live("100", 100)
        q_200, v_200 = cash_row_live("200", 200)
        q_500, v_500 = cash_row_live("500", 500)
        q_1000, v_1000 = cash_row_live("1000", 1000)
        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.markdown(f"## 💵 Разом готівки в касі: {cash_pure} грн")

    # --- ІТОГИ ---
    st.divider()
    calculated_end = start_balance + subtotal_inc - subtotal_exp
    total_actual = cash_pure + subtotal_adv
    discrepancy = total_actual - calculated_end
    st.subheader("🏁 Підсумки зміни")
    r1, r2, r3 = st.columns(3)
    r1.metric("Розрахунковий залишок", f"{calculated_end} грн")
    r2.metric("Фактичний залишок", f"{total_actual} грн")
    if discrepancy == 0: r3.success("Каса зійшлася!")
    elif discrepancy > 0: r3.warning(f"Надлишок: +{discrepancy} грн")
    else: r3.error(f"Недостача: {discrepancy} грн")

    # --- КНОПКИ ---
    col_btn_draft, col_btn_final = st.columns(2)
    with col_btn_draft:
        if st.button("💾 ЗБЕРЕГТИ ЧЕРНЕТКУ", use_container_width=True):
            payload = {"inc": edited_inc_df.to_dict('records'), "exp": edited_exp_df.to_dict('records'), "adv": edited_adv_df.to_dict('records'), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers)
            requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})
            st.success("✅ Збережено!")

    with col_btn_final:
        if st.button("🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ", type="primary", use_container_width=True):
            requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
            requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
            requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
            res_shift = requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json={"date": selected_date, "start_balance": str(start_balance), "calculated_end": str(calculated_end), "actual_end": str(total_actual)})
            if res_shift.status_code in [200, 201]:
                inc_rows = [{"date": selected_date, "type": "income", "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_inc_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Опис", "")).strip()]
                exp_rows = [{"date": selected_date, "type": "expense", "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_exp_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Опис", "")).strip()]
                adv_rows = [{"date": selected_date, "employee": str(r.get("Співробітник", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_adv_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Співробітник", "")).strip()]
                if inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=inc_rows)
                if exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=exp_rows)
                if adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=adv_rows)
                requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers)
                st.success("🎉 Звіт записано!")
                st.rerun()

# --- ВКЛАДКА 2: АРХИВ ---
with tab2:
    if st.query_params.get("archive_auth") == "1": st.session_state["archive_ok"] = True
    if not st.session_state.get("archive_ok", False):
        passwd_archive = st.text_input("🔑 Пароль:", type="password", key="pwd_archive")
        if st.button("Доступ до архіву", key="btn_login_arch"):
            if passwd_archive == "2025":
                st.session_state["archive_ok"] = True
                st.query_params["archive_auth"] = "1"
                st.rerun()
        st.stop()

    if st.button("🔒 Закрити архів", key="btn_close_arch"):
        st.session_state["archive_ok"] = False
        if "archive_auth" in st.query_params: del st.query_params["archive_auth"]
        st.rerun()
        
    st.subheader("🔎 Перегляд історії")
    search_date_raw = st.date_input("Оберіть дату", datetime.today(), key="search", format="DD/MM/YYYY")
    search_date = search_date_raw.strftime('%Y-%m-%d')
    shift_res = requests.get(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{search_date}", headers=headers).json()
    
    if isinstance(shift_res, list) and len(shift_res) > 0:
        shift = shift_res[0]
        st.markdown(f"<h3 style='margin-bottom: 0;'>🌅 Залишок на початок дня: <span style='color: #0066cc;'>{get_int(shift.get('start_balance'))} грн</span></h3>", unsafe_allow_html=True)
        st.divider()
        ac1, ac2 = st.columns(2)
        with ac1:
            st.subheader("🟢 Надходження")
            inc_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.income", headers=headers).json()
            total_inc = 0
            if isinstance(inc_res, list) and inc_res:
                for item in inc_res:
                    amt = get_int(item.get('amount'))
                    total_inc += amt
                    st.write(f"• {item.get('description', 'Без опису')}: {amt} грн")
            st.markdown(f"<p style='font-weight: bold;'>Загалом: {total_inc} грн</p>", unsafe_allow_html=True)
        with ac2:
            st.subheader("🔴 Витрати")
            exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.expense", headers=headers).json()
            total_exp = 0
            if isinstance(exp_res, list) and exp_res:
                for item in exp_res:
                    amt = get_int(item.get('amount'))
                    total_exp += amt
                    st.write(f"• {item.get('description', 'Без опису')}: {amt} грн")
            st.markdown(f"<p style='font-weight: bold;'>Загалом: {total_exp} грн</p>", unsafe_allow_html=True)
        st.divider()
        st.markdown(f"<h3 style='margin-bottom: 0;'>🌇 Залишок на кінець дня: <span style='color: #0066cc;'>{get_int(shift.get('calculated_end'))} грн</span></h3>", unsafe_allow_html=True)
        st.divider()
        st.subheader("🟠 Аванси")
        adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{search_date}", headers=headers).json()
        total_adv = 0
        if isinstance(adv_res, list) and adv_res:
            for item in adv_res:
                amt = get_int(item.get('amount'))
                total_adv += amt
                st.write(f"• {item.get('employee', 'Без імені')}: {amt} грн")
        st.markdown(f"<p style='font-weight: bold;'>Загалом: {total_adv} грн</p>", unsafe_allow_html=True)
    else:
        st.warning("За цей день звітів не знайдено.")
