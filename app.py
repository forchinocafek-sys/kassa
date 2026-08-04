import streamlit as st
from datetime import datetime, timedelta
import requests
import pandas as pd
import time
import io
import uuid
import base64
import json
import calendar
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

# --- КАТЕГОРІЇ НАДХОДЖЕНЬ ---
INCOME_CATEGORIES = [
    "Касса",
    "Дотация",
    "Р/С",
    "Разное"
]

# --- ІЄРАРХІЧНІ КАТЕГОРІЇ ВИТРАТ (Група ➔ Підкатегорія) ---
EXPENSE_TREE = {
    "Выдача денег/взаимозачёты": ["Материальная помощь собственникам", "Пополнение р/с"],
    "FOOD COST / себестоимость продуктов": ["продукты", "проработки кухня/бар"],
    "WASTE technology / списание на технологию": ["вода питьевая"],
    "PAPER COST / упаковка": ["Посуда с собой"],
    "LABOR / расходы по зарплате": ["Зарплата", "зп по факту"],
    "UTILITIES / коммунальные услуги": ["вода/канализация", "директор жек", "электроенергия"],
    "COMMUNICATION SERVICES / услуги связи и ТВ": ["мобильная связь"],
    "OPERATING SUPPLIES / хоз. материалы": ["Хозтовары + хоз.инвентарь", "канцтовары"],
    "WARE, STOCK & LINEN / посуда, инвентарь, униформа, текстиль": ["посуда для зала", "форма официанты", "текстиль для зала", "барный/кухонный инвентарь"],
    "MAINTENANCE & REPAIR / техобслуживание и ремонт": ["вентиляционных систем", "осмос", "жироулавливатели", "кухонного оборудования", "ремонт мебели", "фисной техники", "прочий ремонт", "ТМЦ для ремонта (расходники)"],
    "OUTSIDE SERVICES / услуги внешних организаций": ["услуги дизайнера/художника", "реклама вакансий", "озеленение (ТМЦ)", "прочие услуги внешних организаций"],
    "PROMOTION / продвижение": ["меню choice/smap/knaipa", "типография / брендированная продукция"],
    "TRANSPORT / транспорт и топливо": ["заправка газ. балона", "новая почта", "такси", "транспорт"],
    "MISCELLANEOUS / разное": ["аптечка", "прочее", "декорации (ТМЦ)"],
    "Аренда": ["аренда помещения", "аренда подвала"],
    "MARKETING / маркетинговые расходы": ["маркетинговые активности"]
}

EXPENSE_CHOICES = []
for group, subs in EXPENSE_TREE.items():
    for sub in subs:
        EXPENSE_CHOICES.append(f"{group} ➔ {sub}")

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

def sanitize_df(df):
    records = df.to_dict('records')
    clean_records = []
    for row in records:
        clean_row = {}
        for k, v in row.items():
            if pd.isna(v): clean_row[k] = None
            elif isinstance(v, (int, float)): clean_row[k] = v
            else: clean_row[k] = str(v).strip() if v else ""
        clean_records.append(clean_row)
    return clean_records

def prefetch_week_window(center_date_obj):
    if "drafts_cache" not in st.session_state: st.session_state["drafts_cache"] = {}
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
    if not receipts_list: return True
    errors = []
    for r in receipts_list:
        safe_name = r['name'].replace(" ", "_").replace("/", "-")
        file_path = f"{date_str}/{r['id']}_{safe_name}"
        url = f"{SUPABASE_URL}/storage/v1/object/receipts/{file_path}"
        try:
            res = requests.post(url, headers=upload_headers, data=r['bytes'])
            if res.status_code not in [200, 201]: errors.append(f"{r['name']}: {res.text}")
        except Exception as e:
            errors.append(f"{r['name']}: {e}")
    if errors:
        st.error("❌ Деякі чеки не завантажилися в хмару:")
        for err in errors: st.write(err)
        return False
    return True

