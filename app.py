import streamlit as st
from datetime import datetime
import requests
import pandas as pd
import time

# Настройки облачного веб-доступа к Supabase
SUPABASE_URL = "https://ajkprfhuypcamnybqusr.supabase.co"
SUPABASE_KEY = "sb_publishable_JMxxH6oo3cwsjS09gDe91A_uHL5C90E"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Content-Profile": "public",
    "Accept-Profile": "public",
    "Prefer": "return=representation"
}

def get_int(val):
    try:
        if not val: return 0
        clean_val = str(val).strip().replace(" ", "")
        return int(float(clean_val))
    except Exception:
        return 0

def get_start_balance(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            return get_int(res[0].get('calculated_end', 0))
    except Exception:
        pass
    return 0

def get_previous_advances(date_str):
    try:
        url = f"{SUPABASE_URL}/rest/v1/shifts?date=lt.{date_str}&order=date.desc&limit=1"
        res = requests.get(url, headers=headers).json()
        if isinstance(res, list) and len(res) > 0:
            last_date = res
