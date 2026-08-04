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

# --- ІЄРАРХІЧНІ КАТЕГОРІЇ ВИТРАТ ---
EXPENSE_TREE = {
    "Выдача денег/взаимозачёты": [
        "Материальная помощь собственникам", 
        "Пополнение р/с"
    ],
    "FOOD COST / себестоимость продуктов": [
        "продукты", 
        "проработки кухня/бар"
    ],
    "WASTE technology / списание на технологию": [
        "вода питьевая"
    ],
    "PAPER COST / упаковка": [
        "Посуда с собой"
    ],
    "LABOR / расходы по зарплате": [
        "Зарплата", 
        "зп по факту"
    ],
    "UTILITIES / коммунальные услуги": [
        "вода/канализация", 
        "директор жек", 
        "электроенергия"
    ],
    "COMMUNICATION SERVICES / услуги связи и ТВ": [
        "мобильная связь"
    ],
    "OPERATING SUPPLIES / хоз. материалы": [
        "Хозтовары + хоз.инвентарь", 
        "канцтовары"
    ],
    "WARE, STOCK & LINEN / посуда, инвентарь, униформа, текстиль": [
        "посуда для зала", 
        "форма официанты", 
        "текстиль для зала", 
        "барный/кухонный инвентарь"
    ],
    "MAINTENANCE & REPAIR / техобслуживание и ремонт": [
        "вентиляционных систем", 
        "осмос", 
        "жироулавливатели", 
        "кухонного оборудования", 
        "ремонт мебели", 
        "фисной техники", 
        "прочий ремонт", 
        "ТМЦ для ремонта (расходники)"
    ],
    "OUTSIDE SERVICES / услуги внешних организаций": [
        "услуги дизайнера/художника", 
        "реклама вакансий", 
        "озеленение (ТМЦ)", 
        "прочие услуги внешних организаций"
    ],
    "PROMOTION / продвижение": [
        "меню choice/smap/knaipa", 
        "типография / брендированная продукция"
    ],
    "TRANSPORT / транспорт и топливо": [
        "заправка газ. балона", 
        "новая почта", 
        "такси", 
        "транспорт"
    ],
    "MISCELLANEOUS / разное": [
        "аптечка", 
        "прочее", 
        "декорации (ТМЦ)"
    ],
    "Аренда": [
        "аренда помещения", 
        "аренда подвала"
    ],
    "MARKETING / маркетинговые расходы": [
        "маркетинговые активности"
    ]
}

