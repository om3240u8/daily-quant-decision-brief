"""
High-impact event calendar.
Dates are official release/meeting schedule (not market prices).
Refresh after each FOMC / when BLS-BEA calendars roll.
Last refreshed: 2026-10-16 from BLS / BEA / Fed official schedules.
"""

from datetime import datetime, timedelta

EVENTS = [
    {
        "date": "2026-10-28",
        "event": "FOMC decision",
        "region": "US",
        "impact": "High",
        "notes": "14:00 ET · no SEP · Warsh presser",
    },
    {
        "date": "2026-10-29",
        "event": "GDP Advance (Q3) + PCE (Sep)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · BEA · Fed preferred inflation + growth",
    },
    {
        "date": "2026-10-30",
        "event": "Employment Cost Index (Q3)",
        "region": "US",
        "impact": "Med-High",
        "notes": "08:30 ET · BLS · wage pressure gauge",
    },
    {
        "date": "2026-11-03",
        "event": "JOLTS (Sep)",
        "region": "US",
        "impact": "Med-High",
        "notes": "10:00 ET · BLS · job openings / turnover",
    },
    {
        "date": "2026-11-06",
        "event": "US Employment Report (NFP, Oct)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · BLS · post-Oct FOMC labor print",
    },
    {
        "date": "2026-11-10",
        "event": "US CPI (October)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · BLS · next major inflation print",
    },
    {
        "date": "2026-11-13",
        "event": "US PPI (October)",
        "region": "US",
        "impact": "Med-High",
        "notes": "08:30 ET · BLS",
    },
    {
        "date": "2026-11-17",
        "event": "Advance Retail Sales (Oct)",
        "region": "US",
        "impact": "Med",
        "notes": "08:30 ET · Census",
    },
    {
        "date": "2026-11-18",
        "event": "FOMC Minutes (Oct 27-28)",
        "region": "US",
        "impact": "Med",
        "notes": "14:00 ET · Fed",
    },
    {
        "date": "2026-11-25",
        "event": "GDP 2nd (Q3) + PCE (Oct)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · BEA",
    },
    {
        "date": "2026-12-04",
        "event": "US Employment Report (NFP, Nov)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · BLS",
    },
    {
        "date": "2026-12-09",
        "event": "FOMC decision + SEP",
        "region": "US",
        "impact": "High",
        "notes": "14:00 ET · year-end path / dots",
    },
    {
        "date": "2026-12-10",
        "event": "US CPI (November)",
        "region": "US",
        "impact": "High",
        "notes": "08:30 ET · BLS",
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
          <td style='color:{impact_color};font-weight:600'>{e['impact']}</td>
          <td style='color:var(--muted);font-size:0.8rem'>{e.get('notes','')}</td>
        </tr>"""
    return f"""
    <div class='table-scroll'>
    <table>
      <thead>
        <tr><th>Date</th><th>Event</th><th>Region</th><th>Impact</th><th>Notes</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    """
