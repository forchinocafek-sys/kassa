import streamlit as st
from datetime import datetime, timedelta
import requests
import pandas as pd
import time
import io
import uuid
import base64
import json
from PIL import Image
import streamlit.components.v1 as components

# --- НАЛАШТУВАННЯ БЕЗПЕКИ ---
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

# --- ДОПОМІЖНІ ФУНКЦІЇ ТА РОЗУМНЕ КЕШУВАННЯ ---

@st.cache_data(ttl=60)
def get_start_balance(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return get_int(res[0].get('calculated_end', 0))
    except Exception:
        pass
    return 0

@st.cache_data(ttl=60)
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

@st.cache_data(ttl=60)
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

def get_int(val):
    try:
        if pd.isna(val): return 0 
        if not val: return 0
        clean_val = str(val).strip().replace(" ", "")
        if clean_val in ("None", "<NA>", "nan", ""): return 0
        return int(float(clean_val))
    except Exception:
        return 0

# ПАКЕТНЕ ЗАВАНТАЖЕННЯ ТИЖНЯ (Один запит до бази замість семи)
def prefetch_week_window(center_date_obj):
    if "drafts_cache" not in st.session_state:
        st.session_state["drafts_cache"] = {}
    
    start_date = (center_date_obj - timedelta(days=3)).strftime('%Y-%m-%d')
    end_date = (center_date_obj + timedelta(days=3)).strftime('%Y-%m-%d')
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/drafts?date=gte.{start_date}&date=lte.{end_date}"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list):
            for row in res:
                d = row.get('date')
                st.session_state["drafts_cache"][d] = row.get('payload', {})
    except Exception:
        pass

def upload_receipts_to_supabase(date_str, receipts_list):
    if not receipts_list:
        return True
        
    errors = []
    for r in receipts_list:
        safe_name = r['name'].replace(" ", "_").replace("/", "-")
        file_path = f"{date_str}/{r['id']}_{safe_name}"
        url = f"{SUPABASE_URL}/storage/v1/object/receipts/{file_path}"
        
        try:
            res = requests.post(url, headers=upload_headers, data=r['bytes'])
            if res.status_code not in [200, 201]:
                errors.append(f"{r['name']}: {res.text}")
        except Exception as e:
            errors.append(f"{r['name']}: {e}")
            
    if errors:
        st.error("❌ Деякі чеки не завантажилися в хмару:")
        for err in errors: st.write(err)
        return False
    return True

def prepare_df(data_list, columns):
    if not data_list:
        data_list = [{col: (None if col == "Сума" else "") for col in columns}]
    df = pd.DataFrame(data_list)
    for col in columns:
        if col not in df.columns:
            df[col] = None if col == "Сума" else ""
    if "Сума" in df.columns:
        df["Сума"] = pd.to_numeric(df["Сума"], errors='coerce').astype('Int64')
    for col in columns:
        if col != "Сума":
            df[col] = df[col].fillna("")
    return df[columns]

def load_draft_or_init(date_str):
    coins_key = f"coins_live_{date_str}"
    receipts_key = f"receipts_{date_str}"
    
    if receipts_key not in st.session_state:
        st.session_state[receipts_key] = []
        
    # МИТТЄВА ЗАВАНТАЖЕННЯ З ОПЕРАТИВНОЇ ПАМ'ЯТІ (Якщо день є в тижневому вікні)
    if "drafts_cache" in st.session_state and date_str in st.session_state["drafts_cache"]:
        payload = st.session_state["drafts_cache"][date_str]
        st.session_state["inc_data"] = payload.get('inc', [{"Опис": "", "Сума": None}])
        st.session_state["exp_data"] = payload.get('exp', [{"Опис": "", "Сума": None}])
        st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": None, "Примітка": ""}])
        cash_data = payload.get('cash', {})
        c_coins = cash_data.get('coins', 0)
        st.session_state[coins_key] = str(c_coins) if c_coins else ""
        for k in [20, 50, 100, 200, 500, 1000]:
            c_val = cash_data.get(str(k), 0)
            st.session_state[f"qty_{k}_{date_str}"] = str(c_val) if c_val else ""
        return
        
    # Резервний одиночний запит, якщо вийшли за межі вікна тижня
    try:
        url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}"
        draft_res = requests.get(url_draft, headers=headers).json()
        if isinstance(draft_res, list) and len(draft_res) > 0:
            payload = draft_res[0].get('payload', {})
            if "drafts_cache" not in st.session_state:
                st.session_state["drafts_cache"] = {}
            st.session_state["drafts_cache"][date_str] = payload
            
            st.session_state["inc_data"] = payload.get('inc', [{"Опис": "", "Сума": None}])
            st.session_state["exp_data"] = payload.get('exp', [{"Опис": "", "Сума": None}])
            st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": None, "Примітка": ""}])
            cash_data = payload.get('cash', {})
            c_coins = cash_data.get('coins', 0)
            st.session_state[coins_key] = str(c_coins) if c_coins else ""
            for k in [20, 50, 100, 200, 500, 1000]:
                c_val = cash_data.get(str(k), 0)
                st.session_state[f"qty_{k}_{date_str}"] = str(c_val) if c_val else ""
            return
    except Exception:
        pass
    
    # Ініціалізація порожнього дня, якщо записів взагалі немає ніде
    st.session_state["inc_data"] = [{"Опис": "", "Сума": None}]
    st.session_state["exp_data"] = [{"Опис": "", "Сума": None}]
    
    prev_adv = get_previous_advances(date_str)
    st.session_state["adv_data"] = prev_adv if prev_adv else [{"Співробітник": "", "Сума": None, "Примітка": ""}]
    
    prev_coins = get_previous_coins(date_str)
    st.session_state[coins_key] = str(prev_coins) if prev_coins else ""
    
    for k in [20, 50, 100, 200, 500, 1000]:
        st.session_state[f"qty_{k}_{date_str}"] = ""

