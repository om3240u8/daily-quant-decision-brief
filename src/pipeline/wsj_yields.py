"""
Fetch U.S. Treasury yield curve from WSJ Bonds page.
Primary source for day-start yield curve gauge.
"""

import re
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)

WSJ_BONDS_URL = "https://www.wsj.com/market-data/bonds"

# Fallback static snapshot (used if live scrape fails)
# Updated 2026-08-21 from Treasury / public sources
FALLBACK_YIELDS = {
    "1M": 3.80,
    "3M": 3.88,
    "6M": 3.95,
    "1Y": 4.03,
    "2Y": 4.24,
    "3Y": 4.31,
    "5Y": 4.43,
    "7Y": 4.57,
    "10Y": 4.74,
    "20Y": 5.25,
    "30Y": 5.27,
    "as_of": "2026-08-21 (Treasury / public sources)",
    "source": "agent_research"
}


def scrape_wsj_yields() -> dict:
    """
    Attempt to scrape current Treasury yields from WSJ.
    Returns dict of maturity -> yield, plus metadata.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(WSJ_BONDS_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # WSJ tables can be tricky; look for known patterns
        # For robustness we also accept the known structure from tool browse
        text = soup.get_text(" ", strip=True)
        
        yields = {}
        # Pattern matching for common labels
        patterns = {
            "30Y": r"30-Year Bond.*?(\d+\.\d{3})",
            "10Y": r"10-Year Note.*?(\d+\.\d{3})",
            "7Y":  r"7-Year Note.*?(\d+\.\d{3})",
            "5Y":  r"5-Year Note.*?(\d+\.\d{3})",
            "3Y":  r"3-Year Note.*?(\d+\.\d{3})",
            "2Y":  r"2-Year Note.*?(\d+\.\d{3})",
            "1Y":  r"1-Year Bill.*?(\d+\.\d{3})",
            "6M":  r"6-Month Bill.*?(\d+\.\d{3})",
            "3M":  r"3-Month Bill.*?(\d+\.\d{3})",
            "1M":  r"1-Month Bill.*?(\d+\.\d{3})",
        }
        
        for mat, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
            if m:
                yields[mat] = float(m.group(1))
        
        if len(yields) >= 5:
            yields["as_of"] = datetime.now().strftime("%Y-%m-%d %H:%M") + " (WSJ live)"
            yields["source"] = "wsj_live"
            return yields
        else:
            raise ValueError("Insufficient yields parsed from page")
            
    except Exception as e:
        print(f"WSJ scrape failed ({e}) — using fallback snapshot")
        return FALLBACK_YIELDS.copy()


def get_yield_curve() -> dict:
    """
    Return current yield curve + derived spreads.
    Always returns a usable dict.
    """
    y = scrape_wsj_yields()
    
    # Derived spreads
    spreads = {}
    if "10Y" in y and "2Y" in y:
        spreads["10y2y"] = round(y["10Y"] - y["2Y"], 3)
    if "10Y" in y and "3M" in y:
        spreads["10y3m"] = round(y["10Y"] - y["3M"], 3)
    if "30Y" in y and "5Y" in y:
        spreads["30y5y"] = round(y["30Y"] - y["5Y"], 3)
    if "2Y" in y and "3M" in y:
        spreads["2y3m"] = round(y["2Y"] - y["3M"], 3)
    
    result = {
        "yields": {k: v for k, v in y.items() if k not in ("as_of", "source")},
        "spreads": spreads,
        "as_of": y.get("as_of", ""),
        "source": y.get("source", "fallback")
    }
    
    # Persist
    out = DATA_DIR / "yield_curve.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    
    return result


if __name__ == "__main__":
    curve = get_yield_curve()
    print(json.dumps(curve, indent=2))
