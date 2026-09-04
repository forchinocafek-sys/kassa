import io
from datetime import datetime, timedelta
import pandas as pd
import requests
import streamlit as st
from config import SUPABASE_URL, SUPABASE_KEY, headers, upload_headers, INCOME_CATEGORIES, EXPENSE_CHOICES

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


def auto_assign_category(name, current_cat="", supplies_categories=[]):
    if current_cat and str(current_cat).strip() in supplies_categories:
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
