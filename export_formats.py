"""Attendance export formats: daily PDF list + per-staff calendar HTML."""
from __future__ import annotations

from datetime import datetime as _dt, timedelta as _td
from html import escape
from io import BytesIO


def _status_label(status: str, clock_in: str = "", clock_out: str = "") -> str:
    s = (status or "present").lower().strip()
    if s == "izin":
        return "Izin"
    if s == "alpha":
        return "Alpha"
    if clock_in and clock_out:
        return "Hadir (lengkap)"
    if clock_in:
        return "Hadir (belum out)"
    if s in ("present", "hadir", ""):
        return "Hadir"
    return status or "-"


def attendance_daily_pdf_bytes(date: str, app_name: str = "Staff Management") -> dict:
    """PDF list: No | Nama | Status | Jam Masuk | Jam Keluar for one day."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    except ImportError:
        return {"success": False, "error": "reportlab belum terpasang (pip install reportlab)"}

    from database import export_attendance_rows

    result = export_attendance_rows(mode="daily", date=date)
    if not result.get("success"):
        return result
    rows = result.get("rows") or []
    meta = result.get("meta") or {}
    d = meta.get("date") or date

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=14, spaceAfter=4)
    sub_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=10)

    story = []
    story.append(Paragraph(app_name or "Staff Management", title_style))
    story.append(Paragraph("Daftar Kehadiran Harian - %s" % d, sub_style))
    story.append(Paragraph("Total: %d staff tercatat" % len(rows), sub_style))

    data = [["No", "Nama", "Status", "Jam Masuk", "Jam Keluar"]]
    for i, r in enumerate(rows, 1):
        nama = r.get("nama") or r.get("username") or "-"
        uname = r.get("username") or ""
        if uname and uname not in str(nama):
            nama = "%s (@%s)" % (nama, uname)
        cin = (r.get("clock_in") or "")[:8]
        cout = (r.get("clock_out") or "")[:8]
        st = _status_label(r.get("status"), r.get("clock_in") or "", r.get("clock_out") or "")
        data.append([str(i), nama, st, cin or "-", cout or "-"])

    if len(data) == 1:
        data.append(["-", "(belum ada data)", "-", "-", "-"])

    col_w = [12 * mm, 70 * mm, 40 * mm, 28 * mm, 28 * mm]
    table = Table(data, colWidths=col_w, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Dicetak otomatis dari sistem. Format: No - Nama - Status - Jam Masuk - Jam Keluar.",
            sub_style,
        )
    )
    doc.build(story)
    return {
        "success": True,
        "pdf": buf.getvalue(),
        "filename": "kehadiran_harian_%s.pdf" % d,
        "count": len(rows),
        "meta": meta,
    }


def attendance_staff_calendar_html(
    username: str,
    date_from: str,
    date_to: str,
    app_name: str = "Staff Management",
) -> dict:
    """HTML calendar for one staff - print / screenshot friendly (light theme)."""
    import calendar as _cal

    from database import export_attendance_rows

    result = export_attendance_rows(
        mode="staff", username=username, date_from=date_from, date_to=date_to
    )
    if not result.get("success"):
        return result
    rows = result.get("rows") or []
    meta = result.get("meta") or {}
    by_date = {r.get("date"): r for r in rows}

    try:
        d0 = _dt.strptime(date_from, "%Y-%m-%d").date()
        d1 = _dt.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "error": "Format tanggal harus YYYY-MM-DD"}

    uname = (username or "").strip().lower()
    days = []
    cur = d0
    while cur <= d1:
        key = cur.strftime("%Y-%m-%d")
        att = by_date.get(key)
        if att:
            st = _status_label(att.get("status"), att.get("clock_in") or "", att.get("clock_out") or "")
            cin = (att.get("clock_in") or "")[:5]
            cout = (att.get("clock_out") or "")[:5]
            if st.startswith("Izin"):
                cls = "izin"
            elif st.startswith("Alpha"):
                cls = "alpha"
            else:
                cls = "hadir"
            time_s = ("%s-%s" % (cin or "?", cout or "?")) if (cin or cout) else ""
        else:
            st, cls, time_s = "-", "empty", ""
        days.append(
            {
                "date": key,
                "dow": cur.strftime("%a"),
                "day": cur.day,
                "status": st,
                "cls": cls,
                "time": time_s,
            }
        )
        cur += _td(days=1)

    months = []
    mcur = d0.replace(day=1)
    end_m = d1.replace(day=1)
    while mcur <= end_m:
        months.append(mcur)
        if mcur.month == 12:
            mcur = mcur.replace(year=mcur.year + 1, month=1)
        else:
            mcur = mcur.replace(month=mcur.month + 1)

    def month_grid(month_start):
        y, m = month_start.year, month_start.month
        weeks = _cal.monthcalendar(y, m)
        month_name = month_start.strftime("%B %Y")
        cells = []
        for week in weeks:
            row = []
            for day in week:
                if day == 0:
                    row.append({"empty": True})
                    continue
                key = "%04d-%02d-%02d" % (y, m, day)
                if key < date_from or key > date_to:
                    row.append({"empty": True, "day": day, "out": True})
                    continue
                att = by_date.get(key)
                if not att:
                    row.append({"day": day, "cls": "empty", "label": "", "time": ""})
                else:
                    st = _status_label(
                        att.get("status"), att.get("clock_in") or "", att.get("clock_out") or ""
                    )
                    cin = (att.get("clock_in") or "")[:5]
                    cout = (att.get("clock_out") or "")[:5]
                    if st.startswith("Izin"):
                        cls, lab = "izin", "Izin"
                    elif st.startswith("Alpha"):
                        cls, lab = "alpha", "Alpha"
                    else:
                        cls, lab = "hadir", "Hadir"
                    t = ("%s-%s" % (cin or "?", cout or "?")) if (cin or cout) else ""
                    row.append({"day": day, "cls": cls, "label": lab, "time": t})
            cells.append(row)
        return {"title": month_name, "weeks": cells}

    month_blocks = [month_grid(ms) for ms in months]

    month_html = []
    for mb in month_blocks:
        rows_h = []
        for week in mb["weeks"]:
            tds = []
            for c in week:
                if c.get("empty") and not c.get("day"):
                    tds.append('<td class="cell blank"></td>')
                elif c.get("out"):
                    tds.append('<td class="cell out"><div class="d">%s</div></td>' % c["day"])
                else:
                    tds.append(
                        '<td class="cell %s"><div class="d">%s</div>'
                        '<div class="l">%s</div><div class="t">%s</div></td>'
                        % (
                            c.get("cls") or "empty",
                            c.get("day") or "",
                            escape(c.get("label") or ""),
                            escape(c.get("time") or ""),
                        )
                    )
            rows_h.append("<tr>%s</tr>" % "".join(tds))
        month_html.append(
            '<div class="month"><h2>%s</h2><table><thead><tr>'
            "<th>Sen</th><th>Sel</th><th>Rab</th><th>Kam</th><th>Jum</th><th>Sab</th><th>Min</th>"
            "</tr></thead><tbody>%s</tbody></table></div>"
            % (escape(mb["title"]), "".join(rows_h))
        )

    list_rows = []
    for d in days:
        list_rows.append(
            '<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
            % (
                d["cls"],
                escape(d["date"]),
                escape(d["dow"]),
                escape(d["status"]),
                escape(d["time"] or "-"),
            )
        )

    html = f"""<!DOCTYPE html>
