"""
High-impact event calendar and narrative drivers.
Weighted by typical market impact. Structure allows easy daily update.
"""

from datetime import datetime, timedelta

# Near-term high-impact events (manually curated for quality; expand with scrapers later)
# Format: date, event, region, expected impact (High/Med), notes

EVENTS = [
    {
        "date": "2026-08-12",
        "event": "US CPI (July)",
        "region": "US",
        "impact": "High",
        "notes": "Key inflation print for Fed path pricing"
    },
    {
        "date": "2026-08-14",
        "event": "US Retail Sales",
        "region": "US",
        "impact": "Med",
        "notes": "Consumption momentum"
    },
    {
        "date": "2026-08-15",
        "event": "US Industrial Production / Capacity Util.",
        "region": "US",
        "impact": "Med",
        "notes": ""
    },
    {
        "date": "2026-08-20",
        "event": "FOMC Minutes",
        "region": "US",
        "impact": "High",
        "notes": "Tone on rates and balance sheet"
    },
    {
        "date": "2026-08-22",
        "event": "Jackson Hole Symposium begins",
        "region": "US",
        "impact": "High",
        "notes": "Fed Chair speech historically market-moving"
    },
    {
        "date": "2026-08-27",
        "event": "US GDP (2nd estimate) / Pending Home Sales",
        "region": "US",
        "impact": "Med",
        "notes": ""
    },
    {
        "date": "2026-09-01",
        "event": "ISM Manufacturing",
        "region": "US",
        "impact": "Med-High",
        "notes": "Growth pulse"
    },
    {
        "date": "2026-09-05",
        "event": "US Employment Report (NFP)",
        "region": "US",
        "impact": "High",
        "notes": "Critical for Fed"
    },
    # International placeholders – expand as needed
    {
        "date": "2026-08-19",
        "event": "RBA Minutes / Australia data cluster",
        "region": "AU",
        "impact": "Med",
        "notes": ""
    },
    {
        "date": "2026-08-21",
        "event": "ECB speakers / Eurozone data",
        "region": "EU",
        "impact": "Med",
        "notes": "Watch for policy divergence vs Fed"
    },
]

def get_upcoming_events(days_ahead: int = 30) -> list:
    """Return events in the next N days, sorted."""
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
          <td style="color:{impact_color};font-weight:600">{e['impact']}</td>
          <td style="color:var(--muted);font-size:0.8rem">{e.get('notes','')}</td>
        </tr>"""
    return f"""
    <table>
      <thead>
        <tr><th>Date</th><th>Event</th><th>Region</th><th>Impact</th><th>Notes</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    """
