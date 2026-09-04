"""
High-impact event calendar.
Dates are official release/meeting schedule (not market prices).
Refresh after each FOMC / when BLS-BEA calendars roll.
"""

from datetime import datetime, timedelta

EVENTS = [
    {
        "date": "2026-09-04",
        "event": "US Employment Report (NFP)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · first binary that can reopen Sep FOMC basis",
    },
    {
        "date": "2026-09-07",
        "event": "US Labor Day (markets closed)",
        "region": "US",
        "impact": "Med",
        "notes": "NYSE/NASDAQ closed",
    },
    {
        "date": "2026-09-10",
        "event": "US PPI + ECB decision window",
        "region": "US/EU",
        "impact": "Med-High",
        "notes": "PPI 08:30 ET; watch ECB same week",
    },
    {
        "date": "2026-09-11",
        "event": "US CPI (August)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · last major print before 16 Sep FOMC",
    },
    {
        "date": "2026-09-16",
        "event": "FOMC decision + SEP / presser",
        "region": "US",
        "impact": "High",
        "notes": "14:00 ET statement · Warsh presser 14:30 · SEP meeting",
    },
    {
        "date": "2026-09-30",
        "event": "US PCE / GDP 3rd est.",
        "region": "US",
        "impact": "High",
        "notes": "Fed preferred inflation gauge",
    },
    {
        "date": "2026-10-02",
        "event": "US Employment Report (NFP)",
        "region": "US",
        "impact": "High",
        "notes": "Post-Sep FOMC labor print",
    },
    {
        "date": "2026-10-14",
        "event": "US CPI (September)",
        "region": "US",
        "impact": "High",
        "notes": "",
    },
    {
        "date": "2026-10-28",
        "event": "FOMC decision",
        "region": "US",
        "impact": "High",
        "notes": "14:00 ET · no SEP",
    },
    {
        "date": "2026-12-09",
        "event": "FOMC decision + SEP",
        "region": "US",
        "impact": "High",
        "notes": "Year-end path / dots",
    },
]


def get_upcoming_events(days_ahead: int = 30) -> list:
    today = datetime.now().date()
    upcoming = []
    for e in EVENTS:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
            if today <= d <= today + timedelta(days=days_ahead):
                upcoming.append(e)
        except Exception:
            continue
    return sorted(upcoming, key=lambda x: x["date"])


def events_to_html(events: list) -> str:
    if not events:
        return "<p style='color:var(--muted)'>No high-impact events in the immediate window.</p>"

    rows = ""
    for e in events:
        impact_color = "#f85149" if e["impact"] == "High" else "#d29922"
        rows += f"""
        <tr>
          <td>{e['date'][5:]}</td>
          <td>{e['event']}</td>
          <td>{e['region']}</td>
          <td style=\"color:{impact_color};font-weight:600\">{e['impact']}</td>
          <td style=\"color:var(--muted);font-size:0.8rem\">{e.get('notes','')}</td>
        </tr>"""
    return f"""
    <div class=\"table-scroll\">
    <table>
      <thead>
        <tr><th>Date</th><th>Event</th><th>Region</th><th>Impact</th><th>Notes</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    """
