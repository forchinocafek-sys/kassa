import streamlit as st
from datetime import datetime, timedelta
import requests
import pandas as pd
import time

# --- НАСТРОЙКИ ДОСТУПУ ДО SUPABASE ---
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

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
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

# --- НАЛАШТУВАННЯ СТОРІНКИ ТА CSS ---
st.set_page_config(layout="wide", page_title="Cafe Forchino")

st.markdown("""
<style>
    /* Компактні поля вводу */
    .stTextInput div[data-baseweb="input"] { height: 35px !important; }
    .stTextInput input { padding: 5px !important; }
    
    /* Верстка блоку Факт */
    .fact-block [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; }
    .fact-block [data-testid="column"] { width: auto !important; flex: 1 1 0% !important; min-width: 0 !important; }
    
    /* МІНІМАЛІСТИЧНА ПЛАВАЮЧА КНОПКА (Правий верхній кут, світло-сіра) */
    #floating-anchor { display: none; }
    
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"],
    .element-container:has(#floating-anchor) + .element-container {
        position: fixed !important;
        top: 65px !important;  
        right: 20px !important; 
        left: auto !important;  
        z-index: 1000 !important;
        width: 50px !important;
    }
    
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button,
    .element-container:has(#floating-anchor) + .element-container button {
        width: 50px !important;
        height: 50px !important;
        padding: 0 !important; /* Обнуляємо стандартні відступи Streamlit */
        border-radius: 12px !important; 
        background: linear-gradient(135deg, #f3f4f6, #e5e7eb) !important; 
        color: #4b5563 !important; 
        border: 1px solid #d1d5db !important; 
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; 
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: transform 0.2s, box-shadow 0.2s !important;
    }
    
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button:hover,
    .element-container:has(#floating-anchor) + .element-container button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 15px rgba(0, 0, 0, 0.2) !important;
        background: linear-gradient(135deg, #e5e7eb, #d1d5db) !important;
    }
    
    /* Ідеальне центрування дискети всередині кнопки */
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button div,
    .element-container:has(#floating-anchor) + .element-container button div,
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button p,
    .element-container:has(#floating-anchor) + .element-container button p {
        font-size: 26px !important;
        margin: 0 !important;
        padding: 0 !important;
        width: 100% !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
    }
</style>
""", unsafe_allow_html=True)

# --- ШАПКА ДОДАТКУ ---
st.title("Cafe Forchino")

# Розширена історія останніх 5 версій
with st.popover("🚀 Версія: Stable 2.2 (Історія змін)"):
    st.markdown("""
    **Stable 2.2 (Поточна):**
    - 🎯 Ідеально відцентровано іконку дискети (виправлено зсув вправо через стандартні відступи Streamlit).
    
    **Stable 2.1:**
    - 🎨 Кнопку збереження чернетки переміщено у *правий верхній кут* та змінено на стриманий світло-сірий колір.
    - 📜 Журнал змін розширено до 5 останніх версій.
    
    **Stable 2.0:**
    - 🎨 Новий дизайн кнопки збереження (заокруглений квадрат).
    - 🗓 Стабільний календар (видалено конфліктні стрілочки навігації).
    - 💾 Дані в таблицях більше не очищаються після відправки фінального звіту.
    
    **Stable 1.9:**
    - 🗑 Видалено селектор адміністратора для забезпечення 100% сумісності з базою даних.
    - ⚡️ Оптимізовано швидкість надсилання фінального звіту.
    """)

st.markdown("*Розроблено Богданом для cafe forchino з любов'ю 🧡*")
st.write("") 

# --- ІНІЦІАЛІЗАЦІЯ ДАТИ ---
if "form_date" not in st.session_state:
    st.session_state["form_date"] = datetime.today()

selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date

# --- ВКЛАДКИ ---
tab1, tab2 = st.tabs(["📝 Введення даних", "🔎 Архів"])