# --- НАЛАШТУВАННЯ СТОРІНКИ ТА ПАСПОРТ ДОДАТКУ (PWA) ---
ICON_URL = "https://ajkprfhuypcamnybqusr.supabase.co/storage/v1/object/public/assets/xHJLUtG-wHDFARC-LtBbXJE_original.png?v=2"

st.set_page_config(layout="wide", page_title="Cafe Forchino", page_icon=ICON_URL)

manifest = {
    "name": "Cafe Forchino",
    "short_name": "Forchino",
    "theme_color": "#FAF0E6",
    "background_color": "#FAF0E6",
    "display": "standalone",
    "orientation": "portrait",
    "icons": [{"src": ICON_URL, "sizes": "512x512", "type": "image/png"}]
}
manifest_b64 = base64.b64encode(json.dumps(manifest).encode()).decode()

components.html(f"""
<script>
    const doc = window.parent.document;
    let manifest = doc.createElement('link');
    manifest.rel = 'manifest';
    manifest.href = 'data:application/manifest+json;base64,{manifest_b64}';
    doc.head.appendChild(manifest);

    let appleIcon = doc.createElement('link');
    appleIcon.rel = 'apple-touch-icon';
    appleIcon.href = '{ICON_URL}';
    doc.head.appendChild(appleIcon);

    let appleTitle = doc.createElement('meta');
    appleTitle.name = 'apple-mobile-web-app-title';
    appleTitle.content = 'Forchino';
    doc.head.appendChild(appleTitle);

    // Розумне авто-перезавантаження при розгортанні (Варіант 1)
    let lastActiveTime = Date.now();
    doc.addEventListener('visibilitychange', function() {{
        if (doc.visibilityState === 'visible') {{
            let timeAway = (Date.now() - lastActiveTime) / 1000;
            // Якщо додаток був згорнутий довше 45 секунд — м'яко перезавантажуємо сторінку
            if (timeAway > 45) {{
                window.parent.location.reload();
            }}
        }} else {{
            lastActiveTime = Date.now();
        }}
    }});
</script>
""", height=0, width=0)