def prepare_df(data_list, columns):
    if not data_list: data_list = [{col: (None if col == "Сума" else "") for col in columns}]
    df = pd.DataFrame(data_list)
    for col in columns:
        if col not in df.columns: df[col] = None if col == "Сума" else ""
    if "Сума" in df.columns: df["Сума"] = pd.to_numeric(df["Сума"], errors='coerce').astype('Int64')
    for col in columns:
        if col != "Сума": df[col] = df[col].fillna("")
    return df[columns]

def load_draft_or_init(date_str):
    coins_key = f"coins_live_{date_str}"
    
    if "drafts_cache" in st.session_state and date_str in st.session_state["drafts_cache"]:
        payload = st.session_state["drafts_cache"][date_str]
        
        inc_loaded = payload.get('inc', [])
        st.session_state["inc_data"] = inc_loaded if inc_loaded else [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
        
        exp_loaded = payload.get('exp', [])
        clean_exp = []
        for e in exp_loaded:
            if "Категорія" in e: cat_val = e["Категорія"]
            elif "Група" in e: cat_val = f"{e['Група']} ➔ {e['Підкатегорія']}"
            else: cat_val = EXPENSE_CHOICES[0]
            clean_exp.append({"Категорія": cat_val, "Сума": e.get("Сума"), "Примітка": e.get("Примітка", "")})
            
        st.session_state["exp_data"] = clean_exp if clean_exp else [{"Категорія": EXPENSE_CHOICES[0], "Сума": None, "Примітка": ""}]
        
        st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": None, "Примітка": ""}])
        cash_data = payload.get('cash', {})
        st.session_state[coins_key] = str(cash_data.get('coins', 0)) if cash_data.get('coins', 0) else ""
        for k in [20, 50, 100, 200, 500, 1000]:
            st.session_state[f"qty_{k}_{date_str}"] = str(cash_data.get(str(k), 0)) if cash_data.get(str(k), 0) else ""
        return
        
    try:
        url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}"
        draft_res = requests.get(url_draft, headers=headers).json()
        if isinstance(draft_res, list) and len(draft_res) > 0:
            payload = draft_res[0].get('payload', {})
            st.session_state["drafts_cache"][date_str] = payload
            
            inc_loaded = payload.get('inc', [])
            st.session_state["inc_data"] = inc_loaded if inc_loaded else [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
            
            exp_loaded = payload.get('exp', [])
            clean_exp = []
            for e in exp_loaded:
                if "Категорія" in e: cat_val = e["Категорія"]
                elif "Група" in e: cat_val = f"{e['Група']} ➔ {e['Підкатегорія']}"
                else: cat_val = EXPENSE_CHOICES[0]
                clean_exp.append({"Категорія": cat_val, "Сума": e.get("Сума"), "Примітка": e.get("Примітка", "")})
                
            st.session_state["exp_data"] = clean_exp if clean_exp else [{"Категорія": EXPENSE_CHOICES[0], "Сума": None, "Примітка": ""}]
            st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": None, "Примітка": ""}])
            
            cash_data = payload.get('cash', {})
            st.session_state[coins_key] = str(cash_data.get('coins', 0)) if cash_data.get('coins', 0) else ""
            for k in [20, 50, 100, 200, 500, 1000]:
                st.session_state[f"qty_{k}_{date_str}"] = str(cash_data.get(str(k), 0)) if cash_data.get(str(k), 0) else ""
            return
    except Exception:
        pass
    
    st.session_state["inc_data"] = [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
    st.session_state["exp_data"] = [{"Категорія": EXPENSE_CHOICES[0], "Сума": None, "Примітка": ""}]
    prev_adv = get_previous_advances(date_str)
    st.session_state["adv_data"] = prev_adv if prev_adv else [{"Співробітник": "", "Сума": None, "Примітка": ""}]
    prev_coins = get_previous_coins(date_str)
    st.session_state[coins_key] = str(prev_coins) if prev_coins else ""
    for k in [20, 50, 100, 200, 500, 1000]: st.session_state[f"qty_{k}_{date_str}"] = ""

# --- НАЛАШТУВАННЯ СТОРІНКИ ---
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
components.html(f"""<script>const doc = window.parent.document; let m = doc.createElement('link'); m.rel = 'manifest'; m.href = 'data:application/manifest+json;base64,{manifest_b64}'; doc.head.appendChild(m);</script>""", height=0, width=0)

# --- НАЛАШТУВАННЯ СТИЛІВ CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&display=swap');
    header[data-testid="stHeader"], #MainMenu, footer { display: none !important; }
    h1 { font-family: 'Permanent Marker', cursive !important; font-size: 3em !important; margin-top: 0 !important; padding-top: 0 !important; }
    .stApp { background-color: #FAF0E6 !important; }
    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp label, .stApp li { color: #111827 !important; }
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 1px solid #d1d5db !important; }
    input, .stSelectbox span { color: #111827 !important; }
    .fact-block [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; }
    .fact-block [data-testid="column"] { width: auto !important; flex: 1 1 0% !important; min-width: 0 !important; }
    
    /* GHOST MENU */
    #is-floating { display: none; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) { position: fixed !important; top: 30px !important; right: 15px !important; z-index: 99999 !important; width: 50px !important; display: flex !important; flex-direction: column !important; gap: 12px !important; background: transparent !important; padding: 0 !important; opacity: 0.35 !important; transition: opacity 0.3s ease !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating):hover { opacity: 1 !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) > div[data-testid="column"] { width: 50px !important; min-width: 50px !important; height: 50px !important; flex: 0 0 50px !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button { width: 50px !important; height: 50px !important; border-radius: 12px !important; background: linear-gradient(135deg, #f3f4f6, #e5e7eb) !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; }
</style>
""", unsafe_allow_html=True)

st.title("Cafe Forchino🍋")

with st.popover("🚀 Версія: 2.7.1 (Expense Only Details)"):
    st.markdown("""
    **Останні оновлення:**
    * **v2.7.1:** Прибрано відображення доходів у нижній таблиці розшифровки. Тепер мітка 📌 та деталізація формується виключно для статей витрат, щоб уникнути зайвого візуального шуму.
    """)

# --- АВТОРИЗАЦІЯ ---
if st.query_params.get("auth") == "1": st.session_state["authenticated"] = True
if not st.session_state.get("authenticated", False):
    st.info("🔒 Введіть пароль для доступу до системи.")
    master_pwd = st.text_input("🔑 Пароль:", type="password", key="master_pwd_input")
    if st.button("Увійти", key="btn_login_master"):
        if master_pwd == "2000":
            st.session_state["authenticated"] = True
            st.query_params["auth"] = "1"
            st.rerun()
        elif master_pwd != "":
            st.error("❌ Невірний пароль!")
    st.stop()

if "form_date" not in st.session_state:
    st.session_state["form_date"] = datetime.today()
    prefetch_week_window(st.session_state["form_date"])

if "active_tab" not in st.session_state: st.session_state["active_tab"] = "Касса"
selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
coins_key = f"coins_live_{selected_date}"

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date


# ==========================================
# РОЗДІЛ 1: КАСА
# ==========================================
if st.session_state["active_tab"] == "Касса":
    
    start_balance = get_int(get_start_balance(selected_date))
    st.text_input("Залишок на початок дня (автоматично):", value=str(start_balance), disabled=True)

    st.divider()
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("📈Надходження:")
        inc_df = prepare_df(st.session_state["inc_data"], ["Категорія", "Сума", "Примітка"])
        edited_inc_df = st.data_editor(
            inc_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn("Стаття надходження", options=INCOME_CATEGORIES, required=True),
                "Сума": st.column_config.NumberColumn("Сума", min_value=0, step=1),
                "Примітка": st.column_config.TextColumn("Деталі")
            },
            num_rows="dynamic", use_container_width=True, key=f"inc_editor_{selected_date}"
        )
        subtotal_inc = sum(get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {subtotal_inc} грн</p>", unsafe_allow_html=True)
        
    with col_t2:
        st.subheader("📉Витрати:")
        exp_df = prepare_df(st.session_state["exp_data"], ["Категорія", "Сума", "Примітка"])
        edited_exp_df = st.data_editor(
            exp_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn("Стаття витрат", options=EXPENSE_CHOICES, required=True),
                "Сума": st.column_config.NumberColumn("Сума", min_value=0, step=1),
                "Примітка": st.column_config.TextColumn("Деталі")
            },
            num_rows="dynamic", use_container_width=True, key=f"exp_editor_{selected_date}"
        )
        subtotal_exp = sum(get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; color: #c62828;'>Загалом: {subtotal_exp} грн</p>", unsafe_allow_html=True)

    st.divider()
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.subheader("💸Аванси:")
        adv_df = prepare_df(st.session_state["adv_data"], ["Співробітник", "Сума", "Примітка"])
        edited_adv_df = st.data_editor(adv_df, num_rows="dynamic", use_container_width=True, key=f"adv_editor_{selected_date}")
        subtotal_adv = sum(get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {subtotal_adv} грн</p>", unsafe_allow_html=True)

    with col_b2:
        st.subheader("💰Факт")
        m_coins = get_int(st.text_input("Монети (загальна сума):", placeholder="0", key=f"coins_live_{selected_date}"))
        st.markdown('<div class="fact-block">', unsafe_allow_html=True)
        def cash_row(label, mult):
            c1, c2 = st.columns([1, 4])
            with c1: st.markdown(f"<div style='margin-top:8px;font-weight:bold;'>{label}</div>", unsafe_allow_html=True)
            with c2: qty = get_int(st.text_input(f"q{label}", label_visibility="collapsed", placeholder="0", key=f"qty_{label}_{selected_date}"))
            return qty, qty * mult

        q_20, v_20 = cash_row("20", 20)
        q_50, v_50 = cash_row("50", 50)
        q_100, v_100 = cash_row("100", 100)
        q_200, v_200 = cash_row("200", 200)
        q_500, v_500 = cash_row("500", 500)
        q_1000, v_1000 = cash_row("1000", 1000)
        st.markdown('</div>', unsafe_allow_html=True)
        
        cash_pure = m_coins + v_20 + v_50 + v_100 + v_200 + v_500 + v_1000
        st.markdown(f"## 💵Разом в касі: {cash_pure} грн")

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
        with st.spinner("Стерилізація та відправка звіту..."):
            payload = {
                "inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df),
                "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}
            }
            try: json.dumps(payload)
            except Exception as e: st.error(f"❌ Помилка символів: {e}"); st.stop()

            check_draft = requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers).json()
            if check_draft: requests.patch(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers, json={"payload": payload})
            else: requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})

            st.session_state["drafts_cache"][selected_date] = payload
            st.cache_data.clear() 
            
            requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
            requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
            requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
            
            res_shift = requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json={"date": selected_date, "start_balance": str(start_balance), "calculated_end": str(calculated_end), "actual_end": str(total_actual)})
            
            if res_shift.status_code in [200, 201]:
                inc_rows = []
                for _, r in edited_inc_df.iterrows():
                    amt, cat, note = get_int(r.get("Сума", 0)), str(r.get("Категорія", "")).strip(), str(r.get("Примітка", "")).strip()
                    if amt or cat: inc_rows.append({"date": selected_date, "type": "income", "description": f"{cat} | {note}" if note else cat, "amount": str(amt)})
                
                exp_rows = []
                for _, r in edited_exp_df.iterrows():
                    amt, cat, note = get_int(r.get("Сума", 0)), str(r.get("Категорія", "")).strip(), str(r.get("Примітка", "")).strip()
                    if amt or cat: exp_rows.append({"date": selected_date, "type": "expense", "description": f"{cat} | {note}" if note else cat, "amount": str(amt)})
                
                adv_rows = []
                for _, r in edited_adv_df.iterrows():
                    amt, emp, raw_note = get_int(r.get("Сума", 0)), str(r.get("Співробітник", "")).strip(), r.get("Примітка", "")
                    safe_note = str(raw_note).strip() if pd.notna(raw_note) and str(raw_note).lower() != 'nan' else ""
                    if amt or emp: adv_rows.append({"date": selected_date, "employee": emp, "amount": str(amt), "note": safe_note})
                        
                if inc_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=inc_rows)
                if exp_rows: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=exp_rows)
                if adv_rows: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=adv_rows)
                st.success("🎉 Звіт успішно збережено в хмарі!")
            else:
                st.error(f"❌ Помилка: {res_shift.text}")

    # --- ПЛАВАЮЧЕ МЕНЮ ---
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🗃️", key="fab_nav_arch"):
            st.session_state["drafts_cache"][selected_date] = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            st.session_state["active_tab"] = "Архів"; st.rerun()
    with fc2:
        if st.button("📊", key="fab_nav_pnl"):
            st.session_state["drafts_cache"][selected_date] = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            st.session_state["active_tab"] = "Сличительная"; st.rerun()
    with fc3:
        with st.popover("📅"):
            d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
            if d != st.session_state["form_date"]: st.session_state["form_date"] = d; prefetch_week_window(d); st.rerun()
    with fc4:
        if st.button("💾", key="fab_save"):
            payload = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            try:
                json.dumps(payload)
                if requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers).json(): requests.patch(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers, json={"payload": payload})
                else: requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})
                st.session_state["drafts_cache"][selected_date] = payload
                st.toast("✅ Чернетку збережено!", icon="💾")
            except Exception: st.error("Помилка даних.")
    with fc5:
        if st.button("🚫", key="fab_lock"): st.session_state["authenticated"] = False; st.rerun()

# ==========================================
# РОЗДІЛ 2: АРХІВ
# ==========================================
elif st.session_state["active_tab"] == "Архів":
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
            if inc_res:
                for item in inc_res:
                    amt = get_int(item.get('amount'))
                    total_inc += amt
                    parts = item.get('description', 'Без опису').split(' | ', 1)
                    st.markdown(f"• {parts[0]}: {amt} грн{' <i>— '+parts[1]+'</i>' if len(parts)>1 else ''}", unsafe_allow_html=True)
            st.markdown(f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {total_inc} грн</p>", unsafe_allow_html=True)
            
        with ac2:
            st.subheader("🔴 Витрати")
            exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.expense", headers=headers).json()
            total_exp = 0
            if exp_res:
                for item in exp_res:
                    amt = get_int(item.get('amount'))
                    total_exp += amt
                    parts = item.get('description', 'Без опису').split(' | ', 1)
                    st.markdown(f"• {parts[0]}: {amt} грн{' <i>— '+parts[1]+'</i>' if len(parts)>1 else ''}", unsafe_allow_html=True)
            st.markdown(f"<p style='font-weight: bold; color: #c62828;'>Загалом: {total_exp} грн</p>", unsafe_allow_html=True)
                
        st.divider()
        st.markdown(f"<h3 style='margin-bottom: 0;'>🌇 Залишок на кінець: <span style='color: #0066cc;'>{calc_end} грн</span></h3>", unsafe_allow_html=True)
        st.divider()
        
        st.subheader("🟠 Аванси")
        adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers).json()
        total_adv = 0
        if adv_res:
            for item in adv_res:
                amt = get_int(item.get('amount'))
                total_adv += amt
                safe_note = str(item.get('note', '')).strip()
                st.markdown(f"• {item.get('employee', 'Без імені')}: {amt} грн{' <i>— '+safe_note+'</i>' if safe_note else ''}", unsafe_allow_html=True)
        st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {total_adv} грн</p>", unsafe_allow_html=True)
        
    else: st.warning("За цей день звітів не знайдено.")
        
    st.divider()
    c_header, c_btn = st.columns([3, 1])
    with c_header: st.subheader("🖼️ Галерея чеків")
    with c_btn:
        with st.popover("📷 Додати чеки"):
            ufs = st.file_uploader("Виберіть файли", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"uploader_{selected_date}")
            if st.button("➕ Відправити на сервер", use_container_width=True) and ufs:
                with st.spinner("Завантаження..."):
                    receipts_to_upload = []
                    for uf in ufs:
                        img = Image.open(uf)
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        img.thumbnail((1024, 1024))
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=70)
                        receipts_to_upload.append({"id": str(uuid.uuid4()), "name": uf.name, "bytes": buf.getvalue()})
                    if upload_receipts_to_supabase(selected_date, receipts_to_upload): st.success("Успішно!"); time.sleep(1); st.rerun() 
    
    try:
        storage_res = requests.post(f"{SUPABASE_URL}/storage/v1/object/list/receipts", headers=headers, json={"prefix": selected_date, "limit": 100, "offset": 0})
        if storage_res.status_code == 200:
            files_list = [f for f in storage_res.json() if f.get('name') and f.get('name') != '.emptyFolderPlaceholder']
            if files_list:
                img_cols = st.columns(3)
                for idx, file_obj in enumerate(files_list):
                    file_name = file_obj['name']
                    with img_cols[idx % 3]:
                        st.image(f"{SUPABASE_URL}/storage/v1/object/public/receipts/{selected_date}/{file_name}", use_container_width=True)
                        with st.popover("🗑️ Видалити", use_container_width=True):
                            st.warning(f"Видалити {file_name}?")
                            if st.button("Так", key=f"del_{file_name}", type="primary"):
                                if requests.delete(f"{SUPABASE_URL}/storage/v1/object/receipts/{selected_date}/{file_name}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}).status_code in [200, 204]: st.rerun()
            else: st.info("📂 Папка пуста.")
    except Exception: pass

    # --- ПЛАВАЮЧЕ МЕНЮ ---
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🧮", key="fab_nav_kas"): st.session_state["active_tab"] = "Касса"; st.rerun()
    with fc2:
        if st.button("📊", key="fab_nav_pnl2"): st.session_state["active_tab"] = "Сличительная"; st.rerun()
    with fc3:
        with st.popover("📅"):
            d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
            if d != st.session_state["form_date"]: st.session_state["form_date"] = d; prefetch_week_window(d); st.rerun()
    with fc5:
        if st.button("🚫", key="fab_lock2"): st.session_state["authenticated"] = False; st.rerun()

# ==========================================
# РОЗДІЛ 3: СЛИЧИТЕЛЬНАЯ (PnL)
# ==========================================
elif st.session_state["active_tab"] == "Сличительная":
    st.subheader("📊 Сличительная ведомость")
    
    months = {"Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4, "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8, "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12}
    c_m, c_y = st.columns(2)
    sel_m = c_m.selectbox("Місяць", list(months.keys()), index=st.session_state["form_date"].month-1)
    sel_y = c_y.selectbox("Рік", [2025, 2026, 2027], index=1)
    
    if st.button("🚀 Згенерувати матрицю PnL", type="primary", use_container_width=True):
        with st.spinner("Збір даних з бази..."):
            m_num = months[sel_m]
            start_d = f"{sel_y}-{m_num:02d}-01"
            end_d = f"{sel_y+1}-01-01" if m_num == 12 else f"{sel_y}-{m_num+1:02d}-01"
            num_days = calendar.monthrange(sel_y, m_num)[1]
            
            expense_groups_list = list(EXPENSE_TREE.keys())
            
            order_full = [
                "Касса на начало дня", 
                "🟢 НАДХОДЖЕННЯ"
            ] + INCOME_CATEGORIES + [
                "🔴 ВИТРАТИ"
            ] + expense_groups_list + [
                "Інші (старі ручні записи)", 
                "🔴 ВСЬОГО ВИТРАТ", 
                "Касса на конец дня"
            ]
            
            report_data = {cat: {str(d): {"sum": 0, "notes": [], "set": False} for d in range(1, num_days + 1)} for cat in order_full}

            # 1. Залишки
            shifts_data = requests.get(f"{SUPABASE_URL}/rest/v1/shifts?date=gte.{start_d}&date=lt.{end_d}", headers=headers).json()
            if isinstance(shifts_data, list):
                for s in shifts_data:
                    day = str(int(s['date'].split('-')[2]))
                    report_data["Касса на начало дня"][day]["sum"] = get_int(s.get('start_balance', 0))
                    report_data["Касса на начало дня"][day]["set"] = True
                    report_data["Касса на конец дня"][day]["sum"] = get_int(s.get('actual_end', 0))
                    report_data["Касса на конец дня"][day]["set"] = True

            # 2. Транзакції
            trans_data = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=gte.{start_d}&date=lt.{end_d}", headers=headers).json()
            if isinstance(trans_data, list):
                for t in trans_data:
                    day = str(int(t['date'].split('-')[2]))
                    amt = get_int(t.get('amount', 0))
                    desc_raw = t.get('description', '').strip()
                    parts = desc_raw.split(' | ', 1)
                    left_part = parts[0].strip()
                    note = parts[1].strip() if len(parts) > 1 else ""

                    if t.get('type') == 'income':
                        target_inc = left_part if left_part in INCOME_CATEGORIES else "Разное"
                        report_data[target_inc][day]["sum"] += amt
                        
                        note_text = note if note else (left_part if target_inc == "Разное" else "")
                        if note_text:
                            report_data[target_inc][day]["notes"].append(f"{amt} ({note_text})")
                        else:
                            report_data[target_inc][day]["notes"].append(f"{amt}")
                    else:
                        if ' ➔ ' in left_part: group_name = left_part.split(' ➔ ')[0].strip()
                        elif ' >> ' in left_part: group_name = left_part.split(' >> ')[0].strip()
                        else: group_name = left_part
                        
                        target_cat = group_name if group_name in report_data else "Інші (старі ручні записи)"
                        report_data[target_cat][day]["sum"] += amt
                        
                        sub_cat = ""
                        if ' ➔ ' in left_part: sub_cat = left_part.split(' ➔ ')[1].strip()
                        elif ' >> ' in left_part: sub_cat = left_part.split(' >> ')[1].strip()
                        
                        full_note_parts = [p for p in [sub_cat, note] if p]
                        if full_note_parts: 
                            note_str = " - ".join(full_note_parts)
                            report_data[target_cat][day]["notes"].append(f"{amt} ({note_str})")
                        elif target_cat == "Інші (старі ручні записи)" and group_name: 
                            report_data[target_cat][day]["notes"].append(f"{amt} ({group_name})")
                        else:
                            report_data[target_cat][day]["notes"].append(f"{amt}")

            # Підрахунок ВСЬОГО ВИТРАТ
            for d in range(1, num_days + 1):
                day_str = str(d)
                day_total = sum(report_data[cat][day_str]["sum"] for cat in expense_groups_list + ["Інші (старі ручні записи)"])
                report_data["🔴 ВСЬОГО ВИТРАТ"][day_str]["sum"] = day_total
                if day_total > 0: report_data["🔴 ВСЬОГО ВИТРАТ"][day_str]["set"] = True

            # ФОРМУВАННЯ МАТРИЦІ ТА ПІДРАХУНОК "ІТОГО"
            df_rows = []
            month_notes = [] 
            
            for r in order_full:
                row_dict = {"Стаття": r}
                row_total = 0 
                
                for d in range(1, num_days + 1):
                    cell = report_data[r][str(d)]
                    
                    if r in ["🟢 НАДХОДЖЕННЯ", "🔴 ВИТРАТИ"]:
                        row_dict[str(d)] = ""
                    elif r in ["Касса на начало дня", "Касса на конец дня", "🔴 ВСЬОГО ВИТРАТ"]:
                        row_dict[str(d)] = str(cell["sum"]) if cell["set"] else ""
                        row_total += cell["sum"]
                    else:
                        if cell["sum"] == 0 and not cell["notes"]:
                            row_dict[str(d)] = ""
                        else:
                            row_total += cell["sum"]
                            valid_notes = [n for n in cell["notes"] if n]
                            
                            # ДОДАНА УМОВА ФІЛЬТРАЦІЇ: Ігнорувати доходи для мітки 📌 та нижньої таблиці
                            if valid_notes and r not in INCOME_CATEGORIES:
                                row_dict[str(d)] = f"{cell['sum']} 📌"
                                month_notes.append({
                                    "🗓 День": f"{d} {sel_m.lower()}",
                                    "🗂 Стаття": r,
                                    "💰 Загальна сума": f"{cell['sum']} грн",
                                    "📝 Деталізація": ", ".join(valid_notes)
                                })
                            else:
                                row_dict[str(d)] = str(cell["sum"])
                
                # ДОДАЄМО СТОВПЕЦЬ "Всього"
                if r in ["🟢 НАДХОДЖЕННЯ", "🔴 ВИТРАТИ", "Касса на начало дня", "Касса на конец дня"]:
                    row_dict["Всього"] = ""
                else:
                    row_dict["Всього"] = str(row_total) if row_total > 0 else ""
                    
                df_rows.append(row_dict)
                
            df_report = pd.DataFrame(df_rows)
            
            # --- ФУНКЦІЯ СТИЛІЗАЦІЇ (КОЛЬОРИ) ---
            def style_pnl(row):
                styles = [''] * len(row)
                styles[-1] = 'background-color: #f3f4f6; font-weight: bold; border-left: 2px solid #d1d5db;'
                
                if row['Стаття'] == '🟢 НАДХОДЖЕННЯ': return ['background-color: #d1e7dd; font-weight: bold; color: #0f5132'] * len(row)
                elif row['Стаття'] == '🔴 ВИТРАТИ': return ['background-color: #f8d7da; font-weight: bold; color: #842029'] * len(row)
                elif row['Стаття'] == '🔴 ВСЬОГО ВИТРАТ': return ['background-color: #fff3cd; font-weight: bold; color: #664d03'] * len(row)
                elif row['Стаття'] in ['Касса на начало дня', 'Касса на конец дня']: return ['background-color: #e2e3e5; font-weight: bold; color: #383d41'] * len(row)
                return styles

            styled_df = df_report.style.apply(style_pnl, axis=1)
            
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
            
            # ВИВЕДЕННЯ ДЕТАЛЕЙ ПІД ТАБЛИЦЕЮ
            if month_notes:
                st.markdown("##### 📌 Розшифровка деталей (записи з позначкою 📌)")
                notes_df = pd.DataFrame(month_notes)
                st.dataframe(notes_df, use_container_width=True, hide_index=True)
                
            st.success("✅ Матрицю PnL успішно зведено!")

    # --- ПЛАВАЮЧЕ МЕНЮ ---
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🧮", key="fab_nav_kas_pnl"): st.session_state["active_tab"] = "Касса"; st.rerun()
    with fc2:
        if st.button("🗃️", key="fab_nav_arch_pnl"): st.session_state["active_tab"] = "Архів"; st.rerun()
    with fc3:
        with st.popover("📅"):
            d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
            if d != st.session_state["form_date"]: st.session_state["form_date"] = d; prefetch_week_window(d); st.rerun()
    with fc5:
        if st.button("🚫", key="fab_lock_pnl"): st.session_state["authenticated"] = False; st.rerun()

st.write("---")
st.markdown("<p style='text-align: center; color: #9ca3af; font-size: 14px; font-style: italic; margin-bottom: 30px;'>Розроблено Богданом для cafe forchino з любов'ю 🧡</p>", unsafe_allow_html=True)
