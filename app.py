import base64
import json
from datetime import datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components

from config import ICON_URL, USERS
from tabs.archive import render_archive_tab
from tabs.kassa import render_kassa_tab
from tabs.pnl import render_pnl_tab
from tabs.supplies import render_supplies_tab
from tabs.tableware import render_tableware_tab
from utils import (
    load_draft_or_init,
    log_audit,
    prefetch_week_window,
    save_kassa_draft_to_supabase,
)

# --- НАЛАШТУВАННЯ СТОРІНКИ ---
st.set_page_config(
    layout="wide", page_title="Cafe Forchino", page_icon=ICON_URL
)

manifest = {
    "name": "Cafe Forchino",
    "short_name": "Forchino",
    "theme_color": "#FAF0E6",
    "background_color": "#FAF0E6",
    "display": "standalone",
    "orientation": "portrait",
    "icons": [{"src": ICON_URL, "sizes": "512x512", "type": "image/png"}],
}
manifest_b64 = base64.b64encode(json.dumps(manifest).encode()).decode()
components.html(
    f"""
<script>
    const doc = window.parent.document;
    let manifest = doc.createElement('link');
    manifest.rel = 'manifest';
    manifest.href = 'data:application/manifest+json;base64,{manifest_b64}';
    doc.head.appendChild(manifest);
</script>
""",
    height=0,
    width=0,
)