# --- НАЛАШТУВАННЯ СТИЛІВ CSS ---
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
    
    #is-floating { display: none; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) {
        position: fixed !important; 
        top: 60px !important; 
        right: 15px !important; 
        z-index: 99999 !important; 
        width: 50px !important; 
        display: flex !important;
        flex-direction: column !important; 
        gap: 12px !important; 
        background: transparent !important;
        padding: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) > div[data-testid="column"] {
        width: 50px !important; min-width: 50px !important; max-width: 50px !important; height: 50px !important; flex: 0 0 50px !important;
        margin: 0 !important; padding: 0 !important; display: flex !important; justify-content: center !important; align-items: center !important;
    }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) > div[data-testid="column"] > div {
        width: 100% !important; height: 100% !important; display: flex !important; justify-content: center !important; align-items: center !important; margin: 0 !important; padding: 0 !important;
    }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button {
        width: 50px !important; min-width: 50px !important; height: 50px !important; min-height: 50px !important; padding: 0 !important; margin: 0 !important;
        border-radius: 12px !important; background: linear-gradient(135deg, #f3f4f6, #e5e7eb) !important; color: #4b5563 !important; border: 1px solid #d1d5db !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; display: flex !important; align-items: center !important; justify-content: center !important; transition: transform 0.2s, box-shadow 0.2s !important;
    }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button:hover {
        transform: translateY(-2px) !important; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.2) !important; background: linear-gradient(135deg, #e5e7eb, #d1d5db) !important;
    }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button p { font-size: 20px !important; margin: 0 !important; padding: 0 !important; line-height: 1 !important; }
</style>
""", unsafe_allow_html=True)

# --- ШАПКА ДОДАТКУ ---
st.title("Cafe Forchino")

with st.popover("🚀 Версія: fin 1.2.0 (Auto-Refresh Update)"):
    st.markdown("""
    **Останні оновлення:**
    * **v1.2.0 (Розумне автообновлення):** * Інтегровано невидимий JS-таймер «анти-засипання». Якщо додаток згорнуто довше 45 секунд, при розгортанні сторінка м'яко перезавантажиться сама, запобігаючи вильоту червоних помилок з'єднання Streamlit.
    * **v1.1.0 (Миттєве вікно тижня):** Пакетна загрузка 7 днів одночасно при запуску (переключення дат за 0 секунд) та збереження повної історії.
    * **v1.0.0 (Фінальний запуск):** Додано PWA-модуль, блокування початкового залишку, автозбереження черновика у фінальну кнопку та фактичну готівку в Архів.
    """)

st.markdown("*Розроблено Богданом для cafe forchino з любов'ю 🧡*")
st.write("") 

# --- ІНІЦІАЛІЗАЦІЯ СТАНУ ТА ТИЖНЕВОГО КЕШУ ---
if "form_date" not in st.session_state:
    st.session_state["form_date"] = datetime.today()
    # ПЕРШИЙ СТАРТ: Завантажуємо весь тиждень в пам'ять одним махом
    prefetch_week_window(st.session_state["form_date"])

if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "Касса"

selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')

# === [ВИПРАВЛЕННЯ ТУТ: Захист від очищення пам'яті Streamlit] ===
# Якщо Streamlit видалив поля при переході в Архів, примусово відновлюємо їх з кешу
coins_key = f"coins_live_{selected_date}"
if coins_key not in st.session_state:
    st.session_state["current_loaded_date"] = None
# ================================================================

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date

receipts_key = f"receipts_{selected_date}"
if receipts_key not in st.session_state:
    st.session_state[receipts_key] = []


# ==========================================
# РОЗДІЛ 1: КАСА
# ==========================================
if st.session_state["active_tab"] == "Касса":
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
        network_lock, _ = st.columns([1, 5])
        if network_lock.button("🔒 Заблокувати касу"):
            st.session_state["edit_ok"] = False
            if "edit_auth" in st.query_params: del st.query_params["edit_auth"]
            st.rerun()
        
        db_start = get_start_balance(selected_date)
        start_balance = get_int(db_start)
        st.text_input("Залишок на початок дня (автоматично):", value=str(start_balance), disabled=True, key=f"start_balance_{selected_date}")

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
            m_coins = get_int(st.text_input("Монети (загальна сума):", placeholder="0", key=f"coins_live_{selected_date}"))
            
            st.markdown('<div class="fact-block">', unsafe_allow_html=True)
            def cash_row_live(label, multiplier):
                c1, c2 = st.columns([1, 4])
                with c1: 
                    st.markdown(f"<div style='margin-top: 8px; font-weight: bold; font-size: 16px;'>{label}</div>", unsafe_allow_html=True)
                with c2: 
                    qty = get_int(st.text_input(f"q{label}", label_visibility="collapsed", placeholder="0", key=f"qty_{label}_{selected_date}"))
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

        if st.button("🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ", type="primary", use_container_width=True):
            with st.spinner("Відправка звіту та чеків..."):
                payload = {"inc": edited_inc_df.to_dict('records'), "exp": edited_exp_df.to_dict('records'), "adv": edited_adv_df.to_dict('records'), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
                requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers)
                requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})

                if "drafts_cache" not in st.session_state: st.session_state["drafts_cache"] = {}
                st.session_state["drafts_cache"][selected_date] = payload
                st.cache_data.clear() 

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

        # --- ПЛАВАЮЧЕ МЕНЮ (ДЛЯ КАСИ) ---
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
            with st.popover("☰"):
                nav = st.radio("Розділ:", ["Касса", "Архів"], index=0, label_visibility="collapsed")
                if nav != "Касса":
                    st.session_state["active_tab"] = nav
                    st.rerun()
        with fc2:
            with st.popover("📅"):
                d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
                if d != st.session_state["form_date"]:
                    st.session_state["form_date"] = d
                    prefetch_week_window(d)
                    st.rerun()
        with fc3:
            if st.button("💾", key="fab_save"):
                payload = {"inc": edited_inc_df.to_dict('records'), "exp": edited_exp_df.to_dict('records'), "adv": edited_adv_df.to_dict('records'), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
                requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers)
                requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})
                
                if "drafts_cache" not in st.session_state: st.session_state["drafts_cache"] = {}
                st.session_state["drafts_cache"][selected_date] = payload
                st.cache_data.clear()
                
                st.toast("✅ Дані збережено в пам'ять тижня!", icon="💾")

# ==========================================
# РОЗДІЛ 2: АРХІВ
# ==========================================
elif st.session_state["active_tab"] == "Архів":
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
            
        st.subheader(f"🔎 Перегляд історії: {selected_date}")
        
        url_shift_search = f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}"
        shift_res = requests.get(url_shift_search, headers=headers).json()
        
        if isinstance(shift_res, list) and len(shift_res) > 0:
            shift = shift_res[0]
            calc_end = get_int(shift.get('calculated_end'))
            
            st.markdown(f"<h3 style='margin-bottom: 0;'>🌅 Залишок на початок: <span style='color: #0066cc;'>{get_int(shift.get('start_balance'))} грн</span></h3>", unsafe_allow_html=True)
            st.divider()
            
            ac1, ac2 = st.columns(2)
            with ac1:
                st.subheader("🟢 Надходження")
                inc_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.income", headers=headers).json()
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
                exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.expense", headers=headers).json()
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
            st.markdown(f"<h3 style='margin-bottom: 0;'>🌇 Залишок на кінець: <span style='color: #0066cc;'>{calc_end} грн</span></h3>", unsafe_allow_html=True)
            st.divider()
            
            st.subheader("🟠 Аванси")
            adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers).json()
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
            
            st.divider()
            actual_cash = calc_end - total_adv
            st.markdown(f"<h3 style='margin-bottom: 0; color: #4b5563;'>💵 Фактично готівки: {actual_cash} грн</h3>", unsafe_allow_html=True)
            
        else:
            st.warning("За цей день звітів не знайдено в хмарі (таблиця shifts порожня).")
            
        st.divider()
        st.subheader("🖼️ Галерея чеків за обрану дату")
        
        list_files_url = f"{SUPABASE_URL}/storage/v1/object/list/receipts"
        payload = {
            "prefix": selected_date,
            "limit": 100,
            "offset": 0
        }
        
        try:
            storage_res = requests.post(list_files_url, headers=headers, json=payload)
            if storage_res.status_code == 200:
                files_list = storage_res.json()
                valid_files = [f for f in files_list if f.get('name') and f.get('name') != '.emptyFolderPlaceholder']
                
                if valid_files:
                    img_cols = st.columns(3)
                    for idx, file_obj in enumerate(valid_files):
                        file_name = file_obj['name']
                        img_url = f"{SUPABASE_URL}/storage/v1/object/public/receipts/{selected_date}/{file_name}"
                        with img_cols[idx % 3]:
                            st.image(img_url, use_container_width=True)
                else:
                    st.info("📂 В цей день чеки не завантажувались (або папка пуста).")
            else:
                st.error(f"Помилка доступу до Storage: {storage_res.text}")
        except Exception as e:
            st.error(f"Системна помилка: {e}")

        # --- ПЛАВАЮЧЕ МЕНЮ (ДЛЯ АРХІВУ) ---
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
            with st.popover("☰"):
                nav = st.radio("Розділ:", ["Касса", "Архів"], index=1, label_visibility="collapsed")
                if nav != "Архів":
                    st.session_state["active_tab"] = nav
                    st.rerun()
        with fc2:
            with st.popover("📅"):
                d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
                if d != st.session_state["form_date"]:
                    st.session_state["form_date"] = d
                    prefetch_week_window(d)
                    st.rerun()
        with fc3:
            pass
