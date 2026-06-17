import streamlit as st
from datetime import datetime, timedelta
import requests
import pandas as pd
import time
import io
import uuid
from PIL import Image

# --- НАЛАШТУВАННЯ БЕЗПЕКИ (КЛЮЧІ ВЗЯТІ З SECRETS) ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Content-Profile": "public",
    "Accept-Profile": "public",
    "Prefer": "return=representation"
}

upload_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "image/jpeg" 
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
                    return [{"Співробітник": item.get('employee', ''), "Сума": get_int(item.get('amount', 0)), "Примітка": ""} for item in res_adv]
    except Exception:
        pass
    return []

def get_previous_coins(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            last_date = res[0].get('date')
            if last_date:
                url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{last_date}"
                res_draft = requests.get(url_draft, headers=headers).json()
                if isinstance(res_draft, list) and len(res_draft) > 0:
                    payload = res_draft[0].get('payload', {})
                    return get_int(payload.get('cash', {}).get('coins', 0))
    except Exception:
        pass
    return 0

def upload_receipts_to_supabase(date_str, receipts_list, supabase_client):
    """Відправляє утиснені чеки і записує дані в базу transactions."""
    if not receipts_list:
        return True
        
    errors = []
    for r in receipts_list:
        safe_name = r['name'].replace(" ", "_").replace("/", "-")
        file_path = f"{date_str}/{r['id']}_{safe_name}"
        
        # 1. Твій існуючий код завантаження в Storage
        url = f"{SUPABASE_URL}/storage/v1/object/receipts/{file_path}"
        try:
            res = requests.post(url, headers=upload_headers, data=r['bytes'])
            
            if res.status_code in [200, 201]:
                # 2. ОДРАЗУ ПІСЛЯ УСПІШНОГО ЗАВАНТАЖЕННЯ пишемо в базу
                supabase_client.table("transactions").insert({
                    "date": date_str,
                    "amount": r['amount'],      # Переконайся, що ці дані є в словнику r
                    "category_id": r['category'],
                    "photo_url": file_path      # Зберігаємо шлях!
                }).execute()
            else:
                errors.append(f"{r['name']}: {res.text}")
        except Exception as e:
            errors.append(f"{r['name']}: {e}")
            
    if errors:
        st.error("❌ Помилки:")
        for err in errors: st.write(err)
        return False
    return True

def prepare_df(data_list, columns):
    if not data_list:
        data_list = [{col: (0 if col == "Сума" else "") for col in columns}]
    df = pd.DataFrame(data_list)
    for col in columns:
        if col not in df.columns:
            df[col] = 0 if col == "Сума" else ""
    if "Сума" in df.columns:
        df["Сума"] = pd.to_numeric(df["Сума"], errors='coerce').fillna(0).astype(int)
    df = df.fillna("")
    return df[columns]

def load_draft_or_init(date_str):
    coins_key = f"coins_live_{date_str}"
    receipts_key = f"receipts_{date_str}"
    
    if receipts_key not in st.session_state:
        st.session_state[receipts_key] = []
        
    try:
        url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}"
        draft_res = requests.get(url_draft, headers=headers).json()
        if isinstance(draft_res, list) and len(draft_res) > 0:
            payload = draft_res[0].get('payload', {})
            st.session_state["inc_data"] = payload.get('inc', [{"Опис": "", "Сума": 0}])
            st.session_state["exp_data"] = payload.get('exp', [{"Опис": "", "Сума": 0}])
            st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": 0, "Примітка": ""}])
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
    st.session_state["adv_data"] = prev_adv if prev_adv else [{"Співробітник": "", "Сума": 0, "Примітка": ""}]
    
    prev_coins = get_previous_coins(date_str)
    st.session_state[coins_key] = str(prev_coins)
    
    for k in [20, 50, 100, 200, 500, 1000]:
        st.session_state[f"qty_{k}_{date_str}"] = "0"

# --- НАЛАШТУВАННЯ СТОРІНКИ ТА CSS ---
st.set_page_config(layout="wide", page_title="Cafe Forchino")

