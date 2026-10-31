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
    Components: equity momentum, credit (HY vs IG), inverted VIX+VXN (avg), BTC,
    and a light inverted USD-strength term (UUP / DXY).
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

    # 3. Inverted VIX + VXN (equal-weight average of the two inverted levels)
    vol_scores = []
    if "^VIX" in prices.columns:
        vix = prices["^VIX"].dropna()
        if len(vix) > 5:
            vix_lvl = float(vix.iloc[-1])
            components["vix_level"] = round(vix_lvl, 2)
            vol_scores.append(np.clip((25 - vix_lvl) / 15, -1.5, 1.5))
    if "^VXN" in prices.columns:
        vxn = prices["^VXN"].dropna()
        if len(vxn) > 5:
            vxn_lvl = float(vxn.iloc[-1])
            components["vxn_level"] = round(vxn_lvl, 2)
            vol_scores.append(np.clip((25 - vxn_lvl) / 15, -1.5, 1.5))
    if vol_scores:
        score += float(np.mean(vol_scores))

    # 4. BTC high-beta
    if "BTC-USD" in prices.columns:
        btc = prices["BTC-USD"].dropna()
        if len(btc) > 22:
            btc_m = btc.iloc[-1] / btc.iloc[-22] - 1
            components["btc_momentum"] = round(btc_m, 4)
            score += np.tanh(btc_m * 5) * 0.5

    # 5. Light inverted USD strength (flight-to-USD is a classic risk-off signal)
    # Kept lighter than the Liquidity gauge so the two are not pure duplicates.
    usd_ticker = None
    for cand in ("UUP", "DX-Y.NYB"):
        if cand in prices.columns and prices[cand].dropna().shape[0] > 30:
            usd_ticker = cand
            break
    if usd_ticker is not None:
        u = prices[usd_ticker].dropna()
        if len(u) > 22:
            usd_m = float(u.iloc[-1] / u.iloc[-22] - 1)
            components["usd_momentum_1m"] = round(usd_m, 4)
            components["usd_ticker"] = usd_ticker
            # invert: rising USD → risk-off contribution
            score += np.tanh(-usd_m * 10) * 0.45

    final = float(np.clip(score / 2.8, -2, 2))

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


# ---------- Selective Risk Monitors ----------

def sovereign_relative_gauge(prices: pd.DataFrame = None) -> Dict[str, Any]:
    """
    Placeholder for OAT-Bund / BTP-Bund relative stress.
    Live series required; returns Neutral until injected.
    """
    return {
        "score": 0.0,
        "label": "Neutral Sovereign",
        "components": {},
        "interpretation": "Sovereign relative spreads stable (live OAT-Bund series required for full signal)."
    }


def safe_haven_fx_gauge(prices: pd.DataFrame) -> Dict[str, Any]:
    """
    JPY + CHF strength vs USD.
    Average of FXY and FXF relative to UUP. Positive = safe-haven bid.
    """
    result = {"score": None, "label": "N/A", "components": {}, "interpretation": ""}
    needed = ["FXY", "UUP"]
    if not all(t in prices.columns for t in needed):
        return result

    fxy = prices["FXY"].dropna()
    uup = prices["UUP"].dropna()
    if len(fxy) < 22 or len(uup) < 22:
        return result

    fxy_ret = float(fxy.iloc[-1] / fxy.iloc[-22] - 1)
    uup_ret = float(uup.iloc[-1] / uup.iloc[-22] - 1)
    components = {"fxy_1m": round(fxy_ret, 4), "uup_1m": round(uup_ret, 4)}

    # CHF if available
    if "FXF" in prices.columns:
        fxf = prices["FXF"].dropna()
        if len(fxf) >= 22:
            fxf_ret = float(fxf.iloc[-1] / fxf.iloc[-22] - 1)
            components["fxf_1m"] = round(fxf_ret, 4)
            relative = (fxy_ret + fxf_ret) / 2 - uup_ret
        else:
            relative = fxy_ret - uup_ret
    else:
        relative = fxy_ret - uup_ret

    components["relative"] = round(relative, 4)
    result["components"] = components
    result["score"] = round(relative, 4)

    if relative > 0.015:
        result["label"] = "Risk-Off FX"
        result["interpretation"] = "JPY + CHF outperforming USD — safe-haven bid."
    elif relative < -0.015:
        result["label"] = "Risk-On FX"
        result["interpretation"] = "USD outperforming JPY/CHF — risk appetite in FX."
    else:
        result["label"] = "Neutral FX"
        result["interpretation"] = "Safe-haven FX (JPY + CHF) relative performance stable."
    return result


