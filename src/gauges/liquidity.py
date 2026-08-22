"""
Quantitative Liquidity / Funding gauge.
Both funding liquidity and market liquidity proxies.
Includes inverted USD strength as a global funding / liquidity channel.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


def amihud_illiquidity(prices: pd.Series, volume: pd.Series = None, window: int = 21) -> float:
    """
    Simple Amihud (2002) style: average |return| / volume.
    If volume not available, fall back to |return| volatility as rough proxy.
    """
    rets = prices.pct_change().dropna()
    if volume is not None and len(volume.dropna()) > window:
        common = rets.index.intersection(volume.dropna().index)
        if len(common) > window:
            r = rets.loc[common].iloc[-window:]
            v = volume.loc[common].iloc[-window:]
            v = v.replace(0, np.nan)
            illiq = (r.abs() / v).mean()
            return float(illiq) if not np.isnan(illiq) else None
    if len(rets) > window:
        return float(rets.iloc[-window:].std() * np.sqrt(252))
    return None


def _usd_strength_component(prices: pd.DataFrame) -> Tuple[float, Dict[str, Any]]:
    """
    Inverted USD strength as liquidity / funding stress proxy.
    Stronger USD → tighter global USD funding → lower liquidity score.
    Primary horizon: 63d (≈3M) momentum; also report 21d for diagnostics.
    Prefer UUP; fall back to DX-Y.NYB.
    Returns (contribution_to_score, components_dict)
    """
    ticker = None
    for cand in ("UUP", "DX-Y.NYB"):
        if cand in prices.columns and prices[cand].dropna().shape[0] > 70:
            ticker = cand
            break
    if ticker is None:
        return 0.0, {}

    s = prices[ticker].dropna()
    components: Dict[str, Any] = {"usd_ticker": ticker}
    contrib = 0.0

    # 63d primary
    if len(s) > 63:
        ret_63 = float(s.iloc[-1] / s.iloc[-64] - 1)
        components["usd_ret_63d"] = round(ret_63, 4)
        # invert: positive USD return → negative liquidity contribution
        contrib += float(np.tanh(-ret_63 * 8)) * 0.9

    # 21d diagnostic / robustness
    if len(s) > 21:
        ret_21 = float(s.iloc[-1] / s.iloc[-22] - 1)
        components["usd_ret_21d"] = round(ret_21, 4)
        contrib += float(np.tanh(-ret_21 * 12)) * 0.35

    return contrib, components


def liquidity_gauge(prices: pd.DataFrame, volumes: pd.DataFrame = None) -> Dict[str, Any]:
    """
    Composite liquidity score.
    Higher score = better / more abundant liquidity.

    Components:
      1. Market liquidity (SPY Amihud / realized-vol proxy)
      2. Credit market functioning (HYG realized vol)
      3. Short-rate pressure (^IRX)
      4. Inverted USD strength (UUP / DXY) — global funding channel
    """
    components: Dict[str, Any] = {}
    score = 0.0
    n = 0

    # 1. Market liquidity via SPY
    if "SPY" in prices.columns:
        spy_illiq = amihud_illiquidity(prices["SPY"])
        if spy_illiq is not None:
            components["spy_illiquidity_proxy"] = round(spy_illiq, 6)
            if spy_illiq < 0.15:
                score += 0.8
            elif spy_illiq < 0.22:
                score += 0.3
            else:
                score -= 0.6
            n += 1

    # 2. Credit market functioning
    if "HYG" in prices.columns:
        hyg_vol = prices["HYG"].pct_change().iloc[-21:].std() * np.sqrt(252)
        components["hyg_realized_vol"] = round(float(hyg_vol), 4) if not np.isnan(hyg_vol) else None
        if hyg_vol < 0.08:
            score += 0.5
        elif hyg_vol > 0.15:
            score -= 0.7
        n += 1

    # 3. Short-rate / funding proxy
    if "^IRX" in prices.columns:
        irx = prices["^IRX"].dropna()
        if len(irx) > 5:
            level = float(irx.iloc[-1])
            chg = float(irx.iloc[-1] - irx.iloc[-6]) if len(irx) > 6 else 0.0
            components["tbill_proxy"] = round(level, 3)
            components["tbill_5d_chg"] = round(chg, 3)
            if chg > 0.15:
                score -= 0.4
            elif chg < -0.10:
                score += 0.2
            n += 1

    # 4. Inverted USD strength (funding / global liquidity)
    usd_contrib, usd_comp = _usd_strength_component(prices)
    if usd_comp:
        components.update(usd_comp)
        score += usd_contrib
        n += 1

    if n == 0:
        return {
            "score": None,
            "label": "N/A",
            "components": {},
            "interpretation": "Insufficient data for liquidity gauge."
        }

    final = float(np.clip(score / max(n, 1), -1.5, 1.5))

    if final > 0.5:
        label = "Abundant"
        interp = "Market and funding conditions appear supportive. Low stress signals."
    elif final > 0:
        label = "Normal"
        interp = "Liquidity conditions within normal range."
    elif final > -0.6:
        label = "Tightening"
        interp = "Some signs of reduced market liquidity or funding pressure (incl. USD strength)."
    else:
        label = "Stressed"
        interp = ("Elevated illiquidity / funding stress signals "
                  "(USD strength, credit or market liquidity). "
                  "Caution on crowded or high-beta positions.")

    return {
        "score": round(final, 3),
        "label": label,
        "components": components,
        "interpretation": interp
    }