st.markdown("""
<style>
    .stApp, header[data-testid="stHeader"] { background-color: #FAF0E6 !important; }
    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp label, .stApp li { color: #111827 !important; }
    p[style*="#2e7d32"] { color: #2e7d32 !important; }
    p[style*="#c62828"] { color: #c62828 !important; }
    p[style*="#ef6c00"] { color: #ef6c00 !important; }
    span[style*="#0066cc"] { color: #0066cc !important; }

    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 1px solid #d1d5db !important;
    }
    input, .stSelectbox span { color: #111827 !important; }

    .stTextInput div[data-baseweb="input"] { height: 35px !important; }
    .stTextInput input { padding: 5px !important; }
    
    .fact-block [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; }
    .fact-block [data-testid="column"] { width: auto !important; flex: 1 1 0% !important; min-width: 0 !important; }
    
    #floating-anchor { display: none; }
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"],
    .element-container:has(#floating-anchor) + .element-container {
        position: fixed !important; top: 65px !important; right: 20px !important; left: auto !important; z-index: 1000 !important; width: 50px !important;
    }
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button,
    .element-container:has(#floating-anchor) + .element-container button {
        width: 50px !important; height: 50px !important; padding: 0 !important; border-radius: 12px !important; 
        background: linear-gradient(135deg, #f3f4f6, #e5e7eb) !important; color: #4b5563 !important; 
        border: 1px solid #d1d5db !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; 
        display: flex !important; align-items: center !important; justify-content: center !important; transition: transform 0.2s, box-shadow 0.2s !important;
    }
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button:hover,
    .element-container:has(#floating-anchor) + .element-container button:hover {
        transform: translateY(-2px) !important; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.2) !important; background: linear-gradient(135deg, #e5e7eb, #d1d5db) !important;
    }
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button div,
    .element-container:has(#floating-anchor) + .element-container button div,
    div[data-testid="stElementContainer"]:has(#floating-anchor) + div[data-testid="stElementContainer"] button p,
    .element-container:has(#floating-anchor) + .element-container button p {
        font-size: 26px !important; margin: 0 !important; padding: 0 !important; width: 100% !important; display: flex !important; justify-content: center !important; align-items: center !important; color: #4b5563 !important; 
    }
</style>
""", unsafe_allow_html=True)

# --- ШАПКА ДОДАТКУ ---
st.title("Cafe Forchino")

with st.popover("🚀 Версія: Stable 2.5 Global (Історія змін)"):
    st.markdown("""
    **Stable 2.5 Global (Поточна):**
    - 🗓 **Дати:** Жорстко зафіксовано формат дат (ДД/ММ/РРРР).
    - 📸 **Фото-чеки (LIVE):** Реалізовано повний цикл роботи з чеками. При натисканні "Зберегти фінальний звіт" утиснені фото автоматично відправляються в хмару Supabase Storage у папку відповідної дати зміни.
    """)

st.markdown("*Розроблено Богданом для cafe forchino з любов'ю 🧡*")
st.write("") 

# --- ІНІЦІАЛІЗАЦІЯ ДАТИ ---
if "form_date" not in st.session_state:
    st.session_state["form_date"] = datetime.today()

st.session_state["form_date"] = st.date_input("Оберіть дату:", st.session_state["form_date"], format="DD/MM/YYYY")
selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date

