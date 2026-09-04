import base64
import calendar
import io
import json
import time
import uuid
from datetime import datetime, timedelta

import pandas as pd
from PIL import Image
import requests
import streamlit as st
import streamlit.components.v1 as components

# --- НАЛАШТУВАННЯ БЕЗПЕКИ ТА КОРИСТУВАЧІВ ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Content-Profile": "public",
    "Accept-Profile": "public",
    "Prefer": "return=representation",
}

upload_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "image/jpeg",
}

# СЛОВНИК КОРИСТУВАЧІВ ТА ПРАВ ДОСТУПУ
USERS = {
    "2000": {
        "name": "Юля",
        "role": "read_only",
        "tabs": ["Касса", "Архів", "Сличительная"],
    },
    "2003": {
        "name": "Вероника",
        "role": "edit_recent",
        "tabs": ["Касса", "Архів", "Сличительная", "Закупки"],
    },
    "2323": {
        "name": "Юра",
        "role": "edit_recent",
        "tabs": ["Касса", "Архів", "Сличительная", "Закупки"],
    },
    "1907": {
        "name": "Богдан",
        "role": "admin",
        "tabs": ["Касса", "Архів", "Сличительная", "Закупки"],
    },
    "2025": {"name": "Іра", "role": "pnl_only", "tabs": ["Сличительная"]},
}

# --- КАТЕГОРІЇ ---
INCOME_CATEGORIES = ["Касса", "Дотация", "Р/С", "Разное"]

EXPENSE_TREE = {
    "Выдача денег/взаимозачёты": [
        "Материальная помощь собственникам",
        "Пополнение р/с",
    ],
    "FOOD COST / себестоимость продуктов": ["продукты", "проработки кухня/бар"],
    "WASTE technology / списание на технологию": ["вода питьевая"],
    "PAPER COST / упаковка": ["Посуда с собой"],
    "LABOR / расходы по зарплате": ["Зарплата", "зп по факту"],
    "UTILITIES / коммунальные услуги": [
        "вода/канализация",
        "директор жек",
        "электроенергия",
    ],
    "COMMUNICATION SERVICES / услуги связи и ТВ": ["мобильная связь"],
    "OPERATING SUPPLIES / хоз. материалы": [
        "Хозтовары + хоз.инвентарь",
        "канцтовары",
    ],
    "WARE, STOCK & LINEN / посуда, инвентарь, униформа, текстиль": [
        "посуда для зала",
        "форма официанты",
        "текстиль для зала",
        "барный/кухонный инвентарь",
    ],
    "MAINTENANCE & REPAIR / техобслуживание и ремонт": [
        "вентиляционных систем",
        "осмос",
        "жироулавливатели",
        "кухонного оборудования",
        "ремонт мебели",
        "фисной техники",
        "прочий ремонт",
        "ТМЦ для ремонта (расходники)",
    ],
    "OUTSIDE SERVICES / услуги внешних организаций": [
        "услуги дизайнера/художника",
        "реклама вакансий",
        "озеленение (ТМЦ)",
        "прочие услуги внешних организаций",
    ],
    "PROMOTION / продвижение": [
        "меню choice/smap/knaipa",
        "типография / брендированная продукция",
    ],
    "TRANSPORT / транспорт и топливо": [
        "заправка газ. балона",
        "новая почта",
        "такси",
        "транспорт",
    ],
    "MISCELLANEOUS / разное": ["аптечка", "прочее", "декорации (ТМЦ)"],
    "Аренда": ["аренда помещения", "аренда подвала"],
    "MARKETING / маркетинговые расходы": ["маркетинговые активности"],
}

EXPENSE_CHOICES = []
for group, subs in EXPENSE_TREE.items():
    for sub in subs:
        EXPENSE_CHOICES.append(f"{group} ➔ {sub}")

# --- БАЗОВИЙ СПРАВОЧНИК ХОЗІВ ТА УПАКОВКИ ---
DEFAULT_SUPPLIES_CATALOG = [
    {
        "category": "Упаковка с собой",
        "name": "Пакет крафт 28х15х32",
        "unit": "шт",
        "par": 300,
        "supplier": "Папирус",
    },
    {
        "category": "Упаковка с собой",
        "name": "Ланч-бокс крафт 1000мл",
        "unit": "шт",
        "par": 200,
        "supplier": "Папирус",
    },
    {
        "category": "Упаковка с собой",
        "name": "Супник 500мл + крышка",
        "unit": "шт",
        "par": 150,
        "supplier": "Папирус",
    },
    {
        "category": "Упаковка с собой",
        "name": "Соусник 50мл + крышка",
        "unit": "шт",
        "par": 300,
        "supplier": "Папирус",
    },
    {
        "category": "Упаковка с собой",
        "name": "Стакан 250мл",
        "unit": "шт",
        "par": 400,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Упаковка с собой",
        "name": "Стакан 175мл",
        "unit": "шт",
        "par": 500,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Упаковка с собой",
        "name": "Крышка на стакан 250мл",
        "unit": "шт",
        "par": 400,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Хозтовары",
        "name": "Пакеты мусорные 120л",
        "unit": "рул",
        "par": 10,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Хозтовары",
        "name": "Пакеты мусорные 60л",
        "unit": "рул",
        "par": 15,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Хозтовары",
        "name": "Перчатки нитриловые L",
        "unit": "уп",
        "par": 10,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Хозтовары",
        "name": "Перчатки нитриловые M",
        "unit": "уп",
        "par": 10,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Хозтовары",
        "name": "Бумажные полотенца рулон",
        "unit": "рул",
        "par": 20,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Хозтовары",
        "name": "Туалетная бумага",
        "unit": "рул",
        "par": 30,
        "supplier": "Альфа-Пак",
    },
    {
        "category": "Бытовая химия",
        "name": "Моющее для посуды 5л",
        "unit": "канистра",
        "par": 2,
        "supplier": "ХимПром",
    },
    {
        "category": "Бытовая химия",
        "name": "Дезинфектор поверхностей 5л",
        "unit": "канистра",
        "par": 2,
        "supplier": "ХимПром",
    },
    {
        "category": "Бытовая химия",
        "name": "Губки для посуды (10шт)",
        "unit": "уп",
        "par": 5,
        "supplier": "Альфа-Пак",
    },
]


# --- ФУНКЦІЯ АУДИТУ (ЖУРНАЛ ОПЕРАЦІЙ) ---
def log_audit(action, details=""):
    try:
        user_name = st.session_state.get("user_name", "Система")
        kyiv_time = (datetime.utcnow() + timedelta(hours=3)).isoformat()
        payload = {
            "user_name": user_name,
            "action": action,
            "details": details,
            "created_at": kyiv_time,
        }
        requests.post(
            f"{SUPABASE_URL}/rest/v1/audit_logs",
            headers=headers,
            json=payload,
        )
    except Exception:
        pass