<html lang="id"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Kalender Absensi @{escape(uname)} - {escape(app_name or "Staff Management")}</title>
<style>
  :root {{ --bg:#fff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
    --hadir:#dcfce7; --hadir-b:#16a34a; --izin:#fef3c7; --izin-b:#d97706;
    --alpha:#fee2e2; --alpha-b:#dc2626; --empty:#f8fafc; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    margin: 0; padding: 24px; background: var(--bg); color: var(--ink); }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 16px; }}
  .legend {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom: 18px; }}
  .pill {{ font-size: 11px; padding: 4px 10px; border-radius: 999px; border: 1px solid var(--line); }}
  .pill.hadir {{ background: var(--hadir); border-color: var(--hadir-b); color: #166534; }}
  .pill.izin {{ background: var(--izin); border-color: var(--izin-b); color: #92400e; }}
  .pill.alpha {{ background: var(--alpha); border-color: var(--alpha-b); color: #991b1b; }}
  .pill.empty {{ background: var(--empty); color: var(--muted); }}
  .month {{ margin-bottom: 28px; page-break-inside: avoid; }}
  .month h2 {{ font-size: 15px; margin: 0 0 8px; }}
  table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  th {{ font-size: 11px; color: var(--muted); font-weight: 600; padding: 6px; border-bottom: 1px solid var(--line); }}
  td.cell {{ border: 1px solid var(--line); height: 72px; vertical-align: top; padding: 6px; }}
  td.blank {{ background: #fafafa; }}
  td.out {{ background: #fafafa; color: #cbd5e1; }}
  td.hadir {{ background: var(--hadir); }}
  td.izin {{ background: var(--izin); }}
  td.alpha {{ background: var(--alpha); }}
  td.empty {{ background: var(--empty); }}
  .d {{ font-size: 12px; font-weight: 700; }}
  .l {{ font-size: 10px; margin-top: 4px; font-weight: 600; }}
  .t {{ font-size: 10px; color: var(--muted); margin-top: 2px; }}
  .list {{ margin-top: 24px; page-break-inside: avoid; }}
  .list table td, .list table th {{ border: 1px solid var(--line); padding: 6px 8px; font-size: 12px; height: auto; text-align: left; }}
  .list tr.hadir td:nth-child(3) {{ color: #166534; font-weight: 600; }}
  .list tr.izin td:nth-child(3) {{ color: #92400e; font-weight: 600; }}
  .list tr.alpha td:nth-child(3) {{ color: #991b1b; font-weight: 600; }}
  .actions {{ margin: 0 0 16px; display:flex; gap:8px; }}
  .actions button {{ border: 1px solid var(--line); background: #0f172a; color: #fff;
    border-radius: 8px; padding: 8px 14px; font-size: 13px; cursor: pointer; }}
  @media print {{
    .actions {{ display: none; }}
    body {{ padding: 8mm; }}
  }}
</style>
</head><body>
  <div class="actions">
    <button onclick="window.print()">Print / Save PDF</button>
  </div>
  <h1>{escape(app_name or "Staff Management")} - Kalender Absensi</h1>
  <div class="sub">@{escape(uname)} · {escape(date_from)} s/d {escape(date_to)} · {len(rows)} hari tercatat</div>
  <div class="legend">
    <span class="pill hadir">Hadir</span>
    <span class="pill izin">Izin</span>
    <span class="pill alpha">Alpha</span>
    <span class="pill empty">Kosong</span>
  </div>
  {''.join(month_html)}
  <div class="list">
    <h2 style="font-size:15px;margin:0 0 8px">Ringkasan harian</h2>
    <table>
      <thead><tr><th>Tanggal</th><th>Hari</th><th>Status</th><th>Jam</th></tr></thead>
      <tbody>
        {''.join(list_rows) if list_rows else '<tr><td colspan="4">Belum ada data</td></tr>'}
      </tbody>
    </table>
  </div>
  <p class="sub" style="margin-top:20px">Screenshot-ready · light theme · print-friendly</p>
</body></html>"""

    return {
        "success": True,
        "html": html,
        "meta": meta,
        "count": len(rows),
        "filename": "kalender_%s_%s_%s.html" % (uname, date_from, date_to),
    }
