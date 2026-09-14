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
    /* Минимальный верхний отступ страницы и запас снизу для дока */
    .block-container { 
        padding-top: 0.2rem !important; 
        padding-bottom: 6rem !important; 
    }
    @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&display=swap');
    
    /* Скрытие элементов шапки Streamlit */
    header[data-testid="stHeader"], 
    [data-testid="stToolbar"], 
    [data-testid="stStatusWidget"],
    .stAppDeployButton,
    #MainMenu, 
    footer { 
        display: none !important; 
        visibility: hidden !important; 
    }
    
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
    /* ПРАВИЛЬНЫЙ ИЗОЛИРОВАННЫЙ STREAMLIT DOCK (БЕЗ ПЕРЕЗАГРУЗОК) */
    /* ========================================================= */
    #floating-dock-anchor { display: none; }

    /* Убираем скрытый элемент-контейнер якоря, чтобы первая колонка не сдвигалась вниз */
    div[data-testid="stElementContainer"]:has(#floating-dock-anchor) {
        display: none !important;
        position: absolute !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* Превращаем блок колонок в плавающий Glassmorphism Dock (ПК - ПО ЦЕНТРУ) */
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) {
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
        gap: 6px !important;
        
        width: auto !important;
        min-width: max-content !important;
        max-width: max-content !important;
        
        background: rgba(255, 255, 255, 0.90) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.95) !important;
        border-radius: 22px !important;
        padding: 6px 10px !important;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18), 0 2px 8px rgba(15, 23, 42, 0.06) !important;
    }

    /* Жесткая отмена растяжения колонок Streamlit */
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) > div,
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) [data-testid="column"],
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) [data-testid="stColumn"] {
        width: 42px !important;
        min-width: 42px !important;
        max-width: 42px !important;
        height: 42px !important;
        flex: 0 0 42px !important;
        margin: 0 !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stElementContainer"],
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) .stButton,
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] {
        width: 42px !important;
        min-width: 42px !important;
        max-width: 42px !important;
        height: 42px !important;
        margin: 0 !important;
        padding: 0 !important;
    }

    /* --- ПОЛНОЕ СКРЫТИЕ ТЕКСТА И СИМВОЛОВ ВНУТРИ КНОПКИ ДАТЫ --- */
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] * {
        color: transparent !important;
        font-size: 0 !important;
        line-height: 0 !important;
        user-select: none !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] input {
        position: absolute !important;
        top: 0 !important;
        left: 0 !important;
        width: 42px !important;
        height: 42px !important;
        opacity: 0 !important;
        color: transparent !important;
        background: transparent !important;
        border: none !important;
        cursor: pointer !important;
        z-index: 10 !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] > div,
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] div[data-baseweb="input"] {
        width: 42px !important;
        height: 42px !important;
        min-width: 42px !important;
        min-height: 42px !important;
        border-radius: 14px !important;
        border: 1px solid transparent !important;
        background: rgba(241, 245, 249, 0.85) !important;
        padding: 0 !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: none !important;
        transition: all 0.2s ease !important;
        position: relative !important;
        cursor: pointer !important;
        overflow: hidden !important;
    }

    /* Рисуем иконку 📅 в центре кнопки */
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] > div::before,
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] div[data-baseweb="input"]::before {
        content: "📅" !important;
        font-size: 20px !important;
        line-height: 1 !important;
        color: #111827 !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        z-index: 5 !important;
        pointer-events: none !important;
    }

    /* Выравнивание обычных кнопок */
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) button {
        width: 42px !important;
        height: 42px !important;
        min-width: 42px !important;
        min-height: 42px !important;
        border-radius: 14px !important;
        border: 1px solid transparent !important;
        background: rgba(241, 245, 249, 0.85) !important;
        padding: 0 !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: none !important;
        transition: all 0.2s ease !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) button * {
        font-size: 20px !important;
        line-height: 1 !important;
        margin: 0 !important;
        padding: 0 !important;
        color: #111827 !important;
    }

    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) button:hover,
    div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] > div:hover {
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.1) !important;
    }

    /* ========================================================= */
    /* СМЕЩЕНИЕ К ЛЕВОМУ КРАЮ НА МОБИЛЬНЫХ ЭКРАНАХ (<= 768px)     */
    /* ========================================================= */
    @media (max-width: 768px) {
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) {
            bottom: 12px !important;
            left: 12px !important;                  /* ПРИЖИМАЕМ К ЛЕВОМУ КРАЮ */
            transform: none !important;             /* ОТМЕНЯЕМ ЦЕНТРИРОВАНИЕ */
            gap: 4px !important;
            padding: 4px 6px !important;
            border-radius: 18px !important;
            max-width: calc(100vw - 110px) !important; /* ОСТАВЛЯЕМ МЕСТО ДЛЯ ИКОНОК STREAMLIT */
            overflow-x: auto !important;
            justify-content: flex-start !important;
        }

        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) > div,
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) [data-testid="column"],
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) [data-testid="stColumn"] {
            width: 36px !important;
            min-width: 36px !important;
            max-width: 36px !important;
            height: 36px !important;
            flex: 0 0 36px !important;
        }

        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stElementContainer"],
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) .stButton,
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) button,
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"],
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] > div,
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] div[data-baseweb="input"],
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] input {
            width: 36px !important;
            height: 36px !important;
            min-width: 36px !important;
            min-height: 36px !important;
            max-width: 36px !important;
            max-height: 36px !important;
            border-radius: 11px !important;
        }

        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) button *,
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] > div::before,
        div[data-testid="stHorizontalBlock"]:has(#floating-dock-anchor) div[data-testid="stDateInput"] div[data-baseweb="input"]::before {
            font-size: 17px !important;
        }
    }

    /* Современный Glassmorphism Notification (iOS / Vercel style) */
    div[data-testid="stToast"] {
        background: rgba(17, 24, 39, 0.92) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 18px !important;
        padding: 10px 16px !important;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.25), 0 8px 10px -6px rgba(0, 0, 0, 0.2) !important;
    }
    div[data-testid="stToast"] * {
        color: #ffffff !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    div[data-testid="stToast"] button {
        color: #9ca3af !important;
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

# --- ДИНАМИЧЕСКИЙ ПЛАВАЮЩИЙ DOCK (НАТИВНЫЙ STREAMLIT — БЕЗ ПЕРЕЗАГРУЗОК) ---
allowed = st.session_state.get("allowed_tabs", [])
dock_items = []

# Показываем календарь только если не на вкладках PnL (Сличительная) или Посуда
if active_tab not in ["Сличительная", "Посуда"]:
    dock_items.append("calendar")

if "Касса" in allowed:
    dock_items.append("Касса")
if "Архів" in allowed:
    dock_items.append("Архів")
if "Сличительная" in allowed:
    dock_items.append("Сличительная")
if "Закупки" in allowed:
    dock_items.append("Закупки")
if "Посуда" in allowed:
    dock_items.append("Посуда")

if active_tab == "Касса" and can_edit:
    dock_items.append("save")

dock_items.append("logout")

# Создаем ровно столько колонок, сколько элементов в меню
dock_cols = st.columns(len(dock_items))

for idx, item in enumerate(dock_items):
    with dock_cols[idx]:
        if idx == 0:
            # Anchor для CSS
            st.markdown('<div id="floating-dock-anchor"></div>', unsafe_allow_html=True)

        if item == "calendar":
            d = st.date_input(
                "date",
                st.session_state["form_date"],
                format="DD/MM/YYYY",
                label_visibility="collapsed",
                key="dock_direct_date_picker",
            )
            if d != st.session_state["form_date"]:
                st.session_state["form_date"] = d
                st.session_state.pop("kassa_current_payload", None)
                prefetch_week_window(d)
                st.rerun()

        elif item == "Касса":
            if st.button("🧮", key="btn_dock_kas", help="Каса"):
                if active_tab != "Касса":
                    st.session_state["active_tab"] = "Касса"
                    st.rerun()

        elif item == "Архів":
            if st.button("🗃️", key="btn_dock_arch", help="Архів"):
                if active_tab != "Архів":
                    st.session_state["active_tab"] = "Архів"
                    st.rerun()

        elif item == "Сличительная":
            if st.button("📊", key="btn_dock_pnl", help="Звіт PnL"):
                if active_tab != "Сличительная":
                    st.session_state["active_tab"] = "Сличительная"
                    st.rerun()

        elif item == "Закупки":
            if st.button("🧹", key="btn_dock_sup", help="Закупки"):
                if active_tab != "Закупки":
                    st.session_state["active_tab"] = "Закупки"
                    st.rerun()

        elif item == "Посуда":
            if st.button("🍽️", key="btn_dock_tab", help="Посуд"):
                if active_tab != "Посуда":
                    st.session_state["active_tab"] = "Посуда"
                    st.rerun()

        elif item == "save":
            if st.button("💾", key="btn_dock_save", help="Зберегти чернетку"):
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
                        st.toast("Чернетка збережена", icon="✨")
                except Exception as e:
                    st.toast(f"Помилка збереження: {e}", icon="⚠️")

        elif item == "logout":
            if st.button("🚫", key="btn_dock_logout", help="Вийти"):
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