# --- ДОПОМІЖНІ ФУНКЦІЇ ТА РОЗУМНЕ КЕШУВАННЯ ---
@st.cache_data(ttl=60)
def get_start_balance(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return get_int(res[0].get("calculated_end", 0))
    except Exception:
        pass
    return 0


@st.cache_data(ttl=60)
def get_previous_advances(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            last_date = res[0].get("date")
            if last_date:
                url_adv = f"{SUPABASE_URL}/rest/v1/advances?date=eq.{last_date}"
                res_adv = requests.get(url_adv, headers=headers).json()
                if isinstance(res_adv, list):
                    return [
                        {
                            "Співробітник": item.get("employee", ""),
                            "Сума": get_int(item.get("amount", 0)),
                            "Примітка": "",
                        }
                        for item in res_adv
                    ]
    except Exception:
        pass
    return []


@st.cache_data(ttl=60)
def get_previous_coins(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            last_date = res[0].get("date")
            if last_date:
                url_draft = (
                    f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{last_date}"
                )
                res_draft = requests.get(url_draft, headers=headers).json()
                if isinstance(res_draft, list) and len(res_draft) > 0:
                    payload = res_draft[0].get("payload", {})
                    return get_int(payload.get("cash", {}).get("coins", 0))
    except Exception:
        pass
    return 0


def get_int(val):
    try:
        if pd.isna(val):
            return 0
        if not val:
            return 0
        clean_val = str(val).strip().replace(" ", "")
        if clean_val in ("None", "<NA>", "nan", ""):
            return 0
        return int(float(clean_val))
    except Exception:
        return 0


def sanitize_df(df):
    records = df.to_dict("records")
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

    if isinstance(center_date_obj, datetime):
        center_date_obj = center_date_obj.date()

    start_date = (center_date_obj - timedelta(days=3)).strftime("%Y-%m-%d")
    end_date = (center_date_obj + timedelta(days=3)).strftime("%Y-%m-%d")

    try:
        url = f"{SUPABASE_URL}/rest/v1/drafts?date=gte.{start_date}&date=lte.{end_date}"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list):
            for row in res:
                d = row.get("date")
                st.session_state["drafts_cache"][d] = row.get("payload", {})
    except Exception:
        pass


def upload_receipts_to_supabase(date_str, receipts_list):
    if not receipts_list:
        return True

    errors = []
    for r in receipts_list:
        safe_name = r["name"].replace(" ", "_").replace("/", "-")
        file_path = f"{date_str}/{r['id']}_{safe_name}"
        url = f"{SUPABASE_URL}/storage/v1/object/receipts/{file_path}"

        try:
            res = requests.post(url, headers=upload_headers, data=r["bytes"])
            if res.status_code not in [200, 201]:
                errors.append(f"{r['name']}: {res.text}")
        except Exception as e:
            errors.append(f"{r['name']}: {e}")

    if errors:
        st.error("❌ Деякі чеки не завантажилися в хмару:")
        for err in errors:
            st.write(err)
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
        df["Сума"] = pd.to_numeric(df["Сума"], errors="coerce").astype("Int64")
    for col in columns:
        if col != "Сума":
            df[col] = df[col].fillna("")
    return df[columns]


def load_draft_or_init(date_str):
    coins_key = f"coins_live_{date_str}"

    if (
        "drafts_cache" in st.session_state
        and date_str in st.session_state["drafts_cache"]
    ):
        payload = st.session_state["drafts_cache"][date_str]

        inc_loaded = payload.get("inc", [])
        st.session_state["inc_data"] = (
            inc_loaded
            if inc_loaded
            else [{"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}]
        )

        exp_loaded = payload.get("exp", [])
        clean_exp = []
        for e in exp_loaded:
            if "Категорія" in e:
                cat_val = e["Категорія"]
            elif "Група" in e:
                cat_val = f"{e['Група']} ➔ {e['Підкатегорія']}"
            else:
                cat_val = EXPENSE_CHOICES[0]
            clean_exp.append(
                {
                    "Категорія": cat_val,
                    "Сума": e.get("Сума"),
                    "Примітка": e.get("Примітка", ""),
                }
            )

        st.session_state["exp_data"] = (
            clean_exp
            if clean_exp
            else [{"Категорія": EXPENSE_CHOICES[0], "Сума": None, "Примітка": ""}]
        )

        st.session_state["adv_data"] = payload.get(
            "adv", [{"Співробітник": "", "Сума": None, "Примітка": ""}]
        )
        cash_data = payload.get("cash", {})
        st.session_state[coins_key] = (
            str(cash_data.get("coins", 0))
            if cash_data.get("coins", 0)
            else ""
        )
        for k in [20, 50, 100, 200, 500, 1000]:
            st.session_state[f"qty_{k}_{date_str}"] = (
                str(cash_data.get(str(k), 0))
                if cash_data.get(str(k), 0)
                else ""
            )
        return

    try:
        url_draft = f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{date_str}"
        draft_res = requests.get(url_draft, headers=headers).json()
        if isinstance(draft_res, list) and len(draft_res) > 0:
            payload = draft_res[0].get("payload", {})
            st.session_state["drafts_cache"][date_str] = payload

            inc_loaded = payload.get("inc", [])
            st.session_state["inc_data"] = (
                inc_loaded
                if inc_loaded
                else [
                    {
                        "Категорія": INCOME_CATEGORIES[0],
                        "Сума": None,
                        "Примітка": "",
                    }
                ]
            )

            exp_loaded = payload.get("exp", [])
            clean_exp = []
            for e in exp_loaded:
                if "Категорія" in e:
                    cat_val = e["Категорія"]
                elif "Група" in e:
                    cat_val = f"{e['Група']} ➔ {e['Підкатегорія']}"
                else:
                    cat_val = EXPENSE_CHOICES[0]
                clean_exp.append(
                    {
                        "Категорія": cat_val,
                        "Сума": e.get("Сума"),
                        "Примітка": e.get("Примітка", ""),
                    }
                )

            st.session_state["exp_data"] = (
                clean_exp
                if clean_exp
                else [
                    {
                        "Категорія": EXPENSE_CHOICES[0],
                        "Сума": None,
                        "Примітка": "",
                    }
                ]
            )
            st.session_state["adv_data"] = payload.get(
                "adv", [{"Співробітник": "", "Сума": None, "Примітка": ""}]
            )

            cash_data = payload.get("cash", {})
            st.session_state[coins_key] = (
                str(cash_data.get("coins", 0))
                if cash_data.get("coins", 0)
                else ""
            )
            for k in [20, 50, 100, 200, 500, 1000]:
                st.session_state[f"qty_{k}_{date_str}"] = (
                    str(cash_data.get(str(k), 0))
                    if cash_data.get(str(k), 0)
                    else ""
                )
            return
    except Exception:
        pass

    st.session_state["inc_data"] = [
        {"Категорія": INCOME_CATEGORIES[0], "Сума": None, "Примітка": ""}
    ]
    st.session_state["exp_data"] = [
        {"Категорія": EXPENSE_CHOICES[0], "Сума": None, "Примітка": ""}
    ]
    prev_adv = get_previous_advances(date_str)
    st.session_state["adv_data"] = (
        prev_adv
        if prev_adv
        else [{"Співробітник": "", "Сума": None, "Примітка": ""}]
    )
    prev_coins = get_previous_coins(date_str)
    st.session_state[coins_key] = str(prev_coins) if prev_coins else ""
    for k in [20, 50, 100, 200, 500, 1000]:
        st.session_state[f"qty_{k}_{date_str}"] = ""


# --- НАЛАШТУВАННЯ СТОРІНКИ ---
ICON_URL = "https://ajkprfhuypcamnybqusr.supabase.co/storage/v1/object/public/assets/xHJLUtG-wHDFARC-LtBbXJE_original.png?v=2"
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
""",
    unsafe_allow_html=True,
)

st.title("Cafe Forchino🍋")

with st.popover("🚀 Версія: 3.1.0 (Оновлений PnL)"):
    st.markdown("""
    **Останні оновлення:**
    * **v3.1.0:** У вкладці «Сличительная» закріплено першу колонку з назвами статей при горизонтальній прокрутці, вирівняно однакову ширину колонок днів та зроблено відображення таблиці на повну висоту.
    * **v3.0.0:** Додано інтерактивний модуль закупівлі господарських товарів та упаковки з генерацією текстових повідомлень і збереженням історії замовлень.
    * **v2.9.0:** Впроваджено рівні доступу та журнал аудиту.
    """)

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
coins_key = f"coins_live_{selected_date}"

can_edit = False
user_role = st.session_state.get("user_role", "read_only")

kyiv_today = (datetime.utcnow() + timedelta(hours=3)).date()
yesterday = kyiv_today - timedelta(days=1)

selected_date_obj = st.session_state["form_date"]
if isinstance(selected_date_obj, datetime):
    compare_date = selected_date_obj.date()
else:
    compare_date = selected_date_obj

if user_role == "admin":
    can_edit = True
elif user_role == "edit_recent":
    if compare_date >= yesterday:
        can_edit = True

if st.session_state.get("current_loaded_date") != selected_date:
    load_draft_or_init(selected_date)
    st.session_state["current_loaded_date"] = selected_date


# ==========================================
# РОЗДІЛ 1: КАСА
# ==========================================
if st.session_state["active_tab"] == "Касса":

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, ви переглядаєте цей день в режимі «Тільки читання»."
        )

    start_balance = get_int(get_start_balance(selected_date))
    st.text_input(
        "Залишок на початок дня (автоматично):",
        value=str(start_balance),
        disabled=True,
    )

    st.divider()
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.subheader("📈Надходження:")
        inc_df = prepare_df(
            st.session_state["inc_data"], ["Категорія", "Сума", "Примітка"]
        )
        edited_inc_df = st.data_editor(
            inc_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn(
                    "Стаття надходження",
                    options=INCOME_CATEGORIES,
                    required=True,
                ),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1
                ),
                "Примітка": st.column_config.TextColumn("Деталі"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key=f"inc_editor_{selected_date}",
            disabled=not can_edit,
        )
        subtotal_inc = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_inc_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {subtotal_inc} грн</p>",
            unsafe_allow_html=True,
        )

    with col_t2:
        st.subheader("📉Витрати:")
        exp_df = prepare_df(
            st.session_state["exp_data"], ["Категорія", "Сума", "Примітка"]
        )
        edited_exp_df = st.data_editor(
            exp_df,
            column_config={
                "Категорія": st.column_config.SelectboxColumn(
                    "Стаття витрат", options=EXPENSE_CHOICES, required=True
                ),
                "Сума": st.column_config.NumberColumn(
                    "Сума", min_value=0, step=1
                ),
                "Примітка": st.column_config.TextColumn("Деталі"),
            },
            num_rows="dynamic",
            use_container_width=True,
            key=f"exp_editor_{selected_date}",
            disabled=not can_edit,
        )
        subtotal_exp = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_exp_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: bold; color: #c62828;'>Загалом: {subtotal_exp} грн</p>",
            unsafe_allow_html=True,
        )

    st.divider()
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.subheader("💸Аванси:")
        adv_df = prepare_df(
            st.session_state["adv_data"],
            ["Співробітник", "Сума", "Примітка"],
        )
        edited_adv_df = st.data_editor(
            adv_df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"adv_editor_{selected_date}",
            disabled=not can_edit,
        )
        subtotal_adv = sum(
            get_int(r.get("Сума", 0)) for _, r in edited_adv_df.iterrows()
        )
        st.markdown(
            f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {subtotal_adv} грн</p>",
            unsafe_allow_html=True,
        )

    with col_b2:
        st.subheader("💰Факт")
        m_coins = get_int(
            st.text_input(
                "Монети (загальна сума):",
                placeholder="0",
                key=f"coins_live_{selected_date}",
                disabled=not can_edit,
            )
        )
        st.markdown('<div class="fact-block">', unsafe_allow_html=True)

        def cash_row(label, mult):
            c1, c2 = st.columns([1, 4])
            with c1:
                st.markdown(
                    f"<div style='margin-top:8px;font-weight:bold;'>{label}</div>",
                    unsafe_allow_html=True,
                )
            with c2:
                qty = get_int(
                    st.text_input(
                        f"q{label}",
                        label_visibility="collapsed",
                        placeholder="0",
                        key=f"qty_{label}_{selected_date}",
                        disabled=not can_edit,
                    )
                )
            return qty, qty * mult

        q_20, v_20 = cash_row("20", 20)
        q_50, v_50 = cash_row("50", 50)
        q_100, v_100 = cash_row("100", 100)
        q_200, v_200 = cash_row("200", 200)
        q_500, v_500 = cash_row("500", 500)
        q_1000, v_1000 = cash_row("1000", 1000)
        st.markdown("</div>", unsafe_allow_html=True)

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
    if discrepancy == 0:
        res_c3.success("Зійшлася!")
    elif discrepancy > 0:
        res_c3.warning(f"+{discrepancy} грн")
    else:
        res_c3.error(f"{discrepancy} грн")

    st.write("")

    if can_edit:
        if st.button(
            "🚀 ЗБЕРЕГТИ ФІНАЛЬНИЙ ЗВІТ",
            type="primary",
            use_container_width=True,
        ):
            with st.spinner("Стерилізація та відправка звіту..."):
                payload = {
                    "inc": sanitize_df(edited_inc_df),
                    "exp": sanitize_df(edited_exp_df),
                    "adv": sanitize_df(edited_adv_df),
                    "cash": {
                        "coins": m_coins,
                        "20": q_20,
                        "50": q_50,
                        "100": q_100,
                        "200": q_200,
                        "500": q_500,
                        "1000": q_1000,
                    },
                }
                try:
                    json.dumps(payload)
                except Exception as e:
                    st.error(f"❌ Помилка символів: {e}")
                    st.stop()

                check_draft = requests.get(
                    f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}",
                    headers=headers,
                ).json()
                if isinstance(check_draft, list) and len(check_draft) > 0:
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}",
                        headers=headers,
                        json={"payload": payload},
                    )
                else:
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/drafts",
                        headers=headers,
                        json={"date": selected_date, "payload": payload},
                    )

                st.session_state["drafts_cache"][selected_date] = payload
                st.cache_data.clear()

                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}",
                    headers=headers,
                )
                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}",
                    headers=headers,
                )
                requests.delete(
                    f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}",
                    headers=headers,
                )

                res_shift = requests.post(
                    f"{SUPABASE_URL}/rest/v1/shifts",
                    headers=headers,
                    json={
                        "date": selected_date,
                        "start_balance": str(start_balance),
                        "calculated_end": str(calculated_end),
                        "actual_end": str(total_actual),
                    },
                )

                if res_shift.status_code in [200, 201]:
                    inc_rows = []
                    for _, r in edited_inc_df.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        cat = str(r.get("Категорія", "")).strip()
                        note = str(r.get("Примітка", "")).strip()
                        if amt or cat:
                            inc_rows.append({
                                "date": selected_date,
                                "type": "income",
                                "description": f"{cat} | {note}"
                                if note
                                else cat,
                                "amount": str(amt),
                            })

                    exp_rows = []
                    for _, r in edited_exp_df.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        cat = str(r.get("Категорія", "")).strip()
                        note = str(r.get("Примітка", "")).strip()
                        if amt or cat:
                            exp_rows.append({
                                "date": selected_date,
                                "type": "expense",
                                "description": f"{cat} | {note}"
                                if note
                                else cat,
                                "amount": str(amt),
                            })

                    adv_rows = []
                    for _, r in edited_adv_df.iterrows():
                        amt = get_int(r.get("Сума", 0))
                        emp = str(r.get("Співробітник", "")).strip()
                        raw_note = r.get("Примітка", "")
                        safe_note = (
                            str(raw_note).strip()
                            if pd.notna(raw_note)
                            and str(raw_note).lower() != "nan"
                            else ""
                        )
                        if amt or emp:
                            adv_rows.append({
                                "date": selected_date,
                                "employee": emp,
                                "amount": str(amt),
                                "note": safe_note,
                            })

                    if inc_rows:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/transactions",
                            headers=headers,
                            json=inc_rows,
                        )
                    if exp_rows:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/transactions",
                            headers=headers,
                            json=exp_rows,
                        )
                    if adv_rows:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/advances",
                            headers=headers,
                            json=adv_rows,
                        )

                    log_audit(
                        "Збережено фінальний звіт", f"Дата: {selected_date}"
                    )
                    st.success("🎉 Звіт успішно збережено в хмарі!")
                else:
                    st.error(f"❌ Помилка: {res_shift.text}")

# ==========================================
# РОЗДІЛ 2: АРХІВ
# ==========================================
elif st.session_state["active_tab"] == "Архів":
    st.subheader(f"🔎 Перегляд історії: {selected_date}")

    url_shift_search = (
        f"{SUPABASE_URL}/rest/v1/shifts?date=eq.{selected_date}"
    )
    shift_res = requests.get(url_shift_search, headers=headers).json()

    if isinstance(shift_res, list) and len(shift_res) > 0:
        shift = shift_res[0]
        calc_end = get_int(shift.get("calculated_end"))

        st.markdown(
            f"<h3 style='margin-bottom: 0;'>🌅 Залишок на початок: <span style='color: #0066cc;'>{get_int(shift.get('start_balance'))} грн</span></h3>",
            unsafe_allow_html=True,
        )
        st.divider()

        ac1, ac2 = st.columns(2)
        with ac1:
            st.subheader("🟢 Надходження")
            inc_res = requests.get(
                f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.income",
                headers=headers,
            ).json()
            total_inc = 0
            if isinstance(inc_res, list):
                for item in inc_res:
                    amt = get_int(item.get("amount"))
                    total_inc += amt
                    parts = item.get("description", "Без опису").split(
                        " | ", 1
                    )
                    st.markdown(
                        f"• {parts[0]}: {amt} грн{' <i>— '+parts[1]+'</i>' if len(parts)>1 else ''}",
                        unsafe_allow_html=True,
                    )
            st.markdown(
                f"<p style='font-weight: bold; color: #2e7d32;'>Загалом: {total_inc} грн</p>",
                unsafe_allow_html=True,
            )

        with ac2:
            st.subheader("🔴 Витрати")
            exp_res = requests.get(
                f"{SUPABASE_URL}/rest/v1/transactions?date=eq.{selected_date}&type=eq.expense",
                headers=headers,
            ).json()
            total_exp = 0
            if isinstance(exp_res, list):
                for item in exp_res:
                    amt = get_int(item.get("amount"))
                    total_exp += amt
                    parts = item.get("description", "Без опису").split(
                        " | ", 1
                    )
                    st.markdown(
                        f"• {parts[0]}: {amt} грн{' <i>— '+parts[1]+'</i>' if len(parts)>1 else ''}",
                        unsafe_allow_html=True,
                    )
            st.markdown(
                f"<p style='font-weight: bold; color: #c62828;'>Загалом: {total_exp} грн</p>",
                unsafe_allow_html=True,
            )

        st.divider()
        st.markdown(
            f"<h3 style='margin-bottom: 0;'>🌇 Залишок на кінець: <span style='color: #0066cc;'>{calc_end} грн</span></h3>",
            unsafe_allow_html=True,
        )
        st.divider()

        st.subheader("🟠 Аванси")
        adv_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/advances?date=eq.{selected_date}",
            headers=headers,
        ).json()
        total_adv = 0
        if isinstance(adv_res, list):
            for item in adv_res:
                amt = get_int(item.get("amount"))
                total_adv += amt
                safe_note = str(item.get("note", "")).strip()
                st.markdown(
                    f"• {item.get('employee', 'Без імені')}: {amt} грн{' <i>— '+safe_note+'</i>' if safe_note else ''}",
                    unsafe_allow_html=True,
                )
        st.markdown(
            f"<p style='font-weight: bold; color: #ef6c00;'>Загалом: {total_adv} грн</p>",
            unsafe_allow_html=True,
        )

    else:
        st.warning("За цей день звітів не знайдено.")

    st.divider()
    c_header, c_btn = st.columns([3, 1])
    with c_header:
        st.subheader("🖼️ Галерея чеків")
    with c_btn:
        if can_edit:
            with st.popover("📷 Додати чеки"):
                ufs = st.file_uploader(
                    "Виберіть файли",
                    type=["jpg", "jpeg", "png"],
                    accept_multiple_files=True,
                    key=f"uploader_{selected_date}",
                )
                if (
                    st.button("➕ Відправити на сервер", use_container_width=True)
                    and ufs
                ):
                    with st.spinner("Завантаження..."):
                        receipts_to_upload = []
                        for uf in ufs:
                            img = Image.open(uf)
                            if img.mode in ("RGBA", "P"):
                                img = img.convert("RGB")
                            img.thumbnail((1024, 1024))
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG", quality=70)
                            receipts_to_upload.append({
                                "id": str(uuid.uuid4()),
                                "name": uf.name,
                                "bytes": buf.getvalue(),
                            })
                        if upload_receipts_to_supabase(
                            selected_date, receipts_to_upload
                        ):
                            log_audit(
                                "Завантажено чеки",
                                f"Дата: {selected_date}, К-сть: {len(ufs)}",
                            )
                            st.success("Успішно!")
                            time.sleep(1)
                            st.rerun()

    try:
        storage_res = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/list/receipts",
            headers=headers,
            json={
                "prefix": selected_date,
                "limit": 100,
                "offset": 0,
            },
        )
        if storage_res.status_code == 200:
            files_list = [
                f
                for f in storage_res.json()
                if f.get("name") and f.get("name") != ".emptyFolderPlaceholder"
            ]
            if files_list:
                img_cols = st.columns(3)
                for idx, file_obj in enumerate(files_list):
                    file_name = file_obj["name"]
                    with img_cols[idx % 3]:
                        st.image(
                            f"{SUPABASE_URL}/storage/v1/object/public/receipts/{selected_date}/{file_name}",
                            use_container_width=True,
                        )
                        if can_edit:
                            with st.popover(
                                "🗑️ Видалити", use_container_width=True
                            ):
                                st.warning(f"Видалити {file_name}?")
                                if st.button(
                                    "Так",
                                    key=f"del_{file_name}",
                                    type="primary",
                                ):
                                    if (
                                        requests.delete(
                                            f"{SUPABASE_URL}/storage/v1/object/receipts/{selected_date}/{file_name}",
                                            headers={
                                                "apikey": SUPABASE_KEY,
                                                "Authorization": f"Bearer {SUPABASE_KEY}",
                                            },
                                        ).status_code
                                        in [200, 204]
                                    ):
                                        log_audit(
                                            "Видалено чек",
                                            f"Дата: {selected_date}, Файл: {file_name}",
                                        )
                                        st.rerun()
            else:
                st.info("📂 Папка пуста.")
    except Exception:
        pass

# ==========================================
# РОЗДІЛ 3: СЛИЧИТЕЛЬНАЯ (PnL)
# ==========================================
elif st.session_state["active_tab"] == "Сличительная":
    st.subheader("📊 Сличительная ведомость")

    months = {
        "Січень": 1,
        "Лютий": 2,
        "Березень": 3,
        "Квітень": 4,
        "Травень": 5,
        "Червень": 6,
        "Липень": 7,
        "Серпень": 8,
        "Вересень": 9,
        "Жовтень": 10,
        "Листопад": 11,
        "Грудень": 12,
    }
    c_m, c_y = st.columns(2)
    sel_m = c_m.selectbox(
        "Місяць",
        list(months.keys()),
        index=st.session_state["form_date"].month - 1,
    )
    sel_y = c_y.selectbox("Рік", [2025, 2026, 2027], index=1)

    with st.spinner("Динамічний розрахунок даних..."):
        log_audit("Перегляд PnL", f"Період: {sel_m} {sel_y}")
        m_num = months[sel_m]
        start_d = f"{sel_y}-{m_num:02d}-01"
        if m_num == 12:
            end_d = f"{sel_y+1}-01-01"
        else:
            end_d = f"{sel_y}-{m_num+1:02d}-01"

        num_days = calendar.monthrange(sel_y, m_num)[1]
        expense_groups_list = list(EXPENSE_TREE.keys())

        # Карта обратного поиска: подкатегория -> (Группа, Подкатегория)
        SUB_TO_GROUP = {}
        for grp, subs in EXPENSE_TREE.items():
            for sub in subs:
                SUB_TO_GROUP[sub.strip().lower()] = (grp, sub.strip())

        # Формируем полный порядок строк: Главные категории + подкатегории
        order_full = (
            ["Касса на начало дня", "🟢 НАДХОДЖЕННЯ"]
            + INCOME_CATEGORIES
            + ["🔴 ВИТРАТИ"]
        )

        group_row_keys = []
        sub_row_keys = set()

        for grp, subs in EXPENSE_TREE.items():
            grp_key = f"📁 {grp}"
            order_full.append(grp_key)
            group_row_keys.append(grp_key)
            for sub in subs:
                sub_key = f"↳ {sub}"
                order_full.append(sub_key)
                sub_row_keys.add(sub_key)

        order_full += [
            "Інші (старі ручні записи)",
            "🔴 ВСЬОГО ВИТРАТ",
            "Касса на конец дня",
        ]
        group_row_keys.append("Інші (старі ручні записи)")

        report_data = {
            cat: {
                str(d): {"sum": 0, "notes": [], "set": False}
                for d in range(1, num_days + 1)
            }
            for cat in order_full
        }

        url_prev = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{start_d}&order=date.desc&limit=1"
        res_prev = requests.get(url_prev, headers=headers).json()
        running_balance = 0
        if isinstance(res_prev, list) and len(res_prev) > 0:
            running_balance = get_int(res_prev[0].get("calculated_end", 0))

        url_shifts = f"{SUPABASE_URL}/rest/v1/shifts?date=gte.{start_d}&date=lt.{end_d}"
        shifts_data = requests.get(url_shifts, headers=headers).json()
        active_days = set()
        if isinstance(shifts_data, list):
            for s in shifts_data:
                day = int(s["date"].split("-")[2])
                active_days.add(day)

        url_trans = f"{SUPABASE_URL}/rest/v1/transactions?date=gte.{start_d}&date=lt.{end_d}"
        trans_data = requests.get(url_trans, headers=headers).json()
        if isinstance(trans_data, list):
            for t in trans_data:
                day = str(int(t["date"].split("-")[2]))
                amt = get_int(t.get("amount", 0))
                desc_raw = t.get("description", "").strip()
                parts = desc_raw.split(" | ", 1)
                left_part = parts[0].strip()
                note = parts[1].strip() if len(parts) > 1 else ""

                if t.get("type") == "income":
                    target_inc = (
                        left_part
                        if left_part in INCOME_CATEGORIES
                        else "Разное"
                    )
                    report_data[target_inc][day]["sum"] += amt

                    note_text = f"{amt} грн ({note})" if note else f"{amt} грн"
                    report_data[target_inc][day]["notes"].append(note_text)
                else:
                    group_name = ""
                    sub_cat = ""

                    if " ➔ " in left_part:
                        sp = left_part.split(" ➔ ", 1)
                        group_name = sp[0].strip()
                        sub_cat = sp[1].strip()
                    elif " >> " in left_part:
                        sp = left_part.split(" >> ", 1)
                        group_name = sp[0].strip()
                        sub_cat = sp[1].strip()
                    elif left_part.lower() in SUB_TO_GROUP:
                        group_name, sub_cat = SUB_TO_GROUP[left_part.lower()]
                    elif left_part in EXPENSE_TREE:
                        group_name = left_part
                        sub_cat = ""
                    else:
                        group_name = "Інші (старі ручні записи)"
                        sub_cat = ""

                    grp_key = (
                        f"📁 {group_name}"
                        if group_name in EXPENSE_TREE
                        else group_name
                    )
                    sub_key = f"↳ {sub_cat}" if sub_cat else None

                    note_item = f"{amt} грн ({note})" if note else f"{amt} грн"

                    # Запись в подкатегорию
                    if sub_key and sub_key in report_data:
                        report_data[sub_key][day]["sum"] += amt
                        report_data[sub_key][day]["notes"].append(note_item)
                        report_data[sub_key][day]["set"] = True

                    # Запись в сумму группы для расчета "🔴 ВСЬОГО ВИТРАТ"
                    if grp_key in report_data:
                        report_data[grp_key][day]["sum"] += amt
                        report_data[grp_key][day]["set"] = True
                        if not sub_key:
                            report_data[grp_key][day]["notes"].append(note_item)

        for d in range(1, num_days + 1):
            day_str = str(d)
            day_total = sum(
                report_data[grp_k][day_str]["sum"] for grp_k in group_row_keys
            )
            report_data["🔴 ВСЬОГО ВИТРАТ"][day_str]["sum"] = day_total
            if day_total > 0:
                report_data["🔴 ВСЬОГО ВИТРАТ"][day_str]["set"] = True

        for d in range(1, num_days + 1):
            day_str = str(d)

            day_inc = sum(
                report_data[cat][day_str]["sum"] for cat in INCOME_CATEGORIES
            )
            day_exp = report_data["🔴 ВСЬОГО ВИТРАТ"][day_str]["sum"]

            is_active = d in active_days or day_inc > 0 or day_exp > 0

            if is_active:
                report_data["Касса на начало дня"][day_str][
                    "sum"
                ] = running_balance
                report_data["Касса на начало дня"][day_str]["set"] = True

                calc_end = running_balance + day_inc - day_exp

                report_data["Касса на конец дня"][day_str]["sum"] = calc_end
                report_data["Касса на конец дня"][day_str]["set"] = True

                running_balance = calc_end

        # --- CSS ТАБЛИЦЫ PnL С ОГРАНИЧЕНИЕМ ВЫСОТЫ И ВСЕГДА ВИДИМЫМ СКРОЛЛОМ ---
        pnl_css = """
        <style>
        .pnl-wrapper {
            overflow: auto !important; /* Включает внутреннюю прокрутку по обеим осям */
            max-height: 80vh; /* Контейнер занимает максимум 80% высоты экрана */
            width: 100%;
            margin-top: 15px;
            margin-bottom: 25px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            background-color: #ffffff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }

        /* Стильный и заметный скроллбар (всегда виден в пределах экрана) */
        .pnl-wrapper::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        .pnl-wrapper::-webkit-scrollbar-track {
            background: #f1f5f9;
            border-radius: 4px;
        }
        .pnl-wrapper::-webkit-scrollbar-thumb {
            background: #94a3b8;
            border-radius: 4px;
        }
        .pnl-wrapper::-webkit-scrollbar-thumb:hover {
            background: #64748b;
        }

        .pnl-table {
            border-collapse: separate;
            border-spacing: 0;
            width: max-content;
            table-layout: fixed !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            color: #111827;
        }
        .pnl-table th, .pnl-table td {
            padding: 7px 6px;
            border-bottom: 1px solid #e5e7eb;
            border-right: 1px solid #e5e7eb;
            text-align: center;
            box-sizing: border-box !important;
            vertical-align: middle;
        }
        /* Шапка таблицы - липнет к верху внутреннего окна */
        .pnl-table th {
            background-color: #f3f4f6;
            font-weight: 700;
            border-bottom: 2px solid #cbd5e1;
            position: sticky;
            top: 0;
            z-index: 3;
            white-space: nowrap;
        }
        /* Первый столбец (Стаття) - липнет к левому краю */
        .pnl-table th:first-child, 
        .pnl-table td:first-child {
            position: sticky;
            left: 0;
            z-index: 5 !important;
            text-align: left;
            width: 320px !important;
            min-width: 320px !important;
            max-width: 320px !important;
            border-right: 2px solid #cbd5e1 !important;
            white-space: normal;
            word-break: break-word;
            line-height: 1.25;
            background-color: #ffffff;
        }
        .pnl-table th:first-child {
            z-index: 6 !important;
            background-color: #e2e8f0 !important;
            white-space: nowrap;
        }

        /* Столбцы дней (1-31) */
        .pnl-table th:not(:first-child):not(:last-child), 
        .pnl-table td:not(:first-child):not(:last-child) {
            width: 75px !important;
            min-width: 75px !important;
            max-width: 75px !important;
            white-space: nowrap;
        }

        /* Последний столбец (Всього) */
        .pnl-table th:last-child, 
        .pnl-table td:last-child {
            width: 95px !important;
            min-width: 95px !important;
            max-width: 95px !important;
            font-weight: 700;
            background-color: #f8fafc;
            border-left: 2px solid #cbd5e1;
            white-space: nowrap;
        }

        /* Явные фоны первого столбца для каждого типа строк */
        .pnl-row-inc td:first-child { background-color: #d1e7dd !important; color: #0f5132 !important; }
        .pnl-row-exp-header td:first-child { background-color: #f8d7da !important; color: #842029 !important; }
        .pnl-row-exp-total td:first-child { background-color: #fff3cd !important; color: #664d03 !important; }
        .pnl-row-cash td:first-child { background-color: #e2e3e5 !important; color: #383d41 !important; }
        .pnl-row-grp td:first-child { background-color: #e2e8f0 !important; }
        .pnl-row-sub td:first-child { background-color: #ffffff !important; padding-left: 20px !important; font-weight: 400 !important; color: #374151 !important; }

        /* ИНДИКАТОР КОММЕНТАРИЯ (уголок Excel + подсветка) */
        .has-comment {
            position: relative !important;
            cursor: pointer !important;
            background-color: #fef9c3 !important;
            font-weight: 600;
        }
        .has-comment::after {
            content: '';
            position: absolute;
            top: 0;
            right: 0;
            width: 0;
            height: 0;
            border-top: 8px solid #f59e0b;
            border-left: 8px solid transparent;
        }
        .has-comment:hover {
            background-color: #fef08a !important;
        }

        /* Цвета специальных строк */
        .pnl-row-inc, .pnl-row-inc td {
            background-color: #d1e7dd !important;
            color: #0f5132 !important;
            font-weight: 700;
        }
        .pnl-row-exp-header, .pnl-row-exp-header td {
            background-color: #f8d7da !important;
            color: #842029 !important;
            font-weight: 700;
        }
        .pnl-row-exp-total, .pnl-row-exp-total td {
            background-color: #fff3cd !important;
            color: #664d03 !important;
            font-weight: 700;
        }
        .pnl-row-cash, .pnl-row-cash td {
            background-color: #e2e3e5 !important;
            color: #383d41 !important;
            font-weight: 700;
        }

        /* Заголовок группы расходов */
        .pnl-row-grp, .pnl-row-grp td {
            background-color: #f1f5f9 !important;
            font-weight: 700 !important;
            border-top: 1px solid #cbd5e1 !important;
        }

        .pnl-row-sub:nth-child(even) td:not(:first-child):not(:last-child):not(.has-comment) {
            background-color: #f9fafb;
        }
        .pnl-row-sub:nth-child(odd) td:not(:first-child):not(:last-child):not(.has-comment) {
            background-color: #ffffff;
        }
        </style>
        """

        # Сборка HTML таблицы
        table_parts = [pnl_css, '<div class="pnl-wrapper"><table class="pnl-table"><thead><tr>']
        table_parts.append("<th>Стаття</th>")
        for d in range(1, num_days + 1):
            table_parts.append(f"<th>{d}</th>")
        table_parts.append("<th>Всього</th></tr></thead><tbody>")

        for r in order_full:
            if r == "🟢 НАДХОДЖЕННЯ":
                row_cls = "pnl-row-inc"
            elif r == "🔴 ВИТРАТИ":
                row_cls = "pnl-row-exp-header"
            elif r == "🔴 ВСЬОГО ВИТРАТ":
                row_cls = "pnl-row-exp-total"
            elif r in ["Касса на начало дня", "Касса на конец дня"]:
                row_cls = "pnl-row-cash"
            elif r in group_row_keys:
                row_cls = "pnl-row-grp"
            elif r in sub_row_keys:
                row_cls = "pnl-row-sub"
            else:
                row_cls = "pnl-row-normal"

            table_parts.append(f'<tr class="{row_cls}">')
            table_parts.append(f"<td>{r}</td>")

            row_total = 0

            for d in range(1, num_days + 1):
                cell = report_data[r][str(d)]

                # Из заголовочных строк категорий убираем суммы (оставляем пустые ячейки)
                if r in ["🟢 НАДХОДЖЕННЯ", "🔴 ВИТРАТИ"] or r.startswith("📁 "):
                    table_parts.append("<td></td>")
                elif r in ["Касса на начало дня", "Касса на конец дня", "🔴 ВСЬОГО ВИТРАТ"]:
                    val_str = str(cell["sum"]) if cell["set"] else ""
                    row_total += cell["sum"] if cell["set"] else 0
                    table_parts.append(f"<td>{val_str}</td>")
                else:
                    sum_val = cell["sum"]
                    row_total += sum_val
                    valid_notes = [n for n in cell["notes"] if n]

                    if sum_val == 0 and not valid_notes:
                        table_parts.append("<td></td>")
                    else:
                        val_str = str(sum_val)
                        if valid_notes:
                            note_lines = "\n• " + "\n• ".join(valid_notes)
                            safe_title = f"{note_lines}".replace('"', '&quot;').replace("'", '&apos;').replace("\n", "&#10;")
                            
                            js_comment = note_lines.replace("\\", "\\\\").replace("'", "\\'").replace('"', '&quot;').replace("\n", "\\n")
                            safe_stattya = r.replace("'", "\\'")

                            table_parts.append(
                                f'<td class="has-comment" title="{safe_title}" '
                                f'ondblclick="alert(\'💬 {safe_stattya} ({d} число):\\n{js_comment}\')">'
                                f'{val_str}</td>'
                            )
                        else:
                            table_parts.append(f"<td>{val_str}</td>")

            # Столбец Всього
            if r in ["🟢 НАДХОДЖЕННЯ", "🔴 ВИТРАТИ", "Касса на начало дня", "Касса на конец дня"] or r.startswith("📁 "):
                table_parts.append("<td></td>")
            else:
                vsyogo_val = str(row_total) if row_total > 0 else ""
                table_parts.append(f"<td>{vsyogo_val}</td>")

            table_parts.append("</tr>")

        table_parts.append("</tbody></table></div>")
        st.markdown("".join(table_parts), unsafe_allow_html=True)
        
# ==========================================
# РОЗДІЛ 4: ЗАКУПКИ (ХОЗИ ТА УПАКОВКА)
# ==========================================
elif st.session_state["active_tab"] == "Закупки":
    st.subheader(f"🧹 Закупка ({selected_date})")

    if not can_edit:
        st.warning(
            f"🔒 {st.session_state['user_name']}, просмотр в режиме «Только чтение»."
        )

    # --- СПИСОК КАТЕГОРИЙ И ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---
    SUPPLIES_CATEGORIES = [
        "Губки, мочалки, салфетки для уборки, мопы и инвентарь",
        "Перчатки и одноразовая одежда",
        "Пакеты для мусора",
        "Бумажная продукция (полотенца, туалетная бумага, салфетки)",
        "Бытовая химия, моющие и дезинфицирующие средства",
        "Кассовая лента, канцтовары и прочие расходники",
        "Пакеты (фасовка, вакуум, ZIP), пленка, фольга и пергамент",
        "Приборы, шпажки, соломка и мешалки",
        "Упаковка, контейнеры, стаканы, крышки, емкости и бутылки"
    ]

    def auto_assign_category(name, current_cat=""):
        if current_cat and str(current_cat).strip() in SUPPLIES_CATEGORIES:
            return str(current_cat).strip()
        n = str(name).lower()
        if any(k in n for k in ['рукавичк', 'перчатк', 'шапочк', 'фартук']):
            return "Перчатки и одноразовая одежда"
        elif any(k in n for k in ['сміття', 'мусор']):
            return "Пакеты для мусора"
        elif any(k in n for k in ['рушник', 'полотенц', 'папір', 'бумага', 'туалет']):
            return "Бумажная продукция (полотенца, туалетная бумага, салфетки)"
        elif any(k in n for k in ['засіб', 'средств', 'доместос', 'клінер', 'аква', 'гель', 'мило', 'порошок', 'білизна', 'чищення кавомашин', 'дезинфек', 'дезінфек', 'химия', 'хімія']):
            return "Бытовая химия, моющие и дезинфицирующие средства"
        elif any(k in n for k in ['касов', 'кассовая', 'діркопробивач', 'канц', 'ручка', 'скотч', 'лента']):
            return "Кассовая лента, канцтовары и прочие расходники"
        elif any(k in n for k in ['вакуум', 'зіп', 'zip', 'саше', 'фасов', 'майка', 'плівка', 'пленка', 'стретч', 'стрейч', 'фольга', 'пергамент']):
            return "Пакеты (фасовка, вакуум, ZIP), пленка, фольга и пергамент"
        elif any(k in n for k in ['ложка', 'виделка', 'вилка', 'ніж', 'палочк', 'соломка', 'мішалк', 'мешалк', 'шпажк']):
            return "Приборы, шпажки, соломка и мешалки"
        elif any(k in n for k in ['губк', 'мочалк', 'скребок', 'тканина', 'мікрофібр', 'насадк', 'швабр', 'щітк', 'відро', 'віскоз', 'целюлоз', 'моп', 'інвентар']):
            return "Губки, мочалки, салфетки для уборки, мопы и инвентарь"
        elif any(k in n for k in ['контейнер', 'супов', 'ємність', 'кришк', 'крышк', 'соусник', 'стакан', 'банка', 'пляшк', 'підстаканник', 'тримач', 'упаков', 'бокс', 'пакет крафт']):
            return "Упаковка, контейнеры, стаканы, крышки, емкости и бутылки"
        return "Упаковка, контейнеры, стаканы, крышки, емкости и бутылки"

    # --- ИНИЦИАЛИЗАЦИЯ ЧЕРНОВИКА СЕССИИ ---
    draft_key = f"supplies_draft_qty_{selected_date}"
    if draft_key not in st.session_state:
        st.session_state[draft_key] = {}

    # --- ЗАГРУЗКА СПРАВОЧНИКА ИЗ БАЗЫ ---
    catalog_items = []
    try:
        res_cat = requests.get(
            f"{SUPABASE_URL}/rest/v1/supplies_catalog?select=*&order=id.asc",
            headers=headers,
        )
        if res_cat.status_code == 200 and isinstance(res_cat.json(), list):
            catalog_items = res_cat.json()
    except Exception:
        pass

    if not catalog_items and "supplies_catalog" in st.session_state:
        catalog_items = st.session_state["supplies_catalog"]

    # ------------------------------------------
    # 1. ФОРМИРОВАНИЕ ЗАКАЗА ПО КАТЕГОРИЯМ
    # ------------------------------------------
    st.markdown("### 1. Формирование заказа")

    if not catalog_items:
        st.info(
            "ℹ️ Справочник товаров пуст. Добавьте позиции ниже в блоке **3. Обновление справочника**."
        )
        order_items = pd.DataFrame()
    else:
        catalog_df = pd.DataFrame(catalog_items)
        
        # Гарантируем наличие необходимых колонок
        if "sku" not in catalog_df.columns:
            catalog_df["sku"] = ""
        catalog_df["sku"] = catalog_df["sku"].fillna("")

        if "supplier" not in catalog_df.columns:
            catalog_df["supplier"] = ""
        catalog_df["supplier"] = catalog_df["supplier"].fillna("")

        if "category" not in catalog_df.columns:
            catalog_df["category"] = ""
        
        # Автоматическая разметка категорий при отсутствии
        catalog_df["category"] = catalog_df.apply(
            lambda r: auto_assign_category(r["name"], r.get("category", "")), axis=1
        )

        # Подтягиваем количества из черновика
        catalog_df["qty"] = catalog_df["id"].map(
            lambda item_id: st.session_state[draft_key].get(item_id, 0)
        )

        # Панель управления черновиком
        total_selected = sum(1 for q in st.session_state[draft_key].values() if q > 0)
        
        col_dr1, col_dr2, col_dr3 = st.columns([2, 2, 3])
        with col_dr1:
            if st.button("💾 Сохранить черновик", type="primary", use_container_width=True, disabled=not can_edit):
                st.toast("✅ Черновик заказа сохранен!", icon="💾")
                log_audit("Сохранен черновик закупки", f"Дата: {selected_date}")
        with col_dr2:
            if st.button("🗑️ Очистить ввод", use_container_width=True, disabled=not can_edit):
                st.session_state[draft_key] = {}
                st.rerun()
        with col_dr3:
            st.markdown(f"**Всего выбрано позиций:** `{total_selected}`")

        st.write("")

        # ВЫВОД КАТЕГОРИЙ В ЖЕСТКОМ ПОРЯДКЕ
        for cat_idx, category_name in enumerate(SUPPLIES_CATEGORIES):
            cat_df = catalog_df[catalog_df["category"] == category_name].copy()
            if cat_df.empty:
                continue

            # Считаем активные позиции для категории
            filled_in_cat = sum(1 for _, r in cat_df.iterrows() if st.session_state[draft_key].get(r["id"], 0) > 0)
            badge = f"🟢 [Заказано: {filled_in_cat}]" if filled_in_cat > 0 else f"({len(cat_df)} поз.)"

            with st.expander(f"**{category_name}** {badge}", expanded=(filled_in_cat > 0)):
                edited_cat = st.data_editor(
                    cat_df[["id", "sku", "name", "qty", "unit", "supplier"]],
                    column_config={
                        "id": None,      # Скрываем ID
                        "sku": None,     # Скрываем Артикул (он проявится в готовом заказе)
                        "name": st.column_config.TextColumn("Наименование", disabled=True),
                        "qty": st.column_config.NumberColumn(
                            "Количество", min_value=0, step=1, required=True
                        ),
                        "unit": st.column_config.TextColumn("Ед. изм.", disabled=True, width="small"),
                        "supplier": st.column_config.TextColumn("Поставщик", disabled=True),
                    },
                    column_order=["name", "qty", "unit", "supplier"],
                    hide_index=True,
                    use_container_width=True,
                    key=f"supplies_cat_editor_{cat_idx}_{selected_date}",
                    disabled=not can_edit,
                )

                # Записываем измененные количества в глобальный черновик сессии
                for _, row in edited_cat.iterrows():
                    item_id = row["id"]
                    val = get_int(row["qty"])
                    st.session_state[draft_key][item_id] = val
                    catalog_df.loc[catalog_df["id"] == item_id, "qty"] = val

        # Итоговые выбранные позиции (где qty > 0)
        catalog_df["qty"] = catalog_df["id"].map(lambda x: st.session_state[draft_key].get(x, 0))
        order_items = catalog_df[catalog_df["qty"] > 0].copy()

    st.divider()

    # ------------------------------------------
    # 2. ЗАКАЗЫ (ГРУППИРОВКА ПО ПОСТАВЩИКАМ)
    # ------------------------------------------
    st.markdown("### 2. Заказы")

    if order_items.empty:
        st.info(
            "ℹ️ Укажите количество позиций к закупке в блоках категорий выше."
        )
    else:
        suppliers = order_items["supplier"].unique()

        for sup in suppliers:
            st.markdown(f"#### 🚚 Поставщик: **{sup}**")
            sup_df = order_items[order_items["supplier"] == sup].copy()

            has_sku = (sup_df["sku"].astype(str).str.strip() != "").any()

            table_cols = []
            col_rename = {
                "sku": "Артикул",
                "name": "Наименование",
                "qty": "Количество",
                "unit": "Единица Измерения",
            }

            if has_sku:
                table_cols.append("sku")

            table_cols.extend(["name", "qty", "unit"])

            col_table, col_code = st.columns([1.2, 1])

            with col_table:
                st.dataframe(
                    sup_df[table_cols].rename(columns=col_rename),
                    hide_index=True,
                    use_container_width=True,
                )

            with col_code:
                msg_lines = [
                    f"Привет! Заказ для Cafe Forchino ({selected_date}):"
                ]
                for _, r in sup_df.iterrows():
                    sku_str = str(r["sku"]).strip()
                    if sku_str:
                        msg_lines.append(
                            f"• [{sku_str}] {r['name']} — {int(r['qty'])}"
                            f" {r['unit']}"
                        )
                    else:
                        msg_lines.append(
                            f"• {r['name']} — {int(r['qty'])} {r['unit']}"
                        )
                msg_lines.append("\nСпасибо!")

                full_msg = "\n".join(msg_lines)
                st.code(full_msg, language="markdown")

    st.divider()

    # Фиксация и история закупки
    col_save, col_history = st.columns([1, 1])

    with col_save:
        if can_edit and not order_items.empty:
            if st.button(
                "🚀 Фиксировать и отправлять закупку в историю",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("Сохранение закупки в облаке..."):
                    order_records = sanitize_df(
                        order_items[
                            ["sku", "name", "qty", "unit", "supplier", "category"]
                        ]
                    )

                    order_payload = {
                        "date": selected_date,
                        "created_by": st.session_state["user_name"],
                        "items": order_records,
                    }

                    res_order = requests.post(
                        f"{SUPABASE_URL}/rest/v1/supplies_orders",
                        headers=headers,
                        json={
                            "date": selected_date,
                            "payload": order_payload,
                            "created_at": (
                                datetime.utcnow() + timedelta(hours=3)
                            ).isoformat(),
                        },
                    )

                    log_audit(
                        "Сформирован заказ хозов",
                        f"Дата: {selected_date}, Позиций: {len(order_records)}",
                    )
                    st.success("🎉 Закупка успешно зафиксирована в истории!")

    with col_history:
        with st.popover("📜 Просмотреть историю прошлых закупок"):
            st.markdown("#### Последние закупки")
            try:
                res_hist = requests.get(
                    f"{SUPABASE_URL}/rest/v1/supplies_orders?order=created_at.desc&limit=5",
                    headers=headers,
                ).json()
                if isinstance(res_hist, list) and len(res_hist) > 0:
                    for h in res_hist:
                        p = h.get("payload", {})
                        st.markdown(
                            f"**Дата:** {h.get('date')} | **Кто:**"
                            f" {p.get('created_by', 'Н/Д')}"
                        )
                        items_str = ", ".join([
                            f"{it['name']} — {it['qty']} {it['unit']}"
                            for it in p.get("items", [])
                        ])
                        st.caption(f"Товары: {items_str}")
                        st.write("---")
                else:
                    st.info("История закупок пока пуста.")
            except Exception:
                st.info("Не удалось загрузить историю.")

    st.divider()

    # ------------------------------------------
    # 3. ОБНОВЛЕНИЕ И УПРАВЛЕНИЕ СПРАВОЧНИКОМ
    # ------------------------------------------
    st.markdown("### 3. Обновление справочника")
    st.caption("Добавление новых позиций и удаление устаревших из базы товаров")

    if can_edit:
        # --- ФОРМА ДОБАВЛЕНИЯ НОВОГО ТОВАРА ---
        with st.form(key="add_supplies_item_form", clear_on_submit=True):
            col_sku, col_name, col_cat, col_unit, col_sup = st.columns([1.5, 3, 2.5, 1.2, 2])

            with col_sku:
                new_sku = st.text_input(
                    "Артикул (необязательно)", placeholder="например, PKG-001"
                )
            with col_name:
                new_name = st.text_input(
                    "Наименование *", placeholder="например, Пакет крафт 28х15х32"
                )
            with col_cat:
                new_cat = st.selectbox(
                    "Категория *",
                    options=SUPPLIES_CATEGORIES,
                    index=8
                )
            with col_unit:
                new_unit = st.text_input(
                    "Ед. изм. *", placeholder="шт/рул/уп"
                )
            with col_sup:
                new_sup = st.text_input(
                    "Поставщик *", placeholder="например, Альфа-Пак"
                )

            btn_add = st.form_submit_button(
                "➕ Добавить в справочник",
                use_container_width=True,
                type="primary",
            )

            if btn_add:
                if (
                    not new_name.strip()
                    or not new_unit.strip()
                    or not new_sup.strip()
                ):
                    st.error(
                        "❌ Пожалуйста, заполните обязательные поля: Наименование,"
                        " Ед. изм. и Поставщик."
                    )
                else:
                    new_item = {
                        "sku": new_sku.strip(),
                        "name": new_name.strip(),
                        "category": new_cat.strip(),
                        "unit": new_unit.strip(),
                        "supplier": new_sup.strip(),
                    }

                    try:
                        requests.post(
                            f"{SUPABASE_URL}/rest/v1/supplies_catalog",
                            headers=headers,
                            json=new_item,
                        )
                    except Exception:
                        pass

                    if "supplies_catalog" not in st.session_state:
                        st.session_state["supplies_catalog"] = []
                    st.session_state["supplies_catalog"].append(new_item)

                    log_audit(
                        "Добавлено товар в справочник",
                        f"Товар: {new_name}, Категория: {new_cat}, Поставщик: {new_sup}",
                    )
                    st.success(
                        f"✅ Товар **{new_name}** успешно добавлен в справочник!"
                    )
                    time.sleep(1)
                    st.rerun()

        # --- ИНСТРУМЕНТ УДАЛЕНИЯ ТОВАРА ---
        if catalog_items:
            with st.expander("🗑️ Удалить позицию из справочника"):
                st.caption("Выберите позицию, которую необходимо безвозвратно удалить из Supabase:")
                
                item_map = {}
                for it in catalog_items:
                    item_id = it.get("id")
                    if item_id:
                        sku_label = f"[{it.get('sku')}] " if it.get('sku') else ""
                        label = f"{sku_label}{it.get('name')} | {it.get('supplier')} (ID: {item_id})"
                        item_map[label] = item_id

                if item_map:
                    col_del_select, col_del_btn = st.columns([3, 1])
                    with col_del_select:
                        selected_to_delete = st.selectbox(
                            "Выбор товара к удалению",
                            options=list(item_map.keys()),
                            key="del_item_selectbox",
                            label_visibility="collapsed"
                        )
                    with col_del_btn:
                        if st.button("🗑️ Удалить", type="primary", use_container_width=True):
                            target_id = item_map[selected_to_delete]
                            res_del = requests.delete(
                                f"{SUPABASE_URL}/rest/v1/supplies_catalog?id=eq.{target_id}",
                                headers=headers,
                            )
                            if res_del.status_code in [200, 204]:
                                log_audit(
                                    "Удален товар из справочника",
                                    f"Удален: {selected_to_delete}"
                                )
                                st.success("✅ Товар успешно удален!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Ошибка удаления: {res_del.text}")

    # --- ЭКСПАНДЕР ДЛЯ ПРОСМОТРА ТЕКУЩЕГО СПРАВОЧНИКА ---
    if catalog_items:
        with st.expander("📋 Просмотреть текущий справочник товаров"):
            df_cat_show = pd.DataFrame(catalog_items)
            cols_to_show = [c for c in ["sku", "name", "category", "unit", "supplier"] if c in df_cat_show.columns]
            
            df_cat_show = (
                df_cat_show[cols_to_show]
                .fillna("")
                .rename(
                    columns={
                        "sku": "Артикул",
                        "name": "Наименование",
                        "category": "Категория",
                        "unit": "Ед. изм.",
                        "supplier": "Поставщик",
                    }
                )
            )
            st.dataframe(df_cat_show, hide_index=True, use_container_width=True)

# --- ПЛАВАЮЧЕ МЕНЮ РОУТИНГ ---
fc1, fc2, fc3, fc4, fc5, fc6 = st.columns(6)
with fc1:
    st.markdown('<div id="is-floating"></div>', unsafe_allow_html=True)
    if (
        "Касса" in st.session_state["allowed_tabs"]
        and st.session_state["active_tab"] != "Касса"
    ):
        if st.button("🧮", key="nav_kas"):
            st.session_state["active_tab"] = "Касса"
            st.rerun()
with fc2:
    if (
        "Архів" in st.session_state["allowed_tabs"]
        and st.session_state["active_tab"] != "Архів"
    ):
        if st.button("🗃️", key="nav_arch"):
            st.session_state["active_tab"] = "Архів"
            st.rerun()
with fc3:
    if (
        "Сличительная" in st.session_state["allowed_tabs"]
        and st.session_state["active_tab"] != "Сличительная"
    ):
        if st.button("📊", key="nav_pnl"):
            st.session_state["active_tab"] = "Сличительная"
            st.rerun()
with fc4:
    if (
        "Закупки" in st.session_state["allowed_tabs"]
        and st.session_state["active_tab"] != "Закупки"
    ):
        if st.button("🧹", key="nav_supplies"):
            st.session_state["active_tab"] = "Закупки"
            st.rerun()
with fc5:
    with st.popover("📅"):
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
    if st.session_state["active_tab"] == "Касса" and can_edit:
        if st.button("💾", key="fab_save"):
            try:
                payload = {
                    "inc": sanitize_df(edited_inc_df),
                    "exp": sanitize_df(edited_exp_df),
                    "adv": sanitize_df(edited_adv_df),
                    "cash": {
                        "coins": m_coins,
                        "20": q_20,
                        "50": q_50,
                        "100": q_100,
                        "200": q_200,
                        "500": q_500,
                        "1000": q_1000,
                    },
                }

                check_draft = requests.get(
                    f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}",
                    headers=headers,
                ).json()
                if isinstance(check_draft, list) and len(check_draft) > 0:
                    requests.patch(
                        f"{SUPABASE_URL}/rest/v1/drafts?date=eq.{selected_date}",
                        headers=headers,
                        json={"payload": payload},
                    )
                else:
                    requests.post(
                        f"{SUPABASE_URL}/rest/v1/drafts",
                        headers=headers,
                        json={"date": selected_date, "payload": payload},
                    )

                st.session_state["drafts_cache"][selected_date] = payload
                log_audit("Збережено чернетку", f"Дата: {selected_date}")
                st.toast("✅ Чернетку збережено!", icon="💾")
            except Exception as e:
                st.error("Помилка даних.")
with fc6:
    if st.button("🚫", key="fab_logout"):
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
