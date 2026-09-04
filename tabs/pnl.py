import calendar
import requests
import streamlit as st
from config import SUPABASE_URL, headers, EXPENSE_TREE, INCOME_CATEGORIES
from utils import log_audit, get_int


def render_pnl_tab():
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

        SUB_TO_GROUP = {}
        for grp, subs in EXPENSE_TREE.items():
            for sub in subs:
                SUB_TO_GROUP[sub.strip().lower()] = (grp, sub.strip())

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

                    if sub_key and sub_key in report_data:
                        report_data[sub_key][day]["sum"] += amt
                        report_data[sub_key][day]["notes"].append(note_item)
                        report_data[sub_key][day]["set"] = True

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
            overflow: auto !important;
            max-height: 80vh;
            width: 100%;
            margin-top: 15px;
            margin-bottom: 25px;
            border: 1px solid #d1d5db;
            border-radius: 10px;
            background-color: #ffffff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }

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
        .pnl-table th {
            background-color: #f3f4f6;
            font-weight: 700;
            border-bottom: 2px solid #cbd5e1;
            position: sticky;
            top: 0;
            z-index: 3;
            white-space: nowrap;
        }
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

        .pnl-table th:not(:first-child):not(:last-child), 
        .pnl-table td:not(:first-child):not(:last-child) {
            width: 75px !important;
            min-width: 75px !important;
            max-width: 75px !important;
            white-space: nowrap;
        }

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

        .pnl-row-inc td:first-child { background-color: #d1e7dd !important; color: #0f5132 !important; }
        .pnl-row-exp-header td:first-child { background-color: #f8d7da !important; color: #842029 !important; }
        .pnl-row-exp-total td:first-child { background-color: #fff3cd !important; color: #664d03 !important; }
        .pnl-row-cash td:first-child { background-color: #e2e3e5 !important; color: #383d41 !important; }
        .pnl-row-grp td:first-child { background-color: #e2e8f0 !important; }
        .pnl-row-sub td:first-child { background-color: #ffffff !important; padding-left: 20px !important; font-weight: 400 !important; color: #374151 !important; }

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

            if r in ["🟢 НАДХОДЖЕННЯ", "🔴 ВИТРАТИ", "Касса на начало дня", "Касса на конец дня"] or r.startswith("📁 "):
                table_parts.append("<td></td>")
            else:
                vsyogo_val = str(row_total) if row_total > 0 else ""
                table_parts.append(f"<td>{vsyogo_val}</td>")

            table_parts.append("</tr>")

        table_parts.append("</tbody></table></div>")
        st.markdown("".join(table_parts), unsafe_allow_html=True)
