import base64
import json
from datetime import datetime, timedelta

import streamlit as st
import streamlit.components.v1 as components

from config import ICON_URL, USERS, VENUE_FOOTER, VENUE_NAME
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
    layout="wide", page_title="meal & soul", page_icon=ICON_URL
)

manifest = {
    "name": "meal & soul",
    "short_name": "MealSoul",
    "theme_color": "#87CEFA",
    "background_color": "#87CEFA",
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
    /* 1. Геометрический шрифт Poppins (как на изображении) */
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@600;700&display=swap');

    /* 2. Фон #87CEFA для всего окна приложения */
    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background-color: #87CEFA !important;
    }

    /* 3. Убираем верхние отступы контейнера */
    .block-container {
        padding-top: 0rem !important;
        margin-top: 0rem !important;
        padding-bottom: 6rem !important;
    }

    /* 4. Скрытие элементов шапки Streamlit */
    header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stStatusWidget"], .stAppDeployButton, #MainMenu, footer {
        display: none !important;
        visibility: hidden !important;
    }

    /* 5. Стиль заголовка в точности по макету */
    h1, .brand-title {
        font-family: 'Poppins', sans-serif !important;
        font-weight: 700 !important;
        font-size: 2.3em !important;
        letter-spacing: -0.5px !important;
        margin-top: 0 !important;
        margin-bottom: 0.5rem !important;
        padding-top: 0 !important;
        line-height: 1 !important;
        color: #111827 !important;
    }

    /* 6. Основной цвет текста */
    .stApp, .stApp p, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp label, .stApp li {
        color: #111827 !important;
    }

    /* 7. Белый фон для карточек-контейнеров */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #ffffff !important;
        border-radius: 14px !important;
    }

    /* 8. Белый фон для полей ввода */
    div[data-baseweb="input"] > div, div[data-baseweb="select"] > div {
        background-color: #ffffff !important;
        border: 1px solid #d1d5db !important;
    }

    input, .stSelectbox span {
        color: #111827 !important;
    }

    #floating-dock-anchor {
        display: none;
    }

    div[data-testid="stElementContainer"]:has(#floating-dock-anchor) {
        display: none !important;
        position: absolute !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- ВЕРХНЯЯ НАДПИСЬ ---
st.markdown(
    '<h1 class="brand-title">meal & soul 💁‍♂️</h1>', unsafe_allow_html=True
)

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

# --- НАВИГАЦИЯ И ВКЛАДКИ ---
allowed = st.session_state.get("allowed_tabs", ["Касса"])
if (
    "active_tab" not in st.session_state
    or st.session_state["active_tab"] not in allowed
):
  st.session_state["active_tab"] = allowed[0]

user_role = st.session_state.get("user_role", "read_only")
can_edit = user_role in ["admin", "edit_recent"]

today = datetime.now().date()
if "selected_date" not in st.session_state:
  st.session_state["selected_date"] = today

sel_date = st.date_input(
    "📅 Дата:",
    value=st.session_state["selected_date"],
    format="DD/MM/YYYY",
    key="global_date_picker",
)
st.session_state["selected_date"] = sel_date
selected_date_str = sel_date.strftime("%Y-%m-%d")

prefetch_week_window(sel_date)

active_tab = st.radio(
    "Навигация",
    options=allowed,
    index=allowed.index(st.session_state["active_tab"]),
    horizontal=True,
    key="main_navigation_radio",
)
st.session_state["active_tab"] = active_tab

if active_tab == "Касса":
  render_kassa_tab(selected_date_str, can_edit)
elif active_tab == "Архів":
  render_archive_tab(selected_date_str, can_edit)
elif active_tab == "Сличительная":
  render_pnl_tab()
elif active_tab == "Закупки":
  render_supplies_tab(selected_date_str, can_edit)
elif active_tab == "Посуда":
  render_tableware_tab(selected_date_str, can_edit)

# --- ФУТЕР ---
st.write("---")
st.markdown(
    "<p style='text-align: center; color: #111827; font-size: 14px; font-style:"
    " italic; margin-bottom: 30px;'>Розроблено Богданом для meal & soul з"
    " любов'ю 🧡</p>",
    unsafe_allow_html=True,
)
