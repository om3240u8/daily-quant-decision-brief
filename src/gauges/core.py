"""
Core risk gauges for the Daily Quant Decision Brief.
All calculations are transparent and use public data only.
Yield curve sourced from WSJ.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from src.pipeline.wsj_yields import get_yield_curve
from src.gauges.liquidity import liquidity_gauge


def risk_on_off(prices: pd.DataFrame, returns: pd.DataFrame = None) -> Dict[str, Any]:
    """
    Simple Risk-On / Risk-Off composite.
    Positive = Risk-On.
    Components: equity momentum, credit (HY vs IG), inverted VIX, BTC.
    """
    score = 0.0
    components = {}
    
    # 1. Equity momentum (SPY 1M + 3M)
    if "SPY" in prices.columns:
        spy = prices["SPY"].dropna()
        m1 = spy.iloc[-1] / spy.iloc[-22] - 1 if len(spy) > 22 else 0
        m3 = spy.iloc[-1] / spy.iloc[-66] - 1 if len(spy) > 66 else 0
        eq_mom = 0.5 * m1 + 0.5 * m3
        components["equity_momentum"] = round(eq_mom, 4)
        score += np.tanh(eq_mom * 10)
    
    # 2. Credit risk appetite (HYG / LQD)
    if "HYG" in prices.columns and "LQD" in prices.columns:
        ratio = (prices["HYG"] / prices["LQD"]).dropna()
        if len(ratio) > 22:
            chg = ratio.iloc[-1] / ratio.iloc[-22] - 1
            components["credit_appetite"] = round(chg, 4)
            score += np.tanh(chg * 15)
    
    # 3. Inverted VIX
    if "^VIX" in prices.columns:
        vix = prices["^VIX"].dropna()
        if len(vix) > 5:
            vix_lvl = float(vix.iloc[-1])
            components["vix_level"] = round(vix_lvl, 2)
            vix_score = (25 - vix_lvl) / 15
            score += np.clip(vix_score, -1.5, 1.5)
    
    # 4. BTC high-beta
    if "BTC-USD" in prices.columns:
        btc = prices["BTC-USD"].dropna()
        if len(btc) > 22:
            btc_m = btc.iloc[-1] / btc.iloc[-22] - 1
            components["btc_momentum"] = round(btc_m, 4)
            score += np.tanh(btc_m * 5) * 0.5
    
    final = float(np.clip(score / 2.5, -2, 2))
    
    return {
        "score": round(final, 3),
        "label": "Risk-On" if final > 0.4 else ("Risk-Off" if final < -0.4 else "Neutral"),
        "components": components,
        "interpretation": _risk_interp(final)
    }


def _risk_interp(score: float) -> str:
    if score > 1.0:
        return "Strong risk-on regime. High-beta assets preferred."
    if score > 0.4:
        return "Mild risk-on. Equity and credit appetite present."
    if score > -0.4:
        return "Neutral / mixed signals across risk assets."
    if score > -1.0:
        return "Mild risk-off. Defensive positioning favored."
    return "Strong risk-off. Flight to quality dominant."


def yield_curve_gauge() -> Dict[str, Any]:
    """
    Yield curve from WSJ. Returns level, key spreads, and regime label.
    """
    curve = get_yield_curve()
    yields = curve.get("yields", {})
    spreads = curve.get("spreads", {})
    
    s10_2 = spreads.get("10y2y", np.nan)
    s10_3m = spreads.get("10y3m", np.nan)
    
    if pd.isna(s10_2):
        label = "N/A"
        interp = "Yield curve data unavailable."
    elif s10_2 > 0.50:
        label = "Steep"
        interp = f"10Y-2Y at +{s10_2:.2f}% — curve steep, term premium / growth expectations elevated."
    elif s10_2 > 0.0:
        label = "Mildly Steep"
        interp = f"10Y-2Y at +{s10_2:.2f}% — mildly positive slope."
    elif s10_2 > -0.50:
        label = "Flat / Mild Inversion"
        interp = f"10Y-2Y at {s10_2:.2f}% — flat to mildly inverted (classic late-cycle signal)."
    else:
        label = "Deeply Inverted"
        interp = f"10Y-2Y at {s10_2:.2f}% — deep inversion, historically strong recession warning."
    
    return {
        "score": float(s10_2) if not pd.isna(s10_2) else None,
        "label": label,
        "components": {
            "yields": yields,
            "spreads": spreads,
            "as_of": curve.get("as_of"),
            "source": curve.get("source")
        },
        "interpretation": interp
    }


def vol_risk_premium(prices: pd.DataFrame) -> Dict[str, Any]:
    """VIX – 21-day realized vol of SPY."""
    result = {"score": None, "label": "N/A", "components": {}, "interpretation": ""}
    
    if "^VIX" not in prices.columns or "SPY" not in prices.columns:
        return result
    
    vix = prices["^VIX"].dropna()
    spy_ret = prices["SPY"].pct_change().dropna()
    
    if len(vix) < 5 or len(spy_ret) < 22:
        return result
    
    current_vix = float(vix.iloc[-1])
    realized_21d = float(spy_ret.iloc[-21:].std() * np.sqrt(252) * 100)
    vrp = current_vix - realized_21d
    
    result["components"] = {
        "vix": round(current_vix, 2),
        "realized_21d": round(realized_21d, 2),
        "vrp": round(vrp, 2)
    }
    result["score"] = round(vrp, 2)
    
    if vrp > 5:
        result["label"] = "Elevated VRP"
        result["interpretation"] = "Implied vol rich vs realized — vol sellers historically compensated."
    elif vrp > 0:
        result["label"] = "Normal VRP"
        result["interpretation"] = "Typical positive volatility risk premium."
    else:
        result["label"] = "Negative VRP"
        result["interpretation"] = "Implied below realized — unusual; caution for short-vol strategies."
    
    return result


def credit_gauge(prices: pd.DataFrame) -> Dict[str, Any]:
    """Simple credit risk appetite from HYG vs LQD price ratio."""
    result = {"score": None, "label": "N/A", "components": {}, "interpretation": ""}
    if "HYG" not in prices.columns or "LQD" not in prices.columns:
        return result
    
    ratio = (prices["HYG"] / prices["LQD"]).dropna()
    if len(ratio) < 22:
        return result
    
    current = float(ratio.iloc[-1])
    chg_1m = current / float(ratio.iloc[-22]) - 1
    result["components"] = {"hyg_lqd_ratio": round(current, 4), "chg_1m": round(chg_1m, 4)}
    result["score"] = round(chg_1m, 4)
    
    if chg_1m > 0.01:
        result["label"] = "Risk-On Credit"
        result["interpretation"] = "HY outperforming IG — credit risk appetite improving."
    elif chg_1m < -0.01:
        result["label"] = "Risk-Off Credit"
        result["interpretation"] = "HY underperforming IG — credit stress rising."
    else:
        result["label"] = "Neutral Credit"
        result["interpretation"] = "HY/IG relative performance stable."
    return result


def run_all_gauges(prices: pd.DataFrame) -> Dict[str, Any]:
    return {
        "risk_on_off": risk_on_off(prices),
        "yield_curve": yield_curve_gauge(),
        "vol_risk_premium": vol_risk_premium(prices),
        "credit": credit_gauge(prices),
        "liquidity": liquidity_gauge(prices),
        "generated_at": pd.Timestamp.now().isoformat()
    }