ALL_SUB_CATEGORIES = []
for group, subs in EXPENSE_TREE.items():
    for sub in subs:
        ALL_SUB_CATEGORIES.append(f"{group} >> {sub}")

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
            if pd.isna(v):
                clean_row[k] = None
            elif isinstance(v, (int, float)):
                clean_row[k] = v
            else:
                clean_row[k] = str(v).strip() if v else ""
        clean_records.append(clean_row)
    return clean_records

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
        
    if "drafts_cache" in st.session_state and date_str in st.session_state["drafts_cache"]:
        payload = st.session_state["drafts_cache"][date_str]
        
        # Завантажуємо надходження (Категорія + Сума + Примітка)
        inc_loaded = payload.get('inc', [])
        clean_inc = []
        for i in inc_loaded:
            clean_inc.append({
                "Категорія": i.get("Категорія", i.get("Опис", INCOME_CATEGORIES[0])),
                "Сума": i.get("Сума"),
                "Примітка": i.get("Примітка", "")
            })
        st.session_state["inc_data"] = clean_inc if clean_inc else [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
        
        exp_loaded = payload.get('exp', [])
        clean_exp = []
        for e in exp_loaded:
            clean_exp.append({
                "Група": e.get("Група", list(EXPENSE_TREE.keys())[0]),
                "Підкатегорія": e.get("Підкатегорія", EXPENSE_TREE[list(EXPENSE_TREE.keys())[0]][0]),
                "Сума": e.get("Сума"),
                "Примітка": e.get("Примітка", "")
            })
        st.session_state["exp_data"] = clean_exp if clean_exp else [{"Група": list(EXPENSE_TREE.keys())[0], "Підкатегорія": EXPENSE_TREE[list(EXPENSE_TREE.keys())[0]][0], "Сума": None, "Примітка": ""}]
        
        st.session_state["adv_data"] = payload.get('adv', [{"Співробітник": "", "Сума": None, "Примітка": ""}])
        cash_data = payload.get('cash', {})
        c_coins = cash_data.get('coins', 0)
        st.session_state[coins_key] = str(c_coins) if c_coins else ""
        for k in [20, 50, 100, 200, 500, 1000]:
            c_val = cash_data.get(str(k), 0)
            st.session_state[f"qty_{k}_{date_str}"] = str(c_val) if c_val else ""
        return
        
    try:
        url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}"
        draft_res = requests.get(url_draft, headers=headers).json()
        if isinstance(draft_res, list) and len(draft_res) > 0:
            payload = draft_res[0].get('payload', {})
            if "drafts_cache" not in st.session_state:
                st.session_state["drafts_cache"] = {}
            st.session_state["drafts_cache"][date_str] = payload
            
            inc_loaded = payload.get('inc', [])
            clean_inc = []
            for i in inc_loaded:
                clean_inc.append({
                    "Категорія": i.get("Категорія", i.get("Опис", INCOME_CATEGORIES[0])),
                    "Сума": i.get("Сума"),
                    "Примітка": i.get("Примітка", "")
                })
            st.session_state["inc_data"] = clean_inc if clean_inc else [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
            
            exp_loaded = payload.get('exp', [])
            clean_exp = []
            for e in exp_loaded:
                clean_exp.append({
                    "Група": e.get("Група", list(EXPENSE_TREE.keys())[0]),
                    "Підкатегорія": e.get("Підкатегорія", EXPENSE_TREE[list(EXPENSE_TREE.keys())[0]][0]),
                    "Сума": e.get("Сума"),
                    "Примітка": e.get("Примітка", "")
                })
            st.session_state["exp_data"] = clean_exp if clean_exp else [{"Група": list(EXPENSE_TREE.keys())[0], "Підкатегорія": EXPENSE_TREE[list(EXPENSE_TREE.keys())[0]][0], "Сума": None, "Примітка": ""}]

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
    
    st.session_state["inc_data"] = [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
    st.session_state["exp_data"] = [{"Група": list(EXPENSE_TREE.keys())[0], "Підкатегорія": EXPENSE_TREE[list(EXPENSE_TREE.keys())[0]][0], "Сума": None, "Примітка": ""}]
    
    prev_adv = get_previous_advances(date_str)
    st.session_state["adv_data"] = prev_adv if prev_adv else [{"Співробітник": "", "Сума": None, "Примітка": ""}]
    
    prev_coins = get_previous_coins(date_str)
    st.session_state[coins_key] = str(prev_coins) if prev_coins else ""
    
    for k in [20, 50, 100, 200, 500, 1000]:
        st.session_state[f"qty_{k}_{date_str}"] = ""

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
</script>
""", height=0, width=0)

# --- НАЛАШТУВАННЯ СТИЛІВ CSS ---
st.markdown("""
<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&display=swap');
    header[data-testid="stHeader"] { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { display: none !important; }
    h1 { font-family: 'Permanent Marker', cursive !important; font-size: 3em !important; margin-top: 0 !important; padding-top: 0 !important; }
    .stApp { background-color: #FAF0E6 !important; }
    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp label, .stApp li { color: #111827 !important; }
    p[style*="#2e7d32"] { color: #2e7d32 !important; }
    p[style*="#c62828"] { color: #c62828 !important; }
    p[style*="#ef6c00"] { color: #ef6c00 !important; }
    span[style*="#0066cc"] { color: #0066cc !important; }
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 1px solid #d1d5db !important; }
    input, .stSelectbox span { color: #111827 !important; }
    .stTextInput div[data-baseweb="input"] { height: 35px !important; }
    .stTextInput input { padding: 5px !important; }
    .fact-block [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; }
    .fact-block [data-testid="column"] { width: auto !important; flex: 1 1 0% !important; min-width: 0 !important; }
    
    /* ПРОЗОРЕ ПЛАВАЮЧЕ МЕНЮ (GHOST MENU) */
    #is-floating { display: none; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) { 
        position: fixed !important; top: 30px !important; right: 15px !important; 
        z-index: 99999 !important; width: 50px !important; display: flex !important; 
        flex-direction: column !important; gap: 12px !important; background: transparent !important; 
        padding: 0 !important; opacity: 0.35 !important; transition: opacity 0.3s ease !important; 
    }
    div[data-testid="stHorizontalBlock"]:has(#is-floating):hover,
    div[data-testid="stHorizontalBlock"]:has(#is-floating):active,
    div[data-testid="stHorizontalBlock"]:has(#is-floating):focus-within { opacity: 1 !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) > div[data-testid="column"] { width: 50px !important; min-width: 50px !important; max-width: 50px !important; height: 50px !important; flex: 0 0 50px !important; margin: 0 !important; padding: 0 !important; display: flex !important; justify-content: center !important; align-items: center !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) > div[data-testid="column"] > div { width: 100% !important; height: 100% !important; display: flex !important; justify-content: center !important; align-items: center !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button { width: 50px !important; min-width: 50px !important; height: 50px !important; min-height: 50px !important; padding: 0 !important; margin: 0 !important; border-radius: 12px !important; background: linear-gradient(135deg, #f3f4f6, #e5e7eb) !important; color: #4b5563 !important; border: 1px solid #d1d5db !important; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15) !important; display: flex !important; align-items: center !important; justify-content: center !important; transition: transform 0.2s, box-shadow 0.2s !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button:hover { transform: translateY(-2px) !important; box-shadow: 0 6px 15px rgba(0, 0, 0, 0.2) !important; background: linear-gradient(135deg, #e5e7eb, #d1d5db) !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button p { font-size: 20px !important; margin: 0 !important; padding: 0 !important; line-height: 1 !important; }
</style>
""", unsafe_allow_html=True)

# --- ШАПКА ДОДАТКУ ---
st.title("Cafe Forchino🍋")

with st.popover("🚀 Версія: 2.4.0 (Income Categories)"):
    st.markdown("""
    **Останні оновлення:**
    * **v2.4.0:** Додано строгі категорії для надходжень (Касса, Дотация, Р/С, Разное) з вибором та примітками.
    * **v2.3.0:** Ієрархічний вибір витрат (Група -> Підкатегорія).
    """)

# ==========================================
# ГЛОБАЛЬНА АВТОРИЗАЦІЯ
# ==========================================
if st.query_params.get("auth") == "1":
    st.session_state["authenticated"] = True

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

if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "Касса"

selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
coins_key = f"coins_live_{selected_date}"

if coins_key not in st.session_state:
    st.session_state["current_loaded_date"] = None

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date


# ==========================================
# РОЗДІЛ 1: КАСА
# ==========================================
if st.session_state["active_tab"] == "Касса":
    
    db_start = get_start_balance(selected_date)
    start_balance = get_int(db_start)
    st.text_input("Залишок на початок дня (автоматично):", value=str(start_balance), disabled=True, key=f"start_balance_{selected_date}")

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
        exp_df = prepare_df(st.session_state["exp_data"], ["Група", "Підкатегорія", "Сума", "Примітка"])
        
        edited_exp_df = st.data_editor(
            exp_df,
            column_config={
                "Група": st.column_config.SelectboxColumn("Група витрат", options=list(EXPENSE_TREE.keys()), required=True),
                "Підкатегорія": st.column_config.SelectboxColumn("Підкатегорія", options=ALL_SUB_CATEGORIES, required=True),
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
                "inc": sanitize_df(edited_inc_df),
                "exp": sanitize_df(edited_exp_df),
                "adv": sanitize_df(edited_adv_df),
                "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}
            }
            
            try:
                json.dumps(payload)
            except Exception as e:
                st.error(f"❌ Зупинено! Знайдено недопустимі символи в таблиці. {e}")
                st.stop()

            check_draft = requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers).json()
            if isinstance(check_draft, list) and len(check_draft) > 0:
                requests.patch(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers, json={"payload": payload})
            else:
                requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})

            if "drafts_cache" not in st.session_state: st.session_state["drafts_cache"] = {}
            st.session_state["drafts_cache"][selected_date] = payload
            st.cache_data.clear() 
            
            requests.delete(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers)
            requests.delete(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}", headers=headers)
            requests.delete(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers)
            
            shift_payload = {"date": selected_date, "start_balance": str(start_balance), "calculated_end": str(calculated_end), "actual_end": str(total_actual)}
            res_shift = requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json=shift_payload)
            
            if res_shift.status_code in [200, 201]:
                # СКЛЕЮВАННЯ КАТЕГОРІЇ ТА ПРИМІТКИ ДЛЯ НАДХОДЖЕНЬ
                inc_rows = []
                for _, r in edited_inc_df.iterrows():
                    amt = get_int(r.get("Сума", 0))
                    cat = str(r.get("Категорія", "")).strip()
                    note = str(r.get("Примітка", "")).strip()
                    if amt != 0 or cat:
                        final_desc = f"{cat} | {note}" if note else cat
                        inc_rows.append({"date": selected_date, "type": "income", "description": final_desc, "amount": str(amt)})
                
                exp_rows = []
                for _, r in edited_exp_df.iterrows():
                    amt = get_int(r.get("Сума", 0))
                    group = str(r.get("Група", "")).strip()
                    sub = str(r.get("Підкатегорія", "")).strip()
                    note = str(r.get("Примітка", "")).strip()
                    if amt != 0 or group:
                        sub_part = f"{group} >> {sub}" if sub else group
                        final_desc = f"{sub_part} | {note}" if note else sub_part
                        exp_rows.append({"date": selected_date, "type": "expense", "description": final_desc, "amount": str(amt)})
                
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
                
                st.success("🎉 Звіт успішно та БЕЗПЕЧНО збережено в хмарі!")
            else:
                st.error(f"❌ Помилка бази даних: {res_shift.text}")

    # --- ПЛАВАЮЧЕ МЕНЮ (КАСА) ---
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🗃️", key="fab_nav_arch"):
            payload = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            st.session_state["drafts_cache"][selected_date] = payload
            st.session_state["active_tab"] = "Архів"
            st.rerun()
    with fc2:
        if st.button("📊", key="fab_nav_pnl"):
            payload = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            st.session_state["drafts_cache"][selected_date] = payload
            st.session_state["active_tab"] = "Сличительная"
            st.rerun()
    with fc3:
        with st.popover("📅"):
            d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
            if d != st.session_state["form_date"]:
                payload = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
                st.session_state["drafts_cache"][selected_date] = payload
                st.session_state["form_date"] = d
                prefetch_week_window(d)
                st.rerun()
    with fc4:
        if st.button("💾", key="fab_save"):
            payload = {"inc": sanitize_df(edited_inc_df), "exp": sanitize_df(edited_exp_df), "adv": sanitize_df(edited_adv_df), "cash": {"coins": m_coins, "20": q_20, "50": q_50, "100": q_100, "200": q_200, "500": q_500, "1000": q_1000}}
            try:
                json.dumps(payload)
                check_draft = requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers).json()
                if isinstance(check_draft, list) and len(check_draft) > 0:
                    requests.patch(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}", headers=headers, json={"payload": payload})
                else:
                    requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": selected_date, "payload": payload})
                st.session_state["drafts_cache"][selected_date] = payload
                st.toast("✅ Чернетку безпечно збережено!", icon="💾")
            except Exception as e:
                st.error("Помилка даних.")
    with fc5:
        if st.button("🚫", key="fab_lock"):
            st.session_state["authenticated"] = False
            if "auth" in st.query_params: del st.query_params["auth"]
            st.rerun()

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
            if isinstance(inc_res, list) and inc_res:
                for item in inc_res:
                    amt = get_int(item.get('amount'))
                    total_inc += amt
                    
                    desc_raw = item.get('description', 'Без опису')
                    parts = desc_raw.split(' | ', 1)
                    main_cat = parts[0]
                    note_str = f" <i>— {parts[1]}</i>" if len(parts) > 1 else ""
                    
                    st.markdown(f"• {main_cat}: {amt} грн{note_str}", unsafe_allow_html=True)
            st.markdown(f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {total_inc} грн</p>", unsafe_allow_html=True)
            
        with ac2:
            st.subheader("🔴 Витрати")
            exp_res = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.expense", headers=headers).json()
            total_exp = 0
            if isinstance(exp_res, list) and exp_res:
                for item in exp_res:
                    amt = get_int(item.get('amount'))
                    total_exp += amt
                    
                    desc_raw = item.get('description', 'Без опису')
                    parts = desc_raw.split(' | ', 1)
                    main_cat = parts[0]
                    note_str = f" <i>— {parts[1]}</i>" if len(parts) > 1 else ""
                    
                    st.markdown(f"• {main_cat}: {amt} грн{note_str}", unsafe_allow_html=True)
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
                safe_note = str(item.get('note', '')).strip()
                note_str = f" <i>— {safe_note}</i>" if safe_note else ""
                st.markdown(f"• {item.get('employee', 'Без імені')}: {amt} грн{note_str}", unsafe_allow_html=True)
        st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {total_adv} грн</p>", unsafe_allow_html=True)
        
    else:
        st.warning("За цей день звітів не знайдено в хмарі.")
        
    st.divider()
    c_header, c_btn = st.columns([3, 1])
    with c_header:
        st.subheader("🖼️ Галерея чеків")
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
                    if upload_receipts_to_supabase(selected_date, receipts_to_upload):
                        st.success("✅ Завантажено успішно!")
                        time.sleep(1)
                        st.rerun() 
    
    try:
        storage_res = requests.post(f"{SUPABASE_URL}/storage/v1/object/list/receipts", headers=headers, json={"prefix": selected_date, "limit": 100, "offset": 0})
        if storage_res.status_code == 200:
            files_list = [f for f in storage_res.json() if f.get('name') and f.get('name') != '.emptyFolderPlaceholder']
            if files_list:
                img_cols = st.columns(3)
                for idx, file_obj in enumerate(files_list):
                    file_name = file_obj['name']
                    img_url = f"{SUPABASE_URL}/storage/v1/object/public/receipts/{selected_date}/{file_name}"
                    with img_cols[idx % 3]:
                        st.image(img_url, use_container_width=True)
                        with st.popover("🗑️ Видалити", use_container_width=True):
                            st.warning(f"Видалити {file_name}?")
                            if st.button("Так", key=f"del_confirm_{file_name}", type="primary"):
                                del_res = requests.delete(f"{SUPABASE_URL}/storage/v1/object/receipts/{selected_date}/{file_name}", headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
                                if del_res.status_code in [200, 204]:
                                    st.success("Видалено!")
                                    time.sleep(0.5)
                                    st.rerun()
            else:
                st.info("📂 В цей день чеки не завантажувались (або папка пуста).")
    except Exception:
        pass

    # --- ПЛАВАЮЧЕ МЕНЮ (АРХІВ) ---
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🧮", key="fab_nav_kas"):
            st.session_state["active_tab"] = "Касса"
            st.rerun()
    with fc2:
        if st.button("📊", key="fab_nav_pnl2"):
            st.session_state["active_tab"] = "Сличительная"
            st.rerun()
    with fc3:
        with st.popover("📅"):
            d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
            if d != st.session_state["form_date"]:
                st.session_state["form_date"] = d
                prefetch_week_window(d)
                st.rerun()
    with fc5:
        if st.button("🚫", key="fab_lock2"):
            st.session_state["authenticated"] = False
            if "auth" in st.query_params: del st.query_params["auth"]
            st.rerun()

# ==========================================
# РОЗДІЛ 3: СЛИЧИТЕЛЬНАЯ (PnL)
# ==========================================
elif st.session_state["active_tab"] == "Сличительная":
    st.subheader("📊 Сличительная ведомость")
    
    months = {"Січень": 1, "Лютий": 2, "Березень": 3, "Квітень": 4, "Травень": 5, "Червень": 6, "Липень": 7, "Серпень": 8, "Вересень": 9, "Жовтень": 10, "Листопад": 11, "Грудень": 12}
    c_m, c_y = st.columns(2)
    cur_month = st.session_state["form_date"].month
    sel_m = c_m.selectbox("Місяць", list(months.keys()), index=cur_month-1)
    sel_y = c_y.selectbox("Рік", [2025, 2026, 2027], index=1)
    
    if st.button("🚀 Згенерувати матрицю PnL", type="primary", use_container_width=True):
        with st.spinner("Збір даних з бази..."):
            m_num = months[sel_m]
            start_d = f"{sel_y}-{m_num:02d}-01"
            if m_num == 12:
                end_d = f"{sel_y+1}-01-01"
            else:
                end_d = f"{sel_y}-{m_num+1:02d}-01"
                
            num_days = calendar.monthrange(sel_y, m_num)[1]
            
            # Повний порядок рядків у матриці PnL за твоїм Excel
            expense_groups_list = list(EXPENSE_TREE.keys())
            order_full = ["Касса на начало дня"] + INCOME_CATEGORIES + expense_groups_list + ["Інші (старі ручні записи)", "АВАНСЫ", "Касса на конец дня"]
            report_data = {cat: {str(d): {"sum": 0, "notes": [], "set": False} for d in range(1, num_days + 1)} for cat in order_full}

            url_shifts = f"{SUPABASE_URL}/rest/v1/shifts?date=gte.{start_d}&date=lt.{end_d}"
            shifts_data = requests.get(url_shifts, headers=headers).json()
            if isinstance(shifts_data, list):
                for s in shifts_data:
                    day = str(int(s['date'].split('-')[2]))
                    report_data["Касса на начало дня"][day]["sum"] = get_int(s.get('start_balance', 0))
                    report_data["Касса на начало дня"][day]["set"] = True
                    report_data["Касса на конец дня"][day]["sum"] = get_int(s.get('actual_end', 0))
                    report_data["Касса на конец дня"][day]["set"] = True

            url_trans = f"{SUPABASE_URL}/rest/v1/transactions?date=gte.{start_d}&date=lt.{end_d}"
            trans_data = requests.get(url_trans, headers=headers).json()
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
                        if note:
                            report_data[target_inc][day]["notes"].append(note)
                        elif target_inc == "Разное" and left_part:
                            report_data[target_inc][day]["notes"].append(left_part)
                    else:
                        group_name = left_part.split(' >> ')[0].strip() if ' >> ' in left_part else left_part
                        target_cat = group_name if group_name in report_data else "Інші (старі ручні записи)"
                        report_data[target_cat][day]["sum"] += amt
                        
                        sub_cat = left_part.split(' >> ')[1].strip() if ' >> ' in left_part else ""
                        full_note_parts = [p for p in [sub_cat, note] if p]
                        if full_note_parts:
                            report_data[target_cat][day]["notes"].append(" - ".join(full_note_parts))
                        elif target_cat == "Інші (старі ручні записи)" and group_name:
                            report_data[target_cat][day]["notes"].append(group_name)

            url_adv = f"{SUPABASE_URL}/rest/v1/advances?date=gte.{start_d}&date=lt.{end_d}"
            adv_data = requests.get(url_adv, headers=headers).json()
            if isinstance(adv_data, list):
                for a in adv_data:
                    day = str(int(a['date'].split('-')[2]))
                    amt = get_int(a.get('amount', 0))
                    report_data["АВАНСЫ"][day]["sum"] += amt
                    
                    adv_note = str(a.get('note', '')).strip()
                    emp = str(a.get('employee', '')).strip()
                    full_adv = f"{emp} ({adv_note})" if adv_note and emp else (emp or adv_note)
                    if full_adv:
                        report_data["АВАНСЫ"][day]["notes"].append(full_adv)

            df_rows = []
            for r in order_full:
                row_dict = {"Стаття": r}
                for d in range(1, num_days + 1):
                    cell = report_data[r][str(d)]
                    
                    if r in ["Касса на начало дня", "Касса на конец дня"]:
                        row_dict[str(d)] = str(cell["sum"]) if cell["set"] else ""
                    else:
                        if cell["sum"] == 0 and not cell["notes"]:
                            row_dict[str(d)] = ""
                        else:
                            valid_notes = [n for n in cell["notes"] if n]
                            if valid_notes:
                                notes_str = ", ".join(valid_notes)
                                row_dict[str(d)] = f"{cell['sum']} ({notes_str})"
                            else:
                                row_dict[str(d)] = str(cell["sum"])
                df_rows.append(row_dict)
                
            df_report = pd.DataFrame(df_rows)
            st.dataframe(df_report, use_container_width=True, hide_index=True)
            
            st.success("✅ Матрицю PnL успішно зведено за категоріями надходжень та витрат!")

    # --- ПЛАВАЮЧЕ МЕНЮ (СЛИЧИТЕЛЬНАЯ) ---
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🧮", key="fab_nav_kas_pnl"):
            st.session_state["active_tab"] = "Касса"
            st.rerun()
    with fc2:
        if st.button("🗃️", key="fab_nav_arch_pnl"):
            st.session_state["active_tab"] = "Архів"
            st.rerun()
    with fc3:
        with st.popover("📅"):
            d = st.date_input("Оберіть дату", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")
            if d != st.session_state["form_date"]:
                st.session_state["form_date"] = d
                prefetch_week_window(d)
                st.rerun()
    with fc5:
        if st.button("🚫", key="fab_lock_pnl"):
            st.session_state["authenticated"] = False
            if "auth" in st.query_params: del st.query_params["auth"]
            st.rerun()

# --- ФІНАЛЬНИЙ ПІДПИС ВНИЗУ СТОРІНКИ ---
st.write("---")
st.markdown("<p style='text-align: center; color: #9ca3af; font-size: 14px; font-style: italic; margin-bottom: 30px;'>Розроблено Богданом для cafe forchino з любов'ю 🧡</p>", unsafe_allow_html=True)
