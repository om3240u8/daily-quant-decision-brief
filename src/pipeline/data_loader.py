"""
Data loader for Daily Quant Decision Brief.
Downloads price data via yfinance and key FRED series.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf

# Optional FRED
try:
    from fredapi import Fred
    HAS_FRED = True
except ImportError:
    HAS_FRED = False

from src.config import (
    EQUITIES, RATES, CREDIT, FX, COMMODITIES, VOLATILITY, CRYPTO, THEMES,
    FRED_SERIES, LOOKBACK_DAYS
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(exist_ok=True)


def _flatten_tickers():
    """Return flat list of all price tickers."""
    tickers = []
    for d in [EQUITIES, RATES, CREDIT, FX, COMMODITIES, VOLATILITY, CRYPTO]:
        tickers.extend(d.keys())
    # Themes
    for theme in THEMES.values():
        tickers.extend(theme["tickers"])
    return list(set(tickers))


def download_prices(period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    """Download adjusted close prices for the full universe."""
    tickers = _flatten_tickers()
    print(f"Downloading {len(tickers)} tickers...")
    raw = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False, threads=True)
    
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"].copy()
    else:
        closes = raw[["Close"]].copy() if "Close" in raw.columns else raw.copy()
    
    closes = closes.dropna(how="all")
    # Save
    out_path = DATA_DIR / "prices.parquet"
    closes.to_parquet(out_path)
    print(f"Saved prices → {out_path}  shape={closes.shape}")
    return closes


def download_fred(api_key: str = None) -> pd.DataFrame:
    """Download key FRED series if API key available."""
    if not HAS_FRED:
        print("fredapi not installed – skipping FRED download")
        return pd.DataFrame()
    
    key = api_key or os.environ.get("FRED_API_KEY")
    if not key:
        print("No FRED_API_KEY – skipping FRED download (set env var or pass key)")
        return pd.DataFrame()
    
    fred = Fred(api_key=key)
    frames = {}
    for series_id, name in FRED_SERIES.items():
        try:
            s = fred.get_series(series_id)
            frames[series_id] = s
            print(f"  FRED {series_id} OK")
        except Exception as e:
            print(f"  FRED {series_id} failed: {e}")
    
    if not frames:
        return pd.DataFrame()
    
    df = pd.DataFrame(frames)
    df.to_parquet(DATA_DIR / "fred.parquet")
    return df


def load_prices() -> pd.DataFrame:
    path = DATA_DIR / "prices.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return download_prices()


def compute_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change()


def trailing_metrics(prices: pd.DataFrame, windows: dict = None) -> pd.DataFrame:
    """
    Compute multi-horizon returns, vol, sharpe for each ticker.
    windows example: {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "1Y": 252}
    """
    if windows is None:
        windows = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    
    results = []
    for ticker in prices.columns:
        s = prices[ticker].dropna()
        if len(s) < 5:
            continue
        row = {"ticker": ticker}
        for name, n in windows.items():
            if len(s) > n:
                ret = s.iloc[-1] / s.iloc[-n-1] - 1
            else:
                ret = np.nan
            row[f"ret_{name}"] = ret
        
        # 1Y stats
        r = s.pct_change().dropna()
        look = min(252, len(r))
        rr = r.iloc[-look:]
        ann_factor = 252 if not ticker.endswith("-USD") else 365
        ann_ret = (1 + rr).prod() ** (ann_factor / len(rr)) - 1 if len(rr) > 1 else np.nan
        vol = rr.std() * np.sqrt(ann_factor)
        sharpe = (ann_ret - 0.037) / vol if vol and vol > 0 else np.nan
        row["ann_ret_1y"] = ann_ret
        row["vol_1y"] = vol
        row["sharpe_1y"] = sharpe
        row["last_price"] = s.iloc[-1]
        row["last_date"] = s.index[-1]
        results.append(row)
    
    return pd.DataFrame(results).set_index("ticker")


if __name__ == "__main__":
    prices = download_prices()
    print(prices.tail(3))
    metrics = trailing_metrics(prices)
    print(metrics[["ret_1D", "ret_1W", "ret_1M", "ann_ret_1y", "vol_1y", "sharpe_1y"]].head(15))
