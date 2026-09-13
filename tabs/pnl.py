import calendar
from datetime import datetime
import requests
import streamlit as st
from config import SUPABASE_URL, headers, EXPENSE_TREE, INCOME_CATEGORIES
from utils import log_audit, get_int


def render_pnl_tab():
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

    # --- ЗАГОЛОВОК И СЕЛЕКТОРЫ В ОДНУ СТРОКУ ---
    col_title, col_m, col_y = st.columns(
        [3, 2, 1.5], vertical_alignment="bottom"
    )

    with col_title:
        st.markdown(
            '<h3 style="margin: 0; padding-bottom: 6px; color: #111827; font-weight: 700;">📊 Сличительная ведомость</h3>',
            unsafe_allow_html=True,
        )

    with col_m:
        sel_m = st.selectbox(
            "Місяць",
            list(months.keys()),
            index=st.session_state["form_date"].month - 1,
        )

    with col_y:
        sel_y = st.selectbox("Рік", [2025, 2026, 2027], index=1)

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

        # ============================================================
        # PnL TABLE — UI & FILTERING
        # ============================================================

        today = datetime.today()
        today_day = (
            today.day
            if today.year == sel_y and today.month == m_num
            else None
        )

        month_totals = {
            r: sum(report_data[r][str(d)]["sum"] for d in range(1, num_days + 1))
            for r in order_full
        }

        active_rows = {r for r, total in month_totals.items() if total != 0}

        structural_headers = {
            "Касса на начало дня",
            "🟢 НАДХОДЖЕННЯ",
            "🔴 ВИТРАТИ",
            "🔴 ВСЬОГО ВИТРАТ",
            "Касса на конец дня",
        }

        visible_rows = set(structural_headers)
        for r in order_full:
            if r in active_rows:
                visible_rows.add(r)

        for grp, subs in EXPENSE_TREE.items():
            grp_key = f"📁 {grp}"
            has_active_sub = any(f"↳ {sub}" in active_rows for sub in subs)
            if has_active_sub or grp_key in active_rows:
                visible_rows.add(grp_key)

        hover_column_css = ""
        for d in range(1, num_days + 1):
            col_index = d + 1
            hover_column_css += f"""
            .pnl-table:has(td:nth-child({col_index}):hover) tr > td:nth-child({col_index}):not(:first-child):not(:last-child),
            .pnl-table:has(th:nth-child({col_index}):hover) tr > td:nth-child({col_index}):not(:first-child):not(:last-child),
            .pnl-table:has(td:nth-child({col_index}):hover) th:nth-child({col_index}):not(:first-child):not(:last-child),
            .pnl-table:has(th:nth-child({col_index}):hover) th:nth-child({col_index}):not(:first-child):not(:last-child) {{
                filter: brightness(0.92) !important;
            }}
            """

        pnl_css = f"""
        <style>
        .pnl-wrapper {{
            position: relative;
            overflow: auto !important;
            max-height: 78vh;
            width: 100%;
            margin-top: 12px;
            margin-bottom: 22px;
            border: 1px solid #d6d3d1;
            border-radius: 10px;
            background: #ffffff;
            box-shadow: 0 2px 8px rgba(30, 53, 87, 0.04);
            scrollbar-width: thin;
            scrollbar-color: #b8c1cc #f5f5f4;
        }}

        .pnl-wrapper::-webkit-scrollbar {{
            width: 8px;
            height: 8px;
        }}

        .pnl-wrapper::-webkit-scrollbar-track {{
            background: #f5f5f4;
            border-radius: 5px;
        }}

        .pnl-wrapper::-webkit-scrollbar-thumb {{
            background: #b8c1cc;
            border-radius: 5px;
        }}

        .pnl-wrapper::-webkit-scrollbar-thumb:hover {{
            background: #8e9aaa;
        }}

        .pnl-table {{
            border-collapse: separate;
            border-spacing: 0;
            width: max-content;
            min-width: 100%;
            table-layout: fixed !important;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            color: #1e293b;
        }}

        .pnl-table th,
        .pnl-table td {{
            box-sizing: border-box !important;
            padding: 8px 7px;
            height: 36px;
            border-bottom: 1px solid #e7e5e4;
            border-right: 1px solid #ecebea;
            text-align: center;
            vertical-align: middle;
            white-space: nowrap;
        }}

        .pnl-table th {{
            position: sticky;
            top: 0;
            z-index: 10;
            background: #f1f3f5;
            color: #1e3557;
            font-weight: 700;
            border-bottom: 2px solid #cbd3dc;
            height: 40px;
            box-shadow: 0 1px 0 rgba(30, 53, 87, 0.04);
        }}

        .pnl-table th:not(:first-child):not(:last-child) {{
            width: 75px !important;
            min-width: 75px !important;
            max-width: 75px !important;
        }}

        .pnl-table th:first-child,
        .pnl-table td:first-child {{
            position: sticky;
            left: 0;
            width: 320px !important;
            min-width: 320px !important;
            max-width: 320px !important;
            text-align: left;
            white-space: normal;
            word-break: break-word;
            line-height: 1.25;
            border-right: 2px solid #cbd3dc;
            z-index: 11;
            background: #ffffff;
        }}

        .pnl-table th:first-child {{
            z-index: 20;
            background: #e5eaf0 !important;
            color: #1e3557;
            white-space: nowrap;
        }}

        .pnl-table th:last-child,
        .pnl-table td:last-child {{
            position: sticky;
            right: 0;
            width: 105px !important;
            min-width: 105px !important;
            max-width: 105px !important;
            z-index: 12;
            font-weight: 700;
            background: #f6f7f8;
            border-left: 2px solid #cbd3dc;
        }}

        .pnl-table th:last-child {{
            z-index: 20;
            background: #e5eaf0 !important;
            color: #1e3557;
        }}

        .pnl-row-normal td:not(:first-child):not(:last-child) {{
            background: #ffffff;
        }}

        .pnl-row-normal:nth-child(even) td:not(:first-child):not(:last-child) {{
            background: #fafafa;
        }}

        .pnl-row-inc,
        .pnl-row-inc td {{
            background: #dceee6 !important;
            color: #185c43 !important;
            font-weight: 700;
        }}

        .pnl-row-inc td:first-child {{
            background: #dceee6 !important;
        }}

        .pnl-row-inc td:last-child {{
            background: #d6e9e1 !important;
        }}

        .pnl-row-exp-header,
        .pnl-row-exp-header td {{
            background: #f4dddd !important;
            color: #8b3038 !important;
            font-weight: 700;
        }}

        .pnl-row-exp-header td:last-child {{
            background: #efd8d9 !important;
        }}

        .pnl-row-exp-total,
        .pnl-row-exp-total td {{
            background: #fff4cf !important;
            color: #745713 !important;
            font-weight: 700;
        }}

        .pnl-row-exp-total td:last-child {{
            background: #fff0c2 !important;
        }}

        .pnl-row-cash,
        .pnl-row-cash td {{
            background: #e8eaed !important;
            color: #374151 !important;
            font-weight: 700;
        }}

        .pnl-row-cash td:last-child {{
            background: #e2e5e8 !important;
        }}

        .pnl-row-grp,
        .pnl-row-grp td {{
            background: #edf1f5 !important;
            color: #1e3557 !important;
            font-weight: 700 !important;
            border-top: 1px solid #d2d8df !important;
        }}

        .pnl-row-grp td:first-child {{
            background: #e5eaf0 !important;
        }}

        .pnl-row-grp td:last-child {{
            background: #e8edf2 !important;
        }}

        .pnl-row-sub td:first-child {{
            background: #ffffff !important;
            padding-left: 22px !important;
            color: #475569 !important;
            font-weight: 400 !important;
        }}

        .pnl-row-sub:nth-child(even) td:not(:first-child):not(:last-child):not(.has-comment) {{
            background: #fafafa;
        }}

        .pnl-row-sub:nth-child(odd) td:not(:first-child):not(:last-child):not(.has-comment) {{
            background: #ffffff;
        }}

        .has-comment {{
            position: relative !important;
            cursor: pointer !important;
            background: #fff4c7 !important;
            color: #1e293b !important;
            font-weight: 600;
            transition: background-color 0.12s ease;
        }}

        .has-comment::after {{
            content: '';
            position: absolute;
            top: 0;
            right: 0;
            width: 0;
            height: 0;
            border-top: 8px solid #f0a800;
            border-left: 8px solid transparent;
        }}

        .has-comment:hover {{
            background: #ffefad !important;
        }}

        .pnl-table th.pnl-today {{
            background: #1E3557 !important;
            color: #ffffff !important;
            border-left: 2px solid #1E3557 !important;
            border-right: 2px solid #1E3557 !important;
        }}

        .pnl-table td.pnl-today {{
            border-left: 2px solid #1E3557 !important;
            border-right: 2px solid #1E3557 !important;
            background-color: rgba(30, 53, 87, 0.06) !important;
        }}

        {hover_column_css}

        @media (max-width: 900px) {{
            .pnl-wrapper {{
                max-height: 72vh;
            }}
            .pnl-table {{
                font-size: 12px;
            }}
            .pnl-table th,
            .pnl-table td {{
                padding: 7px 6px;
            }}
            .pnl-table th:first-child,
            .pnl-table td:first-child {{
                width: 250px !important;
                min-width: 250px !important;
                max-width: 250px !important;
            }}
            .pnl-table th:not(:first-child):not(:last-child),
            .pnl-table td:not(:first-child):not(:last-child) {{
                width: 68px !important;
                min-width: 68px !important;
                max-width: 68px !important;
            }}
            .pnl-table th:last-child,
            .pnl-table td:last-child {{
                width: 90px !important;
                min-width: 90px !important;
                max-width: 90px !important;
            }}
        }}
        </style>
        """

        table_parts = [
            pnl_css,
            '<div class="pnl-wrapper">',
            '<table class="pnl-table">',
            "<thead><tr>",
        ]

        table_parts.append("<th>Стаття</th>")

        for d in range(1, num_days + 1):
            today_class = "pnl-today" if d == today_day else ""
            table_parts.append(f'<th class="{today_class}">{d}</th>')

        table_parts.append("<th>Всього</th></tr></thead><tbody>")

        for r in order_full:
            if r not in visible_rows:
                continue

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
                today_class = "pnl-today" if d == today_day else ""

                if (
                    r in ["🟢 НАДХОДЖЕННЯ", "🔴 ВИТРАТИ"]
                    or r.startswith("📁 ")
                ):
                    table_parts.append(f'<td class="{today_class}"></td>')
                    continue

                if r in [
                    "Касса на начало дня",
                    "Касса на конец дня",
                    "🔴 ВСЬОГО ВИТРАТ",
                ]:
                    val_str = (
                        str(cell["sum"])
                        if (cell["set"] and cell["sum"] != 0)
                        else ""
                    )
                    row_total += cell["sum"] if cell["set"] else 0
                    table_parts.append(
                        f'<td class="{today_class}">{val_str}</td>'
                    )
                    continue

                sum_val = cell["sum"]
                row_total += sum_val

                if sum_val == 0:
                    table_parts.append(f'<td class="{today_class}"></td>')
                    continue

                val_str = str(sum_val)
                valid_notes = [n for n in cell["notes"] if n]

                if valid_notes:
                    note_lines = "\n• " + "\n• ".join(valid_notes)
                    safe_title = (
                        note_lines.replace('"', "&quot;")
                        .replace("'", "&apos;")
                        .replace("\n", "&#10;")
                    )
                    js_comment = (
                        note_lines.replace("\\", "\\\\")
                        .replace("'", "\\'")
                        .replace('"', "&quot;")
                        .replace("\n", "\\n")
                    )
                    safe_stattya = r.replace("'", "\\'")

                    table_parts.append(
                        f'<td class="has-comment {today_class}" '
                        f'title="{safe_title}" '
                        f'ondblclick="alert(\'💬 {safe_stattya} ({d} число):\\n{js_comment}\')">'
                        f"{val_str}</td>"
                    )
                else:
                    table_parts.append(
                        f'<td class="{today_class}">{val_str}</td>'
                    )

            if (
                r in [
                    "🟢 НАДХОДЖЕННЯ",
                    "🔴 ВИТРАТИ",
                    "Касса на начало дня",
                    "Касса на конец дня",
                ]
                or r.startswith("📁 ")
            ):
                table_parts.append("<td></td>")
            else:
                vsyogo_val = str(row_total) if row_total != 0 else ""
                table_parts.append(f"<td>{vsyogo_val}</td>")

            table_parts.append("</tr>")

        table_parts.append("</tbody></table></div>")
        st.markdown("".join(table_parts), unsafe_allow_html=True)
