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

headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"}
upload_headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "image/jpeg"}

# --- ДОПОМІЖНІ ФУНКЦІЇ ---
@st.cache_data(ttl=60)
def get_start_balance(date_str):
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1", headers=headers).json()
        return get_int(res[0].get('calculated_end', 0)) if res and isinstance(res, list) else 0
    except: return 0

@st.cache_data(ttl=60)
def get_previous_advances(date_str):
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1", headers=headers).json()
        if res and isinstance(res, list) and (last_date := res[0].get('date')):
            adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{last_date}", headers=headers).json()
            return [{"Співробітник": i.get('employee', ''), "Сума": get_int(i.get('amount', 0)), "Примітка": ""} for i in adv_res] if isinstance(adv_res, list) else []
    except: pass
    return []

@st.cache_data(ttl=60)
def get_previous_coins(date_str):
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1", headers=headers).json()
        if res and isinstance(res, list) and (last_date := res[0].get('date')):
            draft = requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{last_date}", headers=headers).json()
            if draft and isinstance(draft, list): return get_int(draft[0].get('payload', {}).get('cash', {}).get('coins', 0))
    except: pass
    return 0

def get_int(val):
    try:
        if pd.isna(val) or not val: return 0
        v = str(val).strip().replace(" ", "")
        return 0 if v.lower() in ("none", "<na>", "nan", "") else int(float(v))
    except: return 0

def prefetch_week_window(center_date_obj):
    st.session_state.setdefault("drafts_cache", {})
    start, end = (center_date_obj - timedelta(days=3)).strftime('%Y-%m-%d'), (center_date_obj + timedelta(days=3)).strftime('%Y-%m-%d')
    try:
        res = requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=gte.{start}&date=lte.{end}", headers=headers).json()
        if isinstance(res, list): [st.session_state["drafts_cache"].update({r['date']: r.get('payload', {})}) for r in res]
    except: pass

def save_current_draft(date_str, payload):
    requests.delete(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}", headers=headers)
    requests.post(f"{SUPABASE_URL}/rest/v1/drafts", headers=headers, json={"date": date_str, "payload": payload})
    st.session_state.setdefault("drafts_cache", {})[date_str] = payload

def upload_receipts_to_supabase(date_str, receipts_list):
    if not receipts_list: return True
    errors = []
    for r in receipts_list:
        url = f"{SUPABASE_URL}/storage/v1/object/receipts/{date_str}/{r['id']}_{r['name'].replace(' ', '_').replace('/', '-')}"
        try:
            if (res := requests.post(url, headers=upload_headers, data=r['bytes'])).status_code not in [200, 201]: errors.append(f"{r['name']}: {res.text}")
        except Exception as e: errors.append(f"{r['name']}: {e}")
    if errors: st.error("❌ Деякі чеки не завантажилися:"); [st.write(e) for e in errors]; return False
    return True

def prepare_df(data_list, columns):
    df = pd.DataFrame(data_list or [{col: (None if col == "Сума" else "") for col in columns}])
    for col in columns: df[col] = df.get(col, None if col == "Сума" else "")
    if "Сума" in df.columns: df["Сума"] = pd.to_numeric(df["Сума"], errors='coerce').astype('Int64')
    return df[columns].fillna({c: "" for c in columns if c != "Сума"})

def load_draft_or_init(date_str):
    c_key, r_key = f"coins_live_{date_str}", f"receipts_{date_str}"
    st.session_state.setdefault(r_key, [])
    
    payload = st.session_state.setdefault("drafts_cache", {}).get(date_str)
    if not payload:
        try:
            res = requests.get(f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}", headers=headers).json()
            if res and isinstance(res, list): payload = st.session_state["drafts_cache"][date_str] = res[0].get('payload', {})
        except: pass

    p = payload or {}
    st.session_state["inc_data"] = p.get('inc', [{"Опис": "", "Сума": None}])
    st.session_state["exp_data"] = p.get('exp', [{"Опис": "", "Сума": None}])
    st.session_state["adv_data"] = p.get('adv', get_previous_advances(date_str) if not payload else [{"Співробітник": "", "Сума": None, "Примітка": ""}])
    
    cash = p.get('cash', {}) if payload else {}
    st.session_state[c_key] = str(cash.get('coins', get_previous_coins(date_str) if not payload else 0))
    for k in [20, 50, 100, 200, 500, 1000]: st.session_state[f"qty_{k}_{date_str}"] = str(cash.get(str(k), "")) if payload else ""

