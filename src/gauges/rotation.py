"""
Relative Rotation Graph (RRG) style computation for the Daily Quant Decision Brief.

Computes RS-Ratio (relative strength trend) and RS-Momentum for a universe
against a chosen benchmark. Values are normalized around 100.
"""

from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np


def _safe_last(s: pd.Series, n: int = 1) -> float:
    clean = s.dropna()
    if len(clean) < n:
        return np.nan
    return float(clean.iloc[-n])


def compute_rrg_points(
    prices: pd.DataFrame,
    tickers: List[str],
    benchmark: str,
    names: Optional[Dict[str, str]] = None,
    rs_window: int = 20,
    mom_window: int = 10,
    tail_length: int = 8,
) -> List[Dict[str, Any]]:
    """
    Compute RRG coordinates for each ticker vs benchmark.

    RS-Ratio  ≈ 100 * (current RS / SMA(RS, rs_window))
    RS-Momentum ≈ 100 * (1 + ROC of RS over mom_window), centered near 100

    Returns list of dicts with x (RS-Ratio), y (RS-Momentum), quadrant, and optional short tail.
    """
    if benchmark not in prices.columns:
        return []

    bench = prices[benchmark].dropna()
    if len(bench) < max(rs_window, mom_window) + 5:
        return []

    results = []
    for t in tickers:
        if t not in prices.columns or t == benchmark:
            continue
        px = prices[t].dropna()
        common = px.index.intersection(bench.index)
        if len(common) < max(rs_window, mom_window) + 5:
            continue

        rs = (px.loc[common] / bench.loc[common]).dropna()
        if len(rs) < rs_window + 2:
            continue

        # Current RS-Ratio (relative strength trend)
        rs_sma = rs.rolling(rs_window, min_periods=rs_window // 2).mean()
        if pd.isna(rs_sma.iloc[-1]) or rs_sma.iloc[-1] == 0:
            continue
        rs_ratio = 100.0 * float(rs.iloc[-1] / rs_sma.iloc[-1])

        # Momentum of relative strength
        if len(rs) > mom_window:
            roc = float(rs.iloc[-1] / rs.iloc[-mom_window - 1] - 1)
            rs_mom = 100.0 * (1.0 + roc)
        else:
            rs_mom = 100.0

        # Quadrant
        if rs_ratio >= 100 and rs_mom >= 100:
            quad = "Leading"
        elif rs_ratio >= 100 and rs_mom < 100:
            quad = "Weakening"
        elif rs_ratio < 100 and rs_mom < 100:
            quad = "Lagging"
        else:
            quad = "Improving"

        # Short tail (last few points, same definition)
        tail = []
        for lag in range(1, min(tail_length, len(rs) - rs_window) + 1):
            idx = -lag
            if abs(idx) >= len(rs):
                break
            r_now = rs.iloc[idx]
            sma_now = rs.iloc[max(0, idx - rs_window + 1): idx + 1].mean()
            if sma_now and not pd.isna(sma_now) and sma_now != 0:
                r_ratio = 100.0 * float(r_now / sma_now)
                if abs(idx) > mom_window:
                    r_roc = float(rs.iloc[idx] / rs.iloc[idx - mom_window] - 1)
                    r_mom = 100.0 * (1.0 + r_roc)
                else:
                    r_mom = 100.0
                tail.append({"x": round(r_ratio, 2), "y": round(r_mom, 2)})

        tail = list(reversed(tail))  # oldest first

        results.append({
            "ticker": t,
            "name": (names or {}).get(t, t),
            "x": round(rs_ratio, 2),
            "y": round(rs_mom, 2),
            "quadrant": quad,
            "tail": tail,
        })

    return results


def build_rotation_universes(prices: pd.DataFrame) -> Dict[str, Any]:
    """
    Pre-compute RRG points for the main filterable universes across several windows.
    Structure: universes[key] = {label, benchmark, windows: { "21/10": [points], ... }}
    """
    from src.config import EQUITIES, SECTORS, COMMODITIES, CREDIT, CRYPTO

    windows = [
        (10, 5),   # short / tactical
        (21, 10),  # weekly-style (default)
        (63, 21),  # intermediate
        (126, 42), # longer
    ]

    def for_universe(tickers, names, benchmark):
        by_window = {}
        for rs_w, mom_w in windows:
            key = f"{rs_w}/{mom_w}"
            by_window[key] = compute_rrg_points(
                prices, tickers, benchmark, names,
                rs_window=rs_w, mom_window=mom_w, tail_length=6
            )
        return by_window

    style_tickers = ["VLUE", "MTUM", "QUAL", "USMV", "QQQ", "IWM"]
    style_names = {k: EQUITIES.get(k, k) for k in style_tickers}

    region_tickers = ["VGK", "EWJ", "EWH", "EEM", "FXI", "MCHI", "EWY", "EWT", "INDA", "EWZ"]
    region_names = {k: EQUITIES.get(k, k) for k in region_tickers}

    sector_tickers = list(SECTORS.keys())

    asset_tickers = list(COMMODITIES.keys()) + list(CREDIT.keys()) + list(CRYPTO.keys()) + ["UUP"]
    asset_names = {**COMMODITIES, **CREDIT, **CRYPTO, "UUP": "USD Index"}

    return {
        "styles": {
            "label": "US Styles / Factors",
            "benchmark": "SPY",
            "windows": for_universe(style_tickers, style_names, "SPY"),
        },
        "regions": {
            "label": "Regions / Countries",
            "benchmark": "SPY",
            "windows": for_universe(region_tickers, region_names, "SPY"),
        },
        "sectors": {
            "label": "US Sectors",
            "benchmark": "SPY",
            "windows": for_universe(sector_tickers, SECTORS, "SPY"),
        },
        "assets": {
            "label": "Cross-Asset (vs SPY)",
            "benchmark": "SPY",
            "windows": for_universe(asset_tickers, asset_names, "SPY"),
        },
    }
