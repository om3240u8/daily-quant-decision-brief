"""
VIX term structure + commodity roll helpers.
VIX data from public term-structure sites (snapshot + structure).
Commodity roll via yfinance futures where available.
"""

from datetime import datetime
from typing import Dict, Any, List
import yfinance as yf
import pandas as pd
import numpy as np

# ----------------------------------------------------------
# VIX Term Structure (snapshot from public sources e.g. vixstructure / VIXCentral style)
# Update periodically. Values approximate recent market.
# ----------------------------------------------------------
VIX_CURVE_SNAPSHOT = {
    "as_of": "2026-08-07/08 (public term-structure sources)",
    "spot_vix": 16.18,
    "contracts": [
        {"month": "Aug 2026", "expiry": "2026-08-19", "last": 17.85, "contango_vs_prev": 0.0},
        {"month": "Sep 2026", "expiry": "2026-09-16", "last": 19.08, "contango_vs_prev": 6.87},
        {"month": "Oct 2026", "expiry": "2026-10-21", "last": 20.16, "contango_vs_prev": 5.45},
        {"month": "Nov 2026", "expiry": "2026-11-18", "last": 20.62, "contango_vs_prev": 2.11},
        {"month": "Dec 2026", "expiry": "2026-12-16", "last": 20.72, "contango_vs_prev": 0.72},
        {"month": "Jan 2027", "expiry": "2027-01-20", "last": 21.71, "contango_vs_prev": 4.56},
    ],
    "front_vs_second_contango_pct": 6.87,
    "total_contango_pct": 25.79,
    "regime": "Contango",
}


def vix_term_structure() -> Dict[str, Any]:
    """Return current VIX futures term structure snapshot + derived metrics."""
    c = VIX_CURVE_SNAPSHOT
    front = c["contracts"][0]["last"]
    second = c["contracts"][1]["last"] if len(c["contracts"]) > 1 else None
    spot = c["spot_vix"]
    
    # Simple signals
    front_vs_spot = (front / spot - 1) * 100 if spot else None
    regime = c["regime"]
    if second and front > second:
        regime = "Backwardation"
    elif c["front_vs_second_contango_pct"] > 5:
        regime = "Steep Contango"
    elif c["front_vs_second_contango_pct"] > 0:
        regime = "Contango"
    
    interp = ""
    if regime in ("Contango", "Steep Contango"):
        interp = (f"VIX futures in {regime.lower()} (front vs second +{c['front_vs_second_contango_pct']:.1f}%). "
                  "Typical of calm markets; short-vol / roll-down strategies historically favoured, "
                  "but vulnerable to sudden spikes that invert the curve.")
    else:
        interp = (f"VIX futures showing {regime}. Backwardation often accompanies stress or "
                  "elevated near-term risk premium.")
    
    return {
        "spot_vix": spot,
        "front": front,
        "second": second,
        "front_vs_second_pct": c["front_vs_second_contango_pct"],
        "total_contango_pct": c["total_contango_pct"],
        "regime": regime,
        "contracts": c["contracts"],
        "as_of": c["as_of"],
        "interpretation": interp,
        "front_vs_spot_pct": round(front_vs_spot, 2) if front_vs_spot else None,
    }


def commodity_roll_signals() -> Dict[str, Any]:
    """
    Simple commodity roll / curve signals using yfinance continuous futures.
    Positive roll yield ≈ backwardation (beneficial for long holders).
    """
    # Continuous front-month proxies
    symbols = {
        "WTI": "CL=F",
        "Gold": "GC=F",
        "Copper": "HG=F",
        "Natural Gas": "NG=F",
    }
    
    results = {}
    for name, ticker in symbols.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="3mo")
            if hist.empty or len(hist) < 5:
                continue
            last = float(hist["Close"].iloc[-1])
            # Rough 1M change as momentum proxy; true roll requires specific contract months
            ret_1m = float(hist["Close"].iloc[-1] / hist["Close"].iloc[-22] - 1) if len(hist) > 22 else None
            results[name] = {
                "ticker": ticker,
                "last": round(last, 3),
                "ret_1m": round(ret_1m, 4) if ret_1m is not None else None,
            }
        except Exception:
            continue
    
    # Interpretation note
    note = ("True roll yield requires specific nearby vs deferred contract prices. "
            "Here we show front-month continuous futures levels and recent momentum as a practical proxy. "
            "Backwardation (upward-sloping spot-to-futures) historically supports long commodity exposure.")
    
    return {
        "contracts": results,
        "note": note,
        "as_of": datetime.now().strftime("%Y-%m-%d"),
    }


def get_term_structure_bundle() -> Dict[str, Any]:
    return {
        "vix": vix_term_structure(),
        "commodities": commodity_roll_signals(),
    }