def check_auth(state_key, query_key, correct_pwd):
    if st.query_params.get(query_key) == "1": st.session_state[state_key] = True
    elif st.session_state.get(state_key): st.query_params[query_key] = "1"
    
    if not st.session_state.get(state_key):
        st.info("🔒 Введіть пароль для доступу.")
        pwd = st.text_input("🔑 Пароль:", type="password", key=f"pwd_{state_key}")
        if st.button("Увійти", key=f"btn_{state_key}"):
            if pwd == correct_pwd:
                st.session_state[state_key] = True
                st.query_params[query_key] = "1"
                st.rerun()
            elif pwd: st.error("❌ Невірний пароль!")
        return False
    return True

# --- ПАСПОРТ ТА CSS ---
ICON_URL = "https://ajkprfhuypcamnybqusr.supabase.co/storage/v1/object/public/assets/xHJLUtG-wHDFARC-LtBbXJE_original.png?v=2"
st.set_page_config(layout="wide", page_title="Cafe Forchino", page_icon=ICON_URL)

manifest_b64 = base64.b64encode(json.dumps({"name": "Cafe Forchino", "short_name": "Forchino", "theme_color": "#FAF0E6", "background_color": "#FAF0E6", "display": "standalone", "icons": [{"src": ICON_URL, "sizes": "512x512", "type": "image/png"}]}).encode()).decode()
components.html(f"""<script>
    const d=window.parent.document;
    d.head.insertAdjacentHTML('beforeend', `<link rel="manifest" href="data:application/manifest+json;base64,{manifest_b64}"><link rel="apple-touch-icon" href="{ICON_URL}"><meta name="apple-mobile-web-app-title" content="Forchino">`);
    let t=Date.now(); d.addEventListener('visibilitychange', ()=>{{ if(d.visibilityState==='visible' && (Date.now()-t)/1000>45) window.parent.location.reload(); else t=Date.now(); }});
</script>""", height=0, width=0)

st.markdown("""<style>
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&display=swap');
    header[data-testid="stHeader"], #MainMenu, footer { display: none !important; }
    h1 { font-family: 'Permanent Marker', cursive !important; font-size: 3em !important; margin-top: 0 !important; padding-top: 0 !important; }
    .stApp { background-color: #FAF0E6 !important; }
    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp label, .stApp li { color: #111827 !important; }
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 1px solid #d1d5db !important; }
    input, .stSelectbox span { color: #111827 !important; }
    .stTextInput div[data-baseweb="input"] { height: 35px !important; } .stTextInput input { padding: 5px !important; }
    .fact-block [data-testid="stHorizontalBlock"] { flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; }
    .fact-block [data-testid="column"] { width: auto !important; flex: 1 1 0% !important; min-width: 0 !important; }
    #is-floating { display: none; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) { position: fixed !important; top: 30px !important; right: 15px !important; z-index: 99999 !important; width: 50px !important; display: flex !important; flex-direction: column !important; gap: 12px !important; background: transparent !important; padding: 0 !important; opacity: 0.35 !important; transition: opacity 0.3s ease !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating):hover, div[data-testid="stHorizontalBlock"]:has(#is-floating):active { opacity: 1 !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button { width: 50px !important; height: 50px !important; border-radius: 12px !important; background: linear-gradient(135deg, #f3f4f6, #e5e7eb) !important; color: #4b5563 !important; border: 1px solid #d1d5db !important; box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important; transition: transform 0.2s !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button:hover { transform: translateY(-2px) !important; background: linear-gradient(135deg, #e5e7eb, #d1d5db) !important; }
    div[data-testid="stHorizontalBlock"]:has(#is-floating) p { font-size: 20px !important; margin: 0 !important; }
</style>""", unsafe_allow_html=True)

