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
    header[data-testid="stHeader"], #MainMenu, footer { display: none !important; }

    /* Скрываем кнопку деплоя (красную с короной) и виджет обратной связи Streamlit справа внизу */
    .stDeployButton, 
    [data-testid="stToolbar"],
    #MainMenu,
    footer {
        display: none !important;
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

# Обработка действий от плавающего HTML-дока через query_params / сессию
# (Чтобы кнопки внутри components.html могли безопасно управлять Streamlit)
query_action = st.query_params.get("action")
if query_action == "tab_kas":
    st.session_state["active_tab"] = "Касса"
    del st.query_params["action"]
    st.rerun()
elif query_action == "tab_arch":
    st.session_state["active_tab"] = "Архів"
    del st.query_params["action"]
    st.rerun()
elif query_action == "tab_pnl":
    st.session_state["active_tab"] = "Сличительная"
    del st.query_params["action"]
    st.rerun()
elif query_action == "tab_sup":
    st.session_state["active_tab"] = "Закупки"
    del st.query_params["action"]
    st.rerun()
elif query_action == "tab_tab":
    st.session_state["active_tab"] = "Посуда"
    del st.query_params["action"]
    st.rerun()
elif query_action == "save_draft":
    if active_tab == "Касса" and can_edit:
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
    del st.query_params["action"]
elif query_action == "logout":
    log_audit("Вийшов з системи")
    st.session_state.clear()
    if "auth" in st.query_params:
        del st.query_params["auth"]
    if "action" in st.query_params:
        del st.query_params["action"]
    st.rerun()

# --- ВЫПАДАЮЩИЙ КАЛЕНДАРЬ (УБРАН ИЗ ДОКА НАВЕРХ ДЛЯ УДОБСТВА НА МОБИЛЬНЫХ) ---
with st.expander("📅 Обрати дату або переглянути звіт", expanded=False):
    d = st.date_input(
        "Оберіть дату",
        st.session_state["form_date"],
        format="DD/MM/YYYY",
    )
    if d != st.session_state["form_date"]:
        st.session_state["form_date"] = d
        prefetch_week_window(d)
        st.rerun()

# --- ГЕНЕРАЦИЯ HTML ДЛЯ ПЛАВАЮЩЕГО DOCK (ЧЕРЕЗ ST.MARKDOWN) ---
allowed = st.session_state.get("allowed_tabs", [])
is_kassa = active_tab == "Касса"
can_save = is_kassa and can_edit

dock_html_buttons = ""

if "Касса" in allowed:
    active_cls = "active" if is_kassa else ""
    dock_html_buttons += f"""<a href="?auth={auth_token}&action=tab_kas" target="_self" class="dock-btn {active_cls}" title="Каса">🧮</a>"""

if "Архів" in allowed:
    active_cls = "active" if active_tab == "Архів" else ""
    dock_html_buttons += f"""<a href="?auth={auth_token}&action=tab_arch" target="_self" class="dock-btn {active_cls}" title="Архів">🗃️</a>"""

if "Сличительная" in allowed:
    active_cls = "active" if active_tab == "Сличительная" else ""
    dock_html_buttons += f"""<a href="?auth={auth_token}&action=tab_pnl" target="_self" class="dock-btn {active_cls}" title="Звіт PnL">📊</a>"""

if "Закупки" in allowed:
    active_cls = "active" if active_tab == "Закупки" else ""
    dock_html_buttons += f"""<a href="?auth={auth_token}&action=tab_sup" target="_self" class="dock-btn {active_cls}" title="Закупки">🧹</a>"""

if "Посуда" in allowed:
    active_cls = "active" if active_tab == "Посуда" else ""
    dock_html_buttons += f"""<a href="?auth={auth_token}&action=tab_tab" target="_self" class="dock-btn {active_cls}" title="Посуд">🍽️</a>"""

if can_save:
    dock_html_buttons += f"""<a href="?auth={auth_token}&action=save_draft" target="_self" class="dock-btn save-btn" title="Зберегти чернетку">💾</a>"""

dock_html_buttons += f"""<a href="?auth={auth_token}&action=logout" target="_self" class="dock-btn logout-btn" title="Вийти">🚫</a>"""

# Рендерим плавающий док прямо в тело документа Streamlit
st.markdown(
    f"""
<style>
    .floating-dock-wrapper {{
        position: fixed !important;
        bottom: 16px !important;
        left: 50% !important;
        transform: translateX(-50%) !important;
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 6px !important;
        background: rgba(255, 255, 255, 0.88) !important;
        backdrop-filter: blur(16px) !important;
        -webkit-backdrop-filter: blur(16px) !important;
        border: 1px solid rgba(255, 255, 255, 0.95) !important;
        border-radius: 22px !important;
        padding: 6px 10px !important;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.18), 0 2px 8px rgba(15, 23, 42, 0.06) !important;
        z-index: 999999 !important;
    }}
    .floating-dock-wrapper .dock-btn {{
        width: 42px !important;
        height: 42px !important;
        min-width: 42px !important;
        min-height: 42px !important;
        border-radius: 14px !important;
        border: 1px solid transparent !important;
        background: rgba(241, 245, 249, 0.85) !important;
        font-size: 20px !important;
        text-decoration: none !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer !important;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
        padding: 0 !important;
        margin: 0 !important;
        color: #111827 !important;
    }}
    .floating-dock-wrapper .dock-btn:hover {{
        background: #ffffff !important;
        border-color: #cbd5e1 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.1) !important;
    }}
    .floating-dock-wrapper .dock-btn.active {{
        background: #e2e8f0 !important;
        border-color: #94a3b8 !important;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.06) !important;
    }}
    .floating-dock-wrapper .save-btn {{
        background: rgba(220, 252, 231, 0.9) !important;
    }}
    .floating-dock-wrapper .logout-btn {{
        background: rgba(254, 226, 226, 0.9) !important;
    }}
</style>
<div class="floating-dock-wrapper">
    {dock_html_buttons}
</div>
""",
    unsafe_allow_html=True,
)

st.write("---")
st.markdown(
    "<p style='text-align: center; color: #9ca3af; font-size: 14px; font-style:"
    " italic; margin-bottom: 30px;'>Розроблено Богданом для cafe forchino з"
    " любов'ю 🧡</p>",
    unsafe_allow_html=True,
)
