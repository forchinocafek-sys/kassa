import io
import time
import uuid
from PIL import Image
import requests
import streamlit as st
from config import SUPABASE_URL, SUPABASE_KEY, headers
from utils import log_audit, get_int, upload_receipts_to_supabase


def render_archive_tab(selected_date, can_edit):
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