# --- ІНІЦІАЛІЗАЦІЯ ---
st.title("Cafe Forchino🍋")
st.session_state.setdefault("form_date", datetime.today())
st.session_state.setdefault("active_tab", "Касса")

if "drafts_cache" not in st.session_state: prefetch_week_window(st.session_state["form_date"])

selected_date = st.session_state["form_date"].strftime('%Y-%m-%d')
is_frozen = (st.session_state["form_date"].date() if hasattr(st.session_state["form_date"], 'date') else st.session_state["form_date"]) < (datetime.today() - timedelta(days=1)).date()

if st.session_state.setdefault("current_loaded_date", None) != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date
receipts_key = f"receipts_{selected_date}"

# ==================== РОЗДІЛ 1: КАСА ====================
if st.session_state["active_tab"] == "Касса" and check_auth("edit_ok", "edit_auth", "2000"):
    if is_frozen: st.warning("🔒 Цей день закрито для редагування (доступні лише сьогодні та вчора).")

    start_balance = get_int(get_start_balance(selected_date))
    st.text_input("Залишок на початок дня:", value=str(start_balance), disabled=True, key=f"start_balance_{selected_date}")
    st.divider()
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("📈Надходження:")
        edited_inc_df = st.data_editor(prepare_df(st.session_state["inc_data"], ["Опис", "Сума"]), num_rows="dynamic", use_container_width=True, disabled=is_frozen)
        subtotal_inc = sum(get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {subtotal_inc} грн</p>", unsafe_allow_html=True)
        
    with col_t2:
        c_header, c_btn = st.columns([3, 1])
        c_header.subheader("📉Витрати:")
        with c_btn.popover("📷 Чеки"):
            if (ufs := st.file_uploader("Виберіть файли", type=["jpg", "jpeg", "png"], accept_multiple_files=True, disabled=is_frozen)) and st.button("➕ Завантажити вибрані", disabled=is_frozen):
                for uf in ufs:
                    if not any(r['name'] == uf.name for r in st.session_state[receipts_key]):
                        try:
                            img = Image.open(uf).convert("RGB") if Image.open(uf).mode in ("RGBA", "P") else Image.open(uf)
                            img.thumbnail((1024, 1024)); buf = io.BytesIO(); img.save(buf, format="JPEG", quality=70) 
                            st.session_state[receipts_key].append({"id": str(uuid.uuid4()), "name": uf.name, "bytes": buf.getvalue()})
                        except Exception as e: st.error(f"Помилка з файлом: {e}")
                st.success("✅ Збережено в пам'ять!"); time.sleep(1); st.rerun()
            
            if st.session_state[receipts_key]:
                st.write("---"); st.write("📁 Готові до відправки:")
                for r in st.session_state[receipts_key]:
                    c_img, c_del = st.columns([3, 1])
                    c_img.image(r["bytes"])
                    if c_del.button("❌", key=f"del_{r['id']}", disabled=is_frozen):
                        st.session_state[receipts_key] = [x for x in st.session_state[receipts_key] if x["id"] != r["id"]]; st.rerun()

        edited_exp_df = st.data_editor(prepare_df(st.session_state["exp_data"], ["Опис", "Сума"]), num_rows="dynamic", use_container_width=True, disabled=is_frozen)
        subtotal_exp = sum(get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; color: #c62828;'>Загалом: {subtotal_exp} грн</p>", unsafe_allow_html=True)

    st.divider()
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.subheader("💸Аванси:")
        edited_adv_df = st.data_editor(prepare_df(st.session_state["adv_data"], ["Співробітник", "Сума", "Примітка"]), num_rows="dynamic", use_container_width=True, disabled=is_frozen)
        subtotal_adv = sum(get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows())
        st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {subtotal_adv} грн</p>", unsafe_allow_html=True)

    with col_b2:
        st.subheader("💰Факт")
        m_coins = get_int(st.text_input("Монети:", placeholder="0", key=f"coins_live_{selected_date}", disabled=is_frozen))
        st.markdown('<div class="fact-block">', unsafe_allow_html=True)
        def cash_row(label, mult):
            c1, c2 = st.columns([1, 4])
            c1.markdown(f"<div style='margin-top: 8px; font-weight: bold;'>{label}</div>", unsafe_allow_html=True)
            qty = get_int(c2.text_input(f"q{label}", label_visibility="collapsed", placeholder="0", key=f"qty_{label}_{selected_date}", disabled=is_frozen))
            return qty, qty * mult

        cash_vals = [cash_row(lbl, val) for lbl, val in [("20",20),("50",50),("100",100),("200",200),("500",500),("1000",1000)]]
        st.markdown('</div>', unsafe_allow_html=True)
        
        cash_pure = m_coins + sum(v for _, v in cash_vals)
        st.markdown(f"## 💵Разом в касі: {cash_pure} грн")

    st.divider()
    calculated_end = start_balance + subtotal_inc - subtotal_exp
    total_actual = cash_pure + subtotal_adv
    
    st.subheader("🏁 Підсумки зміни")
    res_c1, res_c2, res_c3 = st.columns(3)
    res_c1.metric("Розрахунок", f"{calculated_end} грн")
    res_c2.metric("Факт", f"{total_actual} грн")
    diff = total_actual - calculated_end
    if diff == 0: res_c3.success("Зійшлася!")
    elif diff > 0: res_c3.warning(f"+{diff} грн")
    else: res_c3.error(f"{diff} грн")

    payload = {"inc": edited_inc_df.to_dict('records'), "exp": edited_exp_df.to_dict('records'), "adv": edited_adv_df.to_dict('records'), "cash": {"coins": m_coins, **{str(k): q for k, (q, _) in zip([20,50,100,200,500,1000], cash_vals)}}}

    if st.button("🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ", type="primary", use_container_width=True, disabled=is_frozen):
        with st.spinner("Відправка звіту..."):
            save_current_draft(selected_date, payload)
            if not upload_receipts_to_supabase(selected_date, st.session_state[receipts_key]): st.stop()
            
            for table in ["shifts", "transactions", "advances"]: requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?date=eq.{selected_date}", headers=headers)
            
            if requests.post(f"{SUPABASE_URL}/rest/v1/shifts", headers=headers, json={"date": selected_date, "start_balance": str(start_balance), "calculated_end": str(calculated_end), "actual_end": str(total_actual)}).status_code in [200, 201]:
                
                def extract_tx(df, type_name): return [{"date": selected_date, "type": type_name, "description": str(r.get("Опис", "")).strip(), "amount": str(get_int(r.get("Сума", 0)))} for _, r in df.iterrows() if get_int(r.get("Сума", 0)) or str(r.get("Опис", "")).strip()]
                txs = extract_tx(edited_inc_df, "income") + extract_tx(edited_exp_df, "expense")
                if txs: requests.post(f"{SUPABASE_URL}/rest/v1/transactions", headers=headers, json=txs)
                
                advs = [{"date": selected_date, "employee": str(r.get("Співробітник", "")).strip(), "amount": str(get_int(r.get("Сума", 0))), "note": str(r.get("Примітка", "")).strip() if pd.notna(r.get("Примітка")) else ""} for _, r in edited_adv_df.iterrows() if get_int(r.get("Сума", 0)) or str(r.get("Співробітник", "")).strip()]
                if advs: requests.post(f"{SUPABASE_URL}/rest/v1/advances", headers=headers, json=advs)
                
                st.success("🎉 Збережено в хмарі!"); st.session_state[receipts_key] = []; time.sleep(1.5); st.cache_data.clear(); st.rerun()
            else: st.error("❌ Помилка бази даних")

    # --- FAB MENU (КАССА) ---
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🗃️", key="f_arch"):
            if not is_frozen: save_current_draft(selected_date, payload)
            st.session_state["active_tab"] = "Архів"; st.rerun()
    with fc2:
        with st.popover("📅"):
            if (d := st.date_input("Дата", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")) != st.session_state["form_date"]:
                if not is_frozen: save_current_draft(selected_date, payload)
                st.session_state["form_date"] = d; prefetch_week_window(d); st.rerun()
    with fc3:
        if st.button("💾", key="f_save", disabled=is_frozen):
            save_current_draft(selected_date, payload); st.toast("✅ Збережено!", icon="💾")
    with fc4:
        if st.button("🚫", key="f_lock"): st.session_state["edit_ok"] = False; st.query_params.pop("edit_auth", None); st.rerun()


# ==================== РОЗДІЛ 2: АРХІВ ====================
elif st.session_state["active_tab"] == "Архів" and check_auth("archive_ok", "archive_auth", "2025"):
    st.subheader(f"🔎 Історія: {selected_date}")
    
    if shift_res := requests.get(f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}", headers=headers).json():
        shift = shift_res[0]
        st.markdown(f"<h3>🌅 Початок: <span style='color: #0066cc;'>{get_int(shift.get('start_balance'))} грн</span></h3>", unsafe_allow_html=True)
        st.divider()
        
        def render_txs(title, type_val, color):
            st.subheader(title)
            data = requests.get(f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.{type_val}", headers=headers).json()
            total = 0
            if data and isinstance(data, list):
                for i in data:
                    amt = get_int(i.get('amount')); total += amt
                    st.write(f"• {i.get('description', 'Без опису')}: {amt} грн")
            else: st.write("Немає записів")
            st.markdown(f"<p style='font-weight: bold; color: {color};'>Загалом: {total} грн</p>", unsafe_allow_html=True)
            return total

        ac1, ac2 = st.columns(2)
        with ac1: render_txs("🟢 Надходження", "income", "#2e7d32")
        with ac2: render_txs("🔴 Витрати", "expense", "#c62828")
                
        st.divider()
        st.markdown(f"<h3>🌇 Кінець: <span style='color: #0066cc;'>{get_int(shift.get('calculated_end'))} грн</span></h3>", unsafe_allow_html=True)
        st.divider()
        
        st.subheader("🟠 Аванси")
        adv_res = requests.get(f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}", headers=headers).json()
        total_adv = 0
        if adv_res and isinstance(adv_res, list):
            for i in adv_res:
                amt = get_int(i.get('amount')); total_adv += amt
                note = f" <i>— {str(i.get('note')).strip()}</i>" if i.get('note') else ""
                st.markdown(f"• {i.get('employee', 'Без імені')}: {amt} грн{note}", unsafe_allow_html=True)
        else: st.write("Немає записів")
        st.markdown(f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {total_adv} грн</p>", unsafe_allow_html=True)
        
        st.divider()
        st.markdown(f"<h3 style='color: #4b5563;'>💵 Готівки: {get_int(shift.get('calculated_end')) - total_adv} грн</h3>", unsafe_allow_html=True)
    else: st.warning("За цей день звітів не знайдено.")
        
    st.divider(); st.subheader("🖼️ Чеки")
    try:
        storage_res = requests.post(f"{SUPABASE_URL}/storage/v1/object/list/receipts", headers=headers, json={"prefix": selected_date, "limit": 100, "offset": 0})
        if storage_res.status_code == 200:
            if valid_files := [f for f in storage_res.json() if f.get('name') and f.get('name') != '.emptyFolderPlaceholder']:
                img_cols = st.columns(3)
                for idx, f in enumerate(valid_files):
                    img_cols[idx % 3].image(f"{SUPABASE_URL}/storage/v1/object/public/receipts/{selected_date}/{f['name']}", use_container_width=True)
            else: st.info("📂 Папка пуста.")
        else: st.error("Помилка Storage")
    except Exception as e: st.error(f"Помилка: {e}")

    # --- FAB MENU (АРХІВ) ---
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
        if st.button("🧮", key="f_kas"): st.session_state["active_tab"] = "Касса"; st.rerun()
    with fc2:
        with st.popover("📅"):
            if (d := st.date_input("Дата", st.session_state["form_date"], format="DD/MM/YYYY", label_visibility="collapsed")) != st.session_state["form_date"]:
                st.session_state["form_date"] = d; prefetch_week_window(d); st.rerun()
    with fc3:
        if st.button("🚫", key="f_lock2"): st.session_state["archive_ok"] = False; st.query_params.pop("archive_auth", None); st.rerun()

st.write("---")
st.markdown("<p style='text-align: center; color: #9ca3af; font-size: 14px; font-style: italic; margin-bottom: 30px;'>Розроблено Богданом для cafe forchino з любов'ю 🧡</p>", unsafe_allow_html=True)
