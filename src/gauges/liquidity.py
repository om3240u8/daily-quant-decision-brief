"""
Quantitative Liquidity / Funding gauge.
Both funding liquidity and market liquidity proxies.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any


def amihud_illiquidity(prices: pd.Series, volume: pd.Series = None, window: int = 21) -> float:
    """
    Simple Amihud (2002) style: average |return| / volume.
    If volume not available, fall back to |return| volatility as rough proxy.
    """
    rets = prices.pct_change().dropna()
    if volume is not None and len(volume.dropna()) > window:
        # align
        common = rets.index.intersection(volume.dropna().index)
        if len(common) > window:
            r = rets.loc[common].iloc[-window:]
            v = volume.loc[common].iloc[-window:]
            # avoid div0
            v = v.replace(0, np.nan)
            illiq = (r.abs() / v).mean()
            return float(illiq) if not np.isnan(illiq) else None
    # fallback: realized vol as liquidity stress proxy (higher vol often coincides with worse liquidity)
    if len(rets) > window:
        return float(rets.iloc[-window:].std() * np.sqrt(252))
    return None


def liquidity_gauge(prices: pd.DataFrame, volumes: pd.DataFrame = None) -> Dict[str, Any]:
    """
    Composite liquidity score.
    Higher score = better / more abundant liquidity.
    """
    components = {}
    score = 0.0
    n = 0
    
    # 1. Market liquidity via SPY Amihud-style or vol proxy
    if "SPY" in prices.columns:
        spy_illiq = amihud_illiquidity(prices["SPY"])
        if spy_illiq is not None:
            components["spy_illiquidity_proxy"] = round(spy_illiq, 6)
            # lower illiquidity = better → invert and scale
            # typical daily Amihud is very small; we use the vol fallback mostly
            if spy_illiq < 0.15:          # low realized vol regime
                score += 0.8
            elif spy_illiq < 0.22:
                score += 0.3
            else:
                score -= 0.6
            n += 1
    
    # 2. Credit market functioning (HYG volume or relative performance stability)
    if "HYG" in prices.columns:
        hyg_vol = prices["HYG"].pct_change().iloc[-21:].std() * np.sqrt(252)
        components["hyg_realized_vol"] = round(float(hyg_vol), 4) if not np.isnan(hyg_vol) else None
        if hyg_vol < 0.08:
            score += 0.5
        elif hyg_vol > 0.15:
            score -= 0.7
        n += 1
    
    # 3. Simple funding proxy: if we had SOFR we would use it.
    # Placeholder: use short-term rate stability from available T-bill proxy if present
    if "^IRX" in prices.columns:
        irx = prices["^IRX"].dropna()
        if len(irx) > 5:
            # IRX is discount rate; treat level + recent change
            level = float(irx.iloc[-1])
            chg = float(irx.iloc[-1] - irx.iloc[-6]) if len(irx) > 6 else 0
            components["tbill_proxy"] = round(level, 3)
            components["tbill_5d_chg"] = round(chg, 3)
            # rising short rates sharply can signal funding pressure
            if chg > 0.15:
                score -= 0.4
            elif chg < -0.10:
                score += 0.2
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
        interp = "Some signs of reduced market liquidity or funding pressure."
    else:
        label = "Stressed"
        interp = "Elevated illiquidity / funding stress signals. Caution on crowded or high-beta positions."
    
    return {
        "score": round(final, 3),
        "label": label,
        "components": components,
        "interpretation": interp
    }