receipts_key = f"receipts_{selected_date}"
if receipts_key not in st.session_state:
    st.session_state[receipts_key] = []

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
            c_header, c_btn = st.columns([3, 1])
            with c_header:
                st.subheader("Витрати:")
            with c_btn:
                with st.popover("📷 Чеки"):
                    ufs = st.file_uploader("Виберіть файли", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"uploader_{selected_date}")
                    if st.button("➕ Завантажити вибрані", use_container_width=True) and ufs:
                        for uf in ufs:
                            if not any(r['name'] == uf.name for r in st.session_state[receipts_key]):
                                try:
                                    img = Image.open(uf)
                                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                                    img.thumbnail((1024, 1024)) 
                                    buf = io.BytesIO()
                                    img.save(buf, format="JPEG", quality=70) 
                                    st.session_state[receipts_key].append({"id": str(uuid.uuid4()), "name": uf.name, "bytes": buf.getvalue()})
                                except Exception as e:
                                    st.error(f"Помилка з файлом {uf.name}: {e}")
                        st.success("✅ Збережено в пам'ять!")
                        time.sleep(1)
                        st.rerun()
                    
                    if st.session_state[receipts_key]:
                        st.write("---")
                        st.write("📁 Готові до відправки:")
                        for r in st.session_state[receipts_key]:
                            col_img, col_del = st.columns([3, 1])
                            col_img.image(r["bytes"])
                            if col_del.button("❌", key=f"del_{r['id']}"):
                                st.session_state[receipts_key] = [x for x in st.session_state[receipts_key] if x["id"] != r["id"]]
                                st.rerun()

            exp_df = prepare_df(st.session_state["exp_data"], ["Опис", "Сума"])
            edited_exp_df = st.data_editor(exp_df, num_rows="dynamic", use_container_width=True, key=f"exp_editor_{selected_date}")
            subtotal_exp = sum(get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows())
            st.markdown(f"<p style='font-weight: bold; color: #c62828;'>Загалом: {subtotal_exp} грн</p>", unsafe_allow_html=True)

        st.divider()

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.subheader("Аванси:")
            adv_df = prepare_df(st.session_state["adv_data"], ["Співробітник", "Сума", "Примітка"])
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
        
        st.markdown('<div id="floating-anchor"></div>', unsafe_allow_html=True)
        if st.button("💾", key="fab_save"):
            payload = {"inc": edited_inc_df.to_dict('records'), "exp": edited_exp_df.to_dict('records'), "adv": edited_adv_df.to_dict('records'), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers)
            requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})
            st.toast("✅ Дані збережено!", icon="💾")

        if st.button("🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ", type="primary", use_container_width=True):
            with st.spinner("Відправка звіту та чеків..."):
                files_ok = upload_receipts_to_supabase(selected_date, st.session_state[receipts_key])
                if not files_ok:
                    st.stop()
                
                requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
                requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
                requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
                
                shift_payload = {"date": selected_date, "start_balance": str(start_balance), "calculated_end": str(calculated_end), "actual_end": str(total_actual)}
                res_shift = requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json=shift_payload)
                
                if res_shift.status_code in [200, 201]:
                    inc_rows = [{"date": selected_date, "type": "income", "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_inc_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Опис", "")).strip()]
                    exp_rows = [{"date": selected_date, "type": "expense", "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in edited_exp_df.iterrows() if get_int(r.get("Сума", 0)) != 0 or str(r.get("Опис", "")).strip()]
                    
                    adv_rows = []
                    for _, r in edited_adv_df.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        emp = str(r.get("Співробітник", "")).strip()
                        raw_note = r.get("Примітка", "")
                        safe_note = str(raw_note).strip() if pd.notna(raw_note) and str(raw_note).lower() != 'nan' else ""
                        if amt != 0 or emp:
                            adv_rows.append({"date": selected_date, "employee": emp, "amount": str(amt), "note": safe_note})
                            
                    if inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=inc_rows)
                    if exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=exp_rows)
                    if adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=adv_rows)
                    
                    st.success("🎉 Звіт та чеки успішно збережено в хмарі!")
                    st.session_state[receipts_key] = []
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
                    
                    note_val = item.get('note')
                    safe_note = str(note_val).strip() if note_val else ""
                    note_str = f" <i>— {safe_note}</i>" if safe_note else ""
                    
                    st.markdown(f"• {item.get('employee', 'Без імені')}: {amt} грн{note_str}", unsafe_allow_html=True)
            else:
                st.write("Немає записів")
            st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {total_adv} грн</p>", unsafe_allow_html=True)
            
            # ========================================================
            # НОВЫЙ БЛОК: ГАЛЕРЕЯ ЧЕКОВ ДЛЯ СМЕНЫ
            # ========================================================
            st.divider()
            st.subheader("🖼️ Галерея чеків за зміну")
            
            # Запрашиваем список файлов в бакете 'receipts', которые лежат в папке выбранной даты
            list_files_url = f"{SUPABASE_URL}/storage/v1/object/list/receipts"
            try:
                # Передаем префикс в виде даты (например, "2026-06-18")
                storage_res = requests.post(list_files_url, headers=headers, json={"prefix": search_date})
                
                if storage_res.status_code == 200:
                    files_list = storage_res.json()
                    
                    # Фильтруем системные заглушки, если они есть
                    valid_files = [f for f in files_list if f.get('name') != '.emptyFolderPlaceholder']
                    
                    if valid_files:
                        # Строим сетку из 3 колонок под картинки
                        img_cols = st.columns(3)
                        for idx, file_obj in enumerate(valid_files):
                            file_name = file_obj['name']
                            # Собираем прямой публичный URL к файлу
                            img_url = f"{SUPABASE_URL}/storage/v1/object/public/receipts/{search_date}/{file_name}"
                            
                            # Распределяем картинки по колонкам
                            with img_cols[idx % 3]:
                                st.image(img_url, use_container_width=True)
                    else:
                        st.info("Чеки для цієї зміни не завантажувались.")
                else:
                    st.warning("Не вдалося отримати список файлів зі сховища.")
            except Exception as e:
                st.error(f"Помилка при запиті галереї: {e}")
            # ========================================================
            
        else:
            st.warning("За цей день звітів не знайдено в хмарі.")