# --- НАЛАШТУВАННЯ СТИЛІВ CSS ---
st.markdown(
    """
<style>
    /* Минимальный верхний отступ страницы */
    .block-container { 
        padding-top: 0.2rem !important; 
        padding-bottom: 5rem !important; 
    }
    @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&display=swap');
    header[data-testid="stHeader"], #MainMenu, footer { display: none !important; }
    
    /* Заголовок подтянут максимально к верху */
    h1 { 
        font-family: 'Permanent Marker', cursive !important; 
        font-size: 3em !important; 
        margin-top: 0 !important; 
        margin-bottom: 0.5rem !important;
        padding-top: 0 !important; 
    }
    .stApp { background-color: #FAF0E6 !important; }
    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp label, .stApp li { color: #111827 !important; }
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div { background-color: #ffffff !important; border: 1px solid #d1d5db !important; }
    input, .stSelectbox span { color: #111827 !important; }

    /* ========================================================= */
    /* ПРЕМИАЛЬНОЕ ПЛАВАЮЩЕЕ МЕНЮ (GLASSMORPHISM DOCK)           */
    /* ========================================================= */
    #is-floating { display: none; }
    
    /* Жестко фиксируем контейнер внизу экрана по центру для любых устройств */
    div[data-testid="stHorizontalBlock"]:has(#is-floating) {
        position: fixed !important;
        bottom: 16px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        z-index: 999999 !important;
        
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 4px !important;
        
        width: max-content !important;
        max-width: 96vw !important;
        overflow-x: auto !important;
        
        background: rgba(255, 255, 255, 0.85) !important;
        backdrop-filter: blur(14px) !important;
        -webkit-backdrop-filter: blur(14px) !important;
        border: 1px solid rgba(255, 255, 255, 0.95) !important;
        border-radius: 20px !important;
        padding: 6px 8px !important;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18), 0 2px 8px rgba(15, 23, 42, 0.06) !important;
    }

    /* Отменяем адаптивное сжатие колонок Streamlit внутри нашего дока */
    div[data-testid="stHorizontalBlock"]:has(#is-floating) > div[data-testid="column"] {
        width: 38px !important;
        min-width: 38px !important;
        max-width: 38px !important;
        height: 38px !important;
        flex: 0 0 38px !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Все кнопки внутри дока */
    div[data-testid="stHorizontalBlock"]:has(#is-floating) button {
        width: 38px !important;
        height: 38px !important;
        min-width: 38px !important;
        min-height: 38px !important;
        max-width: 38px !important;
        max-height: 38px !important;
        border-radius: 10px !important;
        border: 1px solid transparent !important;
        background: rgba(241, 245, 249, 0.9) !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: transform 0.15s ease, background 0.15s ease !important;
        box-shadow: none !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#is-floating) button * {
        font-size: 16px !important;
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#is-floating) button:hover {
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
        transform: scale(1.1) !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#is-floating) button:active {
        transform: scale(0.92) !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

st.title("Cafe Forchino🍋")

# --- АВТОРИЗАЦІЯ ---
auth_token = st.query_params.get("auth")
if auth_token in USERS:
    st.session_state["authenticated"] = True
    st.session_state["user_name"] = USERS[auth_token]["name"]
    st.session_state["user_role"] = USERS[auth_token]["role"]
    st.session_state["allowed_tabs"] = USERS[auth_token]["tabs"]

if st.session_state.get("authenticated", False):
    if (
        "allowed_tabs" not in st.session_state
        or "user_role" not in st.session_state
    ):
        st.session_state["authenticated"] = False

if not st.session_state.get("authenticated", False):
    st.info("🔒 Введіть персональний пароль для доступу до системи.")
    master_pwd = st.text_input(
        "🔑 Пароль:", type="password", key="master_pwd_input"
    )
    if st.button("Увійти", key="btn_login_master"):
        if master_pwd in USERS:
            u_info = USERS[master_pwd]
            st.session_state["authenticated"] = True
            st.session_state["user_name"] = u_info["name"]
            st.session_state["user_role"] = u_info["role"]
            st.session_state["allowed_tabs"] = u_info["tabs"]
            st.session_state["active_tab"] = u_info["tabs"][0]
            st.query_params["auth"] = master_pwd
            log_audit("Увійшов в систему")
            st.rerun()
        elif master_pwd != "":
            st.error("❌ Невірний пароль!")
    st.stop()

# --- ЛОГІКА ДАТИ ТА ПРАВ ДОСТУПУ (RBAC) ---
if "form_date" not in st.session_state:
    st.session_state["form_date"] = (
        datetime.utcnow() + timedelta(hours=3)
    ).date()
    prefetch_week_window(st.session_state["form_date"])

if st.session_state.get("active_tab") not in st.session_state["allowed_tabs"]:
    st.session_state["active_tab"] = st.session_state["allowed_tabs"][0]

selected_date = st.session_state["form_date"].strftime("%Y-%m-%d")

can_edit = False
user_role = st.session_state.get("user_role", "read_only")

kyiv_today = (datetime.utcnow() + timedelta(hours=3)).date()
yesterday = kyiv_today - timedelta(days=1)

selected_date_obj = st.session_state["form_date"]
compare_date = (
    selected_date_obj.date()
    if isinstance(selected_date_obj, datetime)
    else selected_date_obj
)

if user_role == "admin":
    can_edit = True
elif user_role == "edit_recent":
    if compare_date >= yesterday:
        can_edit = True

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date

# --- РОУТИНГ ВКЛАДОК ---
active_tab = st.session_state["active_tab"]

if active_tab == "Касса":
    render_kassa_tab(selected_date, can_edit)
elif active_tab == "Архів":
    render_archive_tab(selected_date, can_edit)
elif active_tab == "Сличительная":
    render_pnl_tab()
elif active_tab == "Закупки":
    render_supplies_tab(selected_date, can_edit)
elif active_tab == "Посуда":
    render_tableware_tab(selected_date, can_edit)

# --- ЕДИНЫЙ ПЛАВАЮЩИЙ DOCK (РОУТИНГ + ДЕЙСТВИЯ) ---
fc1, fc2, fc3, fc4, fc5, fc6, fc7, fc8 = st.columns(8)

with fc1:
    # Маркер для CSS-селектора
    st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
    if (
        "Касса" in st.session_state["allowed_tabs"]
        and active_tab != "Касса"
    ):
        if st.button("🧮", key="nav_kas", help="Каса"):
            st.session_state["active_tab"] = "Касса"
            st.rerun()

with fc2:
    if (
        "Архів" in st.session_state["allowed_tabs"]
        and active_tab != "Архів"
    ):
        if st.button("🗃️", key="nav_arch", help="Архів"):
            st.session_state["active_tab"] = "Архів"
            st.rerun()

with fc3:
    if (
        "Сличительная" in st.session_state["allowed_tabs"]
        and active_tab != "Сличительная"
    ):
        if st.button("📊", key="nav_pnl", help="Звіт PnL"):
            st.session_state["active_tab"] = "Сличительная"
            st.rerun()

with fc4:
    if (
        "Закупки" in st.session_state["allowed_tabs"]
        and active_tab != "Закупки"
    ):
        if st.button("🧹", key="nav_supplies", help="Закупки"):
            st.session_state["active_tab"] = "Закупки"
            st.rerun()

with fc5:
    if (
        "Посуда" in st.session_state["allowed_tabs"]
        and active_tab != "Посуда"
    ):
        if st.button("🍽️", key="nav_tableware", help="Посуд"):
            st.session_state["active_tab"] = "Посуда"
            st.rerun()

with fc6:
    with st.popover("📅", help="Обрати дату"):
        d = st.date_input(
            "Оберіть дату",
            st.session_state["form_date"],
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )
        if d != st.session_state["form_date"]:
            st.session_state["form_date"] = d
            prefetch_week_window(d)
            st.rerun()

with fc7:
    if active_tab == "Касса" and can_edit:
        if st.button("💾", key="fab_save", help="Зберегти чернетку"):
            try:
                kp = st.session_state.get("kassa_current_payload", {})
                if kp:
                    save_kassa_draft_to_supabase(
                        selected_date,
                        kp["edited_inc_df"],
                        kp["edited_exp_df"],
                        kp["edited_adv_df"],
                        kp["m_coins"],
                        kp["q_dict"],
                    )
                    st.toast("📝 Чернетку успішно збережено!", icon="✅")
            except Exception as e:
                st.toast(f"❌ Помилка збереження: {e}", icon="⚠️")

with fc8:
    if st.button("🚫", key="fab_logout", help="Вийти з системи"):
        log_audit("Вийшов з системи")
        st.session_state.clear()
        if "auth" in st.query_params:
            del st.query_params["auth"]
        st.rerun()

st.write("---")
st.markdown(
    "<p style='text-align: center; color: #9ca3af; font-size: 14px; font-style:"
    " italic; margin-bottom: 30px;'>Розроблено Богданом для cafe forchino з"
    " любов'ю 🧡</p>",
    unsafe_allow_html=True,
)
