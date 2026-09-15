import streamlit as st

# --- ПОДКЛЮЧЕНИЕ К SUPABASE ---
# В скобках указываем строго названия ключей, а не значения!
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# --- ДИНАМИЧЕСКИЕ НАСТРОЙКИ ЗАВЕДЕНИЯ ---
VENUE_NAME = st.secrets.get("VENUE_NAME", "meal&soul")
VENUE_FOOTER = st.secrets.get("VENUE_FOOTER", "meal&soul")

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

# --- ПОЛЬЗОВАТЕЛИ И ПРАВА ДОСТУПА ---
USERS = {
    "2000": {
        "name": "Юля",
        "role": "read_only",
        "tabs": ["Касса", "Архів", "Сличительная"],
    },
    "2003": {
        "name": "Вероника",
        "role": "edit_recent",
        "tabs": ["Касса", "Архів", "Сличительная", "Закупки", "Посуда"],
    },
    "2323": {
        "name": "Юра",
        "role": "edit_recent",
        "tabs": ["Касса", "Архів", "Сличительная", "Закупки", "Посуда"],
    },
    "1907": {
        "name": "Богдан",
        "role": "admin",
        "tabs": ["Касса", "Архів", "Сличительная", "Закупки", "Посуда"],
    },
    "2025": {
        "name": "Іра",
        "role": "pnl_only",
        "tabs": ["Сличительная"],
    },
}

# --- КАТЕГОРИИ И ТРЕЕ РАСХОДОВ ---
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
    "OPERATING SUPPLIES / хоз. товары": [
        "бытовая химия",
        "инвентарь",
        "канцтовары",
    ],
    "LOGISTICS / логистика": [
        "газ для балона",
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

SUPPLIES_CATEGORIES = [
    "Губки, мочалки, салфетки для уборки, мопы и инвентарь",
    "Перчатки и одноразовая одежда",
    "Пакеты для мусора",
    "Бумажная продукция (полотенца, туалетная бумага, салфетки)",
    "Бытовая химия, моющие и дезинфицирующие средства",
    "Кассовая лента, канцтовары и прочие расходники",
    "Пакеты (фасовка, вакуум, ZIP), пленка, фольга и пергамент",
    "Приборы, шпажки, соломка и мешалки",
    "Упаковка, контейнеры, стаканы, крышки, емкости и бутылки",
]