# ==========================================
# ВКЛАДКА 1: КАСА
# ==========================================
with tab1:
    if st.query_params.get("edit_auth") == "1": 
        st.session_state["edit_ok"] = True

    if not st.session_state.get("edit_ok", False):
        st.info("🔒 Введіть пароль для доступу до форми введення даних.")
        passwd_edit = st.text_input("🔑 Пароль:", type="password", key="pwd_edit")
        if st.button("Увійти", key="btn_login_edit"):
            if passwd_edit == "2000":
                st.session_state["edit_ok"] = True
                st.query_params["edit_auth"] = "1"
                st.rerun()
            elif passwd_edit != "":
                st.error("❌ Невірний пароль!")
    else:
        c_lock, _ = st.columns([1, 5])
        if c_lock.button("🔒 Заблокувати касу"):
            st.session_state["edit_ok"] = False
            if "edit_auth" in st.query_params: del st.query_params["edit_auth"]
            st.rerun()

        # Календар
        st.session_state["form_date"] = st.date_input("Оберіть дату:", st.session_state["form_date"])
        selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
        
        db_start = get_start_balance(selected_date)
        start_balance = get_int(st.text_input("Залишок на початок дня:", value=str(db_start), key=f"start_balance_{selected_date}"))

        st.divider()
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.subheader("Надходження:")
            inc_df = prepare_df(st.session_state["inc_data"], ["Опис", "Сума"])
            edited_inc_df = st.data_editor(inc_df, num_rows="dynamic", use_container_width=True, key=f"inc_editor_{selected_date}")
            subtotal_inc = sum(get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows())
            st.markdown(f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {subtotal_inc} грн</p>", unsafe_allow_html=True)
            
        with col_t2:
            st.subheader("Витрати:")
            exp_df = prepare_df(st.session_state["exp_data"], ["Опис", "Сума"])
            edited_exp_df = st.data_editor(exp_df, num_rows="dynamic", use_container_width=True, key=f"exp_editor_{selected_date}")
            subtotal_exp = sum(get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows())
            st.markdown(f"<p style='font-weight: bold; color: #c62828;'>Загалом: {subtotal_exp} грн</p>", unsafe_allow_html=True)

        st.divider()

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.subheader("Аванси:")
            adv_df = prepare_df(st.session_state["adv_data"], ["Співробітник", "Сума"])
            edited_adv_df = st.data_editor(adv_df, num_rows="dynamic", use_container_width=True, key=f"adv_editor_{selected_date}")
            subtotal_adv = sum(get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows())
            st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {subtotal_adv} грн</p>", unsafe_allow_html=True)

        with col_b2:
            st.subheader("💰 | Факт")
            m_coins = get_int(st.text_input("Монети (загальна сума):", key=f"coins_live_{selected_date}"))
            
            st.markdown('<div class="fact-block">', unsafe_allow_html=True)
            def cash_row_live(label, multiplier):
                c1, c2 = st.columns([1, 4])
                with c1: 
                    st.markdown(f"<div style='margin-top: 8px; font-weight: bold; font-size: 16px;'>{label}</div>", unsafe_allow_html=True)
                with c2: 
                    qty = get_int(st.text_input(f"q{label}", label_visibility="collapsed", key=f"qty_{label}_{selected_date}"))
                return qty, qty * multiplier

            q_20, v_20 = cash_row_live("20", 20)
            q_50, v_50 = cash_row_live("50", 50)
            q_100, v_100 = cash_row_live("100", 100)
            q_200, v_200 = cash_row_live("200", 200)
            q_500, v_500 = cash_row_live("500", 500)
            q_1000, v_1000 = cash_row_live("1000", 1000)
            st.markdown('</div>', unsafe_allow_html=True)
            
            cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
            st.markdown(f"## 💵 Разом в касі: {cash_pure} грн")

        st.divider()
        calculated_end = start_balance + subtotal_inc - subtotal_exp
        total_actual = cash_pure + subtotal_adv
        discrepancy = total_actual - calculated_end

        st.subheader("🏁 Підсумки зміни")
        res_c1, res_c2, res_c3 = st.columns(3)
        res_c1.metric("Розрахунок", f"{calculated_end} грн")
        res_c2.metric("Факт", f"{total_actual} грн")
        if discrepancy == 0: res_c3.success("Зійшлася!")
        elif discrepancy > 0: res_c3.warning(f"+{discrepancy} грн")
        else: res_c3.error(f"{discrepancy} грн")

        st.write("") 
        
        # --- ДИНАМІЧНА ПЛАВАЮЧА КНОПКА ЗБЕРЕЖЕННЯ ---
        st.markdown('<div id="floating-anchor"></div>', unsafe_allow_html=True)
        if st.button("💾", key="fab_save"):
            payload = {"inc": edited_inc_df.to_dict('records'), "exp": edited_exp_df.to_dict('records'), "adv": edited_adv_df.to_dict('records'), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers)
            requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})
            st.toast("✅ Дані збережено!", icon="💾")

        # Фінальний звіт 
        if st.button("🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ", type="primary", use_container_width=True):
            with st.spinner("Відправка..."):
                requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
                requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
                requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
                
                shift_payload = {
                    "date": selected_date, 
                    "start_balance": str(start_balance), 
                    "calculated_end": str(calculated_end), 
                    "actual_end": str(total_actual)
                }
                
                res_shift = requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json=shift_payload)
                
                if res_shift.status_code in [200, 201]:
                    inc_rows = [{"date": selected_date, "type": "income", "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_inc_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Опис", "")).strip()]
                    exp_rows = [{"date": selected_date, "type": "expense", "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_exp_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Опис", "")).strip()]
                    adv_rows = [{"date": selected_date, "employee": str(r.get("Співробітник", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_adv_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Співробітник", "")).strip()]
                    if inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=inc_rows)
                    if exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=exp_rows)
                    if adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=adv_rows)
                    
                    st.success("🎉 Звіт успішно записано в архів!")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error(f"❌ Помилка бази даних: {res_shift.text}")

# ==========================================
# ВКЛАДКА 2: АРХІВ
# ==========================================
with tab2:
    if st.query_params.get("archive_auth") == "1":
        st.session_state["archive_ok"] = True

    if not st.session_state.get("archive_ok", False):
        st.info("🔒 Введіть пароль для доступу до архіву.")
        passwd_archive = st.text_input("🔑 Пароль:", type="password", key="pwd_archive")
        if st.button("Доступ до архіву", key="btn_login_arch"):
            if passwd_archive == "2025":
                st.session_state["archive_ok"] = True
                st.query_params["archive_auth"] = "1"
                st.rerun()
            elif passwd_archive != "":
                st.error("❌ Невірний пароль!")
    else:
        c_lock_arch, _ = st.columns([1, 5])
        if c_lock_arch.button("🔒 Закрити архів", key="btn_close_arch"):
            st.session_state["archive_ok"] = False
            if "archive_auth" in st.query_params: del st.query_params["archive_auth"]
            st.rerun()
            
        st.subheader("🔎 Перегляд історії")
        search_date_raw = st.date_input("Оберіть дату", datetime.today(), key="search", format="DD/MM/YYYY")
        search_date = search_date_raw.strftime('%Y-%m-%d')
        
        url_shift_search = f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{search_date}"
        shift_res = requests.get(url_shift_search, headers=headers).json()
        
        if isinstance(shift_res, list) and len(shift_res) > 0:
            shift = shift_res[0]
            
            st.markdown(f"<h3 style='margin-bottom: 0;'>🌅 Залишок на початок: <span style='color: #0066cc;'>{get_int(shift.get('start_balance'))} грн</span></h3>", unsafe_allow_html=True)
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
                else:
                    st.write("Немає записів")
                st.markdown(f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {total_inc} грн</p>", unsafe_allow_html=True)
                
            with ac2:
                st.subheader("🔴 Витрати")
                exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{search_date}&type=eq.expense", headers=headers).json()
                total_exp = 0
                if isinstance(exp_res, list) and exp_res:
                    for item in exp_res:
                        amt = get_int(item.get('amount'))
                        total_exp += amt
                        st.write(f"• {item.get('description', 'Без опису')}: {amt} грн")
                else:
                    st.write("Немає записів")
                st.markdown(f"<p style='font-weight: bold; color: #c62828;'>Загалом: {total_exp} грн</p>", unsafe_allow_html=True)
                    
            st.divider()
            st.markdown(f"<h3 style='margin-bottom: 0;'>🌇 Залишок на кінець: <span style='color: #0066cc;'>{get_int(shift.get('calculated_end'))} грн</span></h3>", unsafe_allow_html=True)
            st.divider()
            
            st.subheader("🟠 Аванси")
            adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{search_date}", headers=headers).json()
            total_adv = 0
            if isinstance(adv_res, list) and adv_res:
                for item in adv_res:
                    amt = get_int(item.get('amount'))
                    total_adv += amt
                    st.write(f"• {item.get('employee', 'Без імені')}: {amt} грн")
            else:
                st.write("Немає записів")
            st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {total_adv} грн</p>", unsafe_allow_html=True)
            
        else:
            st.warning("За цей день звітів не знайдено в хмарі.")
