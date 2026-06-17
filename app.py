import streamlit as st
from datetime import datetime
import requests
import pandas as pd
import time

# --- НАЛАШТУВАННЯ ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

st.set_page_config(layout="wide")

# ... (пропустим до tab2) ...

with tab2:
    st.subheader("🔎 Перегляд історії")
    search_date = st.date_input("Оберіть дату", datetime.today()).strftime('%Y-%m-%d')
    
    # Галерея
    st.divider()
    st.subheader("🖼️ Галерея чеків")
    
    list_files_url = f"{SUPABASE_URL}/storage/v1/object/list/receipts"
    try:
        storage_res = requests.post(list_files_url, headers=headers, json={"prefix": search_date})
        if storage_res.status_code == 200:
            files = storage_res.json()
            valid_files = [f for f in files if f.get('name') != '.emptyFolderPlaceholder']
            
            if valid_files:
                for f in valid_files:
                    url = f"{SUPABASE_URL}/storage/v1/object/public/receipts/{search_date}/{f['name']}"
                    st.image(url, width=200)
            else:
                st.write("Чеків немає.")
        else:
            st.write(f"Помилка: {storage_res.status_code}")
    except Exception as e:
        st.write(f"Помилка: {e}")
