"""
Trending Themes & Fund Flow Radar
"""

import pandas as pd
import numpy as np
from src.config import THEMES


def compute_theme_metrics(prices: pd.DataFrame) -> pd.DataFrame:
    """
    For each theme, compute relative performance vs SPY and simple risk metrics.
    """
    rows = []
    spy = prices.get("SPY")
    
    for theme_id, meta in THEMES.items():
        tickers = [t for t in meta["tickers"] if t in prices.columns]
        if not tickers:
            continue
        
        # Equal-weight theme return series
        theme_prices = prices[tickers].mean(axis=1).dropna()
        if len(theme_prices) < 30:
            continue
        
        def ret(n):
            if len(theme_prices) > n:
                return theme_prices.iloc[-1] / theme_prices.iloc[-n-1] - 1
            return np.nan
        
        r1m = ret(21)
        r3m = ret(63)
        r1y = ret(252)
        
        # Relative to SPY
        if spy is not None and len(spy.dropna()) > 21:
            spy_1m = spy.dropna().iloc[-1] / spy.dropna().iloc[-22] - 1
            rel_1m = r1m - spy_1m if not np.isnan(r1m) else np.nan
        else:
            rel_1m = np.nan
        
        # Vol & Sharpe approx
        rets = theme_prices.pct_change().dropna().iloc[-126:]
        vol = rets.std() * np.sqrt(252)
        ann = (1 + rets).prod() ** (252 / len(rets)) - 1 if len(rets) > 5 else np.nan
        sharpe = (ann - 0.037) / vol if vol and vol > 0 else np.nan
        
        rows.append({
            "theme_id": theme_id,
            "name": meta["name"],
            "tickers": ", ".join(tickers),
            "ret_1m": r1m,
            "ret_3m": r3m,
            "ret_1y": r1y,
            "rel_spy_1m": rel_1m,
            "vol_6m": vol,
            "sharpe_6m": sharpe,
            "last_price": theme_prices.iloc[-1]
        })
    
    df = pd.DataFrame(rows)
    if not df.empty:
        # Simple ranking score: recent relative strength + Sharpe
        df["score"] = df["rel_spy_1m"].fillna(0) * 2 + df["sharpe_6m"].fillna(0) * 0.3
        df = df.sort_values("score", ascending=False)
    return df
