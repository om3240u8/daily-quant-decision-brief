"""
Lightweight historical series of core gauges for charts and range bars.
Samples every ~5 trading days to keep generation fast.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple


def _risk_score_at(prices: pd.DataFrame, end_loc: int) -> float:
    """Simplified risk-on/off score using data up to end_loc (inclusive)."""
    score = 0.0
    # Equity mom
    if "SPY" in prices.columns:
        spy = prices["SPY"].iloc[:end_loc + 1].dropna()
        if len(spy) > 66:
            m1 = spy.iloc[-1] / spy.iloc[-22] - 1
            m3 = spy.iloc[-1] / spy.iloc[-66] - 1
            score += np.tanh((0.5 * m1 + 0.5 * m3) * 10)
    # Credit
    if "HYG" in prices.columns and "LQD" in prices.columns:
        ratio = (prices["HYG"] / prices["LQD"]).iloc[:end_loc + 1].dropna()
        if len(ratio) > 22:
            chg = ratio.iloc[-1] / ratio.iloc[-22] - 1
            score += np.tanh(chg * 15)
    # VIX
    if "^VIX" in prices.columns:
        vix = prices["^VIX"].iloc[:end_loc + 1].dropna()
        if len(vix) > 5:
            vix_lvl = float(vix.iloc[-1])
            score += np.clip((25 - vix_lvl) / 15, -1.5, 1.5)
    # BTC
    if "BTC-USD" in prices.columns:
        btc = prices["BTC-USD"].iloc[:end_loc + 1].dropna()
        if len(btc) > 22:
            btc_m = btc.iloc[-1] / btc.iloc[-22] - 1
            score += np.tanh(btc_m * 5) * 0.5
    # Light inverted USD
    for cand in ("UUP", "DX-Y.NYB"):
        if cand in prices.columns:
            u = prices[cand].iloc[:end_loc + 1].dropna()
            if len(u) > 22:
                usd_m = float(u.iloc[-1] / u.iloc[-22] - 1)
                score += np.tanh(-usd_m * 10) * 0.45
            break
    return float(np.clip(score / 2.8, -2, 2))


def _liq_score_at(prices: pd.DataFrame, end_loc: int) -> float:
    """Simplified liquidity score up to end_loc."""
    score = 0.0
    n = 0
    # SPY vol proxy
    if "SPY" in prices.columns:
        spy = prices["SPY"].iloc[:end_loc + 1].dropna()
        if len(spy) > 22:
            vol = float(spy.pct_change().iloc[-21:].std() * np.sqrt(252))
            if vol < 0.15:
                score += 0.8
            elif vol < 0.22:
                score += 0.3
            else:
                score -= 0.6
            n += 1
    # HYG vol
    if "HYG" in prices.columns:
        hyg = prices["HYG"].iloc[:end_loc + 1].dropna()
        if len(hyg) > 22:
            hvol = float(hyg.pct_change().iloc[-21:].std() * np.sqrt(252))
            if hvol < 0.08:
                score += 0.5
            elif hvol > 0.15:
                score -= 0.7
            n += 1
    # USD inverted
    for cand in ("UUP", "DX-Y.NYB"):
        if cand in prices.columns:
            u = prices[cand].iloc[:end_loc + 1].dropna()
            if len(u) > 64:
                r63 = float(u.iloc[-1] / u.iloc[-64] - 1)
                score += float(np.tanh(-r63 * 8)) * 0.9
                n += 1
            break
    if n == 0:
        return 0.0
    return float(np.clip(score / n, -1.5, 1.5))


def _vrp_at(prices: pd.DataFrame, end_loc: int) -> float:
    if "^VIX" not in prices.columns or "SPY" not in prices.columns:
        return np.nan
    vix = prices["^VIX"].iloc[:end_loc + 1].dropna()
    spy = prices["SPY"].iloc[:end_loc + 1].dropna()
    if len(vix) < 5 or len(spy) < 22:
        return np.nan
    current_vix = float(vix.iloc[-1])
    realized = float(spy.pct_change().iloc[-21:].std() * np.sqrt(252) * 100)
    return current_vix - realized


def compute_gauge_history(prices: pd.DataFrame,
                          lookback_days: int = 756,
                          step: int = 5) -> Dict[str, Any]:
    """
    Return sparse time series of Risk, Liquidity, VRP scores + discrete regime labels.
    lookback_days ≈ 3y trading days; step=5 keeps it fast.
    """
    n = len(prices)
    if n < 100:
        return {"dates": [], "risk": [], "liq": [], "vrp": [], "regime": []}

    start = max(80, n - lookback_days)
    dates, risk, liq, vrp, regimes = [], [], [], [], []

    for i in range(start, n, step):
        r = _risk_score_at(prices, i)
        l = _liq_score_at(prices, i)
        v = _vrp_at(prices, i)
        # discrete regime for the block view (simplified 3-state on risk)
        if r > 0.4:
            reg = "RiskOn"
        elif r < -0.4:
            reg = "RiskOff"
        else:
            reg = "Neutral"
        dates.append(prices.index[i].strftime("%Y-%m-%d"))
        risk.append(round(r, 3))
        liq.append(round(l, 3))
        vrp.append(round(v, 2) if not np.isnan(v) else None)
        regimes.append(reg)

    # percentiles for range bars (last ~1Y of the series)
    def pcts(series: List[float]) -> Dict[str, float]:
        clean = [x for x in series if x is not None and not (isinstance(x, float) and np.isnan(x))]
        if len(clean) < 10:
            return {"p5": None, "p95": None, "min": None, "max": None}
        arr = np.array(clean)
        return {
            "p5": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }

    # use last ~50 points (~1Y at step=5) for 1Y range
    one_y = max(0, len(risk) - 55)
    return {
        "dates": dates,
        "risk": risk,
        "liq": liq,
        "vrp": vrp,
        "regime": regimes,
        "range_1y": {
            "risk": pcts(risk[one_y:]),
            "liq": pcts(liq[one_y:]),
            "vrp": pcts([x for x in vrp[one_y:] if x is not None]),
        },
        "range_full": {
            "risk": pcts(risk),
            "liq": pcts(liq),
            "vrp": pcts([x for x in vrp if x is not None]),
        },
    }
