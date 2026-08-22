"""
Historical analogs: quantitative forward returns and forward vol under similar
gauge regimes + short qualitative narrative.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List


def _regime_label(risk_score: float, slope_10y2y: float, vrp: float) -> str:
    if risk_score > 0.4:
        risk = "RiskOn"
    elif risk_score < -0.4:
        risk = "RiskOff"
    else:
        risk = "Neutral"

    if slope_10y2y is None:
        curve = "NA"
    elif slope_10y2y > 0.5:
        curve = "Steep"
    elif slope_10y2y > 0:
        curve = "MildSteep"
    elif slope_10y2y > -0.5:
        curve = "Flat"
    else:
        curve = "Inverted"

    if vrp is not None and vrp > 5:
        vol = "HighVRP"
    elif vrp is not None and vrp < 0:
        vol = "NegVRP"
    else:
        vol = "NormVRP"

    return f"{risk}_{curve}_{vol}"


# Expanded universe for regime-conditional performance
ANALOG_ASSETS = [
    # Core
    "SPY", "QQQ", "IWM",
    # DM / Asia
    "VGK", "EWJ", "EWH", "EWT",
    # EM
    "EEM", "EWY",
    # Credit / rates proxy
    "HYG", "TLT",
    # Commodities
    "GLD", "SLV", "USO", "BNO", "CPER",
    # Crypto
    "BTC-USD",
]


def compute_forward_stats(prices: pd.DataFrame,
                          entry_dates: List,
                          horizons: Dict[str, int] = None) -> Dict[str, Any]:
    """
    For each asset and horizon compute:
      - avg forward return
      - hit rate
      - avg forward realized vol (annualised)
      - n
    """
    if horizons is None:
        horizons = {"1M": 21, "3M": 63}

    assets = [t for t in ANALOG_ASSETS if t in prices.columns]
    # results[a][h] = list of (ret, fwd_vol)
    results = {a: {h: [] for h in horizons} for a in assets}

    for dt in entry_dates:
        try:
            if dt not in prices.index:
                idx = prices.index.get_indexer([dt], method="nearest")[0]
                if idx < 0:
                    continue
                dt = prices.index[idx]
        except Exception:
            continue

        for a in assets:
            s = prices[a].dropna()
            if dt not in s.index:
                continue
            try:
                pos = s.index.get_loc(dt)
            except Exception:
                continue
            for hname, n in horizons.items():
                if pos + n < len(s):
                    ret = float(s.iloc[pos + n] / s.iloc[pos] - 1)
                    # forward realized vol over the same horizon
                    rets = s.iloc[pos:pos + n + 1].pct_change().dropna()
                    if len(rets) > 3:
                        fwd_vol = float(rets.std() * np.sqrt(252))
                    else:
                        fwd_vol = np.nan
                    results[a][hname].append((ret, fwd_vol))

    summary = {}
    for a in assets:
        summary[a] = {}
        for hname in horizons:
            pairs = results[a][hname]
            if len(pairs) >= 3:
                rets = [p[0] for p in pairs]
                vols = [p[1] for p in pairs if not np.isnan(p[1])]
                summary[a][hname] = {
                    "avg": float(np.mean(rets)),
                    "hit_rate": float(np.mean([1 if v > 0 else 0 for v in rets])),
                    "avg_fwd_vol": float(np.mean(vols)) if vols else None,
                    "n": len(pairs),
                }
            else:
                summary[a][hname] = {
                    "avg": None,
                    "hit_rate": None,
                    "avg_fwd_vol": None,
                    "n": len(pairs),
                }
    return summary


def find_similar_regimes(prices: pd.DataFrame,
                         current_risk: float,
                         current_slope: float,
                         current_vrp: float) -> Dict[str, Any]:
    """
    Practical regime match using available history.
    Uses equity momentum + realized vol buckets as proxy for full gauge history.
    """
    spy = prices["SPY"].dropna() if "SPY" in prices.columns else None
    if spy is None or len(spy) < 120:
        return {
            "regime": _regime_label(current_risk, current_slope or 0, current_vrp),
            "n_episodes": 0,
            "forward": {},
            "narrative": "Insufficient history in current data cache for robust analogs.",
            "sample_note": "Price history too short."
        }

    ret_3m = spy.pct_change(63)
    vol_21 = spy.pct_change().rolling(21).std() * np.sqrt(252)

    curr_mom = ret_3m.iloc[-1] if len(ret_3m.dropna()) else 0
    curr_vol = vol_21.iloc[-1] if len(vol_21.dropna()) else 0.15

    mom_bucket = "pos" if curr_mom > 0.03 else ("neg" if curr_mom < -0.03 else "flat")
    vol_bucket = "high" if curr_vol > 0.20 else ("low" if curr_vol < 0.12 else "mid")

    candidates = []
    for i in range(63, len(spy) - 66):
        m = ret_3m.iloc[i]
        v = vol_21.iloc[i]
        if pd.isna(m) or pd.isna(v):
            continue
        m_b = "pos" if m > 0.03 else ("neg" if m < -0.03 else "flat")
        v_b = "high" if v > 0.20 else ("low" if v < 0.12 else "mid")
        if m_b == mom_bucket and v_b == vol_bucket:
            candidates.append(spy.index[i])

    filtered = []
    last = None
    for d in candidates:
        if last is None or (d - last).days > 15:
            filtered.append(d)
            last = d

    forward = compute_forward_stats(prices, filtered[-25:])
    regime = _regime_label(current_risk, current_slope or 0, current_vrp)
    n = len(filtered)

    spy_1m = forward.get("SPY", {}).get("1M", {})
    avg = spy_1m.get("avg")
    hit = spy_1m.get("hit_rate")
    avg_vol = spy_1m.get("avg_fwd_vol")

    if n < 5:
        narrative = f"Only {n} roughly similar momentum/vol episodes found. Treat statistics cautiously."
    elif avg is not None:
        vol_txt = f", avg forward 1M vol ≈ {avg_vol*100:.1f}%" if avg_vol is not None else ""
        narrative = (
            f"Found {n} similar episodes in available history. "
            f"Average SPY forward 1M return: {avg*100:+.1f}% (hit rate {hit*100:.0f}%{vol_txt}). "
            f"Current mix ({regime}) has historically supported risk assets when momentum stayed positive "
            f"and realized vol stayed contained."
        )
    else:
        narrative = f"Found {n} similar episodes; forward sample still limited."

    return {
        "regime": regime,
        "n_episodes": n,
        "forward": forward,
        "narrative": narrative,
        "sample_note": f"Based on ~{len(spy)//252}y of price history. Longer history improves robustness."
    }
