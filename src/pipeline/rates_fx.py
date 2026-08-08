"""
Rates & FX snapshot helpers.
International 10Y yields are static/periodic snapshots (no live scrape required).
"""

# Snapshot of major 10Y yields (update periodically from WSJ or other public sources)
# Values as of recent WSJ browse (Aug 2026)
INTL_10Y = {
    "US": 4.651,
    "Germany": 3.148,
    "UK": 4.927,
    "Japan": 2.802,
    "Australia": 4.993,
    "China": 1.718,
    "France": 3.918,
    "Italy": 3.897,
}

def rate_differentials():
    us = INTL_10Y["US"]
    diffs = {}
    for k, v in INTL_10Y.items():
        if k == "US":
            continue
        diffs[f"US-{k}"] = round(us - v, 3)
    return diffs

def rates_fx_summary():
    diffs = rate_differentials()
    return {
        "intl_10y": INTL_10Y,
        "differentials": diffs,
        "as_of": "2026-08-07 (WSJ snapshot)",
        "note": "Rate differentials drive FX and capital flow signals. Positive US-Germany / US-Japan = USD support via carry / relative yields."
    }