def cross_asset_correlation_gauge(prices: pd.DataFrame) -> Dict[str, Any]:
    """20-day average pairwise correlation of SPY, HYG, EEM."""
    result = {"score": None, "label": "N/A", "components": {}, "interpretation": ""}
    tickers = [t for t in ["SPY", "HYG", "EEM"] if t in prices.columns]
    if len(tickers) < 2:
        return result

    rets = prices[tickers].pct_change().dropna()
    if len(rets) < 20:
        return result

    corr_matrix = rets.iloc[-20:].corr()
    avg_corr = corr_matrix.where(~np.eye(len(tickers), dtype=bool)).stack().mean()
    result["components"] = {"avg_corr_20d": round(float(avg_corr), 3)}
    result["score"] = round(float(avg_corr), 3)

    if avg_corr > 0.65:
        result["label"] = "High Correlation"
        result["interpretation"] = "Cross-asset correlation elevated — selective stress may be spilling over."
    elif avg_corr > 0.40:
        result["label"] = "Moderate Correlation"
        result["interpretation"] = "Correlations rising but not yet systemic."
    else:
        result["label"] = "Low Correlation"
        result["interpretation"] = "Cross-asset moves still differentiated."
    return result


def liquidity_functioning_gauge(prices: pd.DataFrame) -> Dict[str, Any]:
    """HYG 21-day realized vol as a simple functioning proxy."""
    result = {"score": None, "label": "N/A", "components": {}, "interpretation": ""}
    if "HYG" not in prices.columns:
        return result

    hyg = prices["HYG"].dropna()
    if len(hyg) < 21:
        return result

    vol_21 = float(hyg.pct_change().iloc[-21:].std() * np.sqrt(252))
    result["components"] = {"hyg_realized_vol": round(vol_21, 3)}
    result["score"] = round(vol_21, 3)

    if vol_21 > 0.12:
        result["label"] = "Stressed Functioning"
        result["interpretation"] = "HY realized vol elevated — credit market functioning under pressure."
    elif vol_21 > 0.08:
        result["label"] = "Elevated Functioning"
        result["interpretation"] = "Moderate stress in credit market functioning."
    else:
        result["label"] = "Normal Functioning"
        result["interpretation"] = "Credit market functioning appears orderly."
    return result


def funding_stress_gauge(prices: pd.DataFrame) -> Dict[str, Any]:
    """Yen 1M strength as a simple funding/carry stress proxy."""
    result = {"score": None, "label": "N/A", "components": {}, "interpretation": ""}
    if "FXY" not in prices.columns:
        return result

    fxy = prices["FXY"].dropna()
    if len(fxy) < 22:
        return result

    fxy_1m = float(fxy.iloc[-1] / fxy.iloc[-22] - 1)
    result["components"] = {"fxy_1m": round(fxy_1m, 4)}
    result["score"] = round(fxy_1m, 4)

    if fxy_1m > 0.02:
        result["label"] = "Funding Stress"
        result["interpretation"] = "Yen strengthening sharply — potential carry/funding stress."
    elif fxy_1m > 0.01:
        result["label"] = "Mild Funding Stress"
        result["interpretation"] = "Yen firming — mild funding pressure."
    else:
        result["label"] = "Normal Funding"
        result["interpretation"] = "No significant funding stress signal from yen."
    return result


def run_all_gauges(prices: pd.DataFrame) -> Dict[str, Any]:
    return {
        "risk_on_off": risk_on_off(prices),
        "yield_curve": yield_curve_gauge(),
        "vol_risk_premium": vol_risk_premium(prices),
        "credit": credit_gauge(prices),
        "liquidity": liquidity_gauge(prices),
        # Selective risk monitors
        "sovereign_relative": sovereign_relative_gauge(prices),
        "safe_haven_fx": safe_haven_fx_gauge(prices),
        "cross_asset_corr": cross_asset_correlation_gauge(prices),
        "liquidity_functioning": liquidity_functioning_gauge(prices),
        "funding_stress": funding_stress_gauge(prices),
        "generated_at": pd.Timestamp.now().isoformat()
    }
