"""
Quantitative Liquidity / Funding gauge.
Both funding liquidity and market liquidity proxies.
Includes inverted USD strength as a global funding / liquidity channel.
Enhanced with SOFR-IORB, HY OAS, TGA/net liquidity, and market breadth (MLGT-style).
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional


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


def _market_breadth_component(prices: pd.DataFrame) -> Tuple[float, Dict[str, Any]]:
    """
    Simple market breadth: % of available equity ETFs above their 50-day SMA.
    Higher % = better breadth = higher liquidity score.
    """
    equity_tickers = [t for t in ["SPY", "QQQ", "IWM", "VGK", "EWJ", "EEM", "FXI"] if t in prices.columns]
    if len(equity_tickers) < 3:
        return 0.0, {}

    above_50 = 0
    total = 0
    for t in equity_tickers:
        s = prices[t].dropna()
        if len(s) > 50:
            sma50 = s.iloc[-50:].mean()
            if s.iloc[-1] > sma50:
                above_50 += 1
            total += 1

    if total == 0:
        return 0.0, {}

    pct = above_50 / total
    components = {"breadth_pct_above_50sma": round(pct, 3), "breadth_n": total}
    # Score contribution: 0.5 at 50%, +0.4 at 80%, -0.5 at 20%
    contrib = (pct - 0.5) * 1.0
    return contrib, components


def liquidity_gauge(
    prices: pd.DataFrame,
    volumes: pd.DataFrame = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Composite liquidity score.
    Higher score = better / more abundant liquidity.

    Components:
      1. Market liquidity (SPY Amihud / realized-vol proxy)
      2. Credit market functioning (HYG realized vol)
      3. Short-rate pressure (^IRX)
      4. Inverted USD strength (UUP / DXY)
      5. Market breadth (% above 50SMA)
      6. Optional injected: SOFR-IORB spread (bp), HY OAS (%), TGA (B)
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

    # 5. Market breadth
    breadth_contrib, breadth_comp = _market_breadth_component(prices)
    if breadth_comp:
        components.update(breadth_comp)
        score += breadth_contrib
        n += 1

    # 6. Injected microstructure series (SOFR-IORB, HY OAS, TGA)
    if extra:
        if "sofr_iorb_bp" in extra:
            bp = float(extra["sofr_iorb_bp"])
            components["sofr_iorb_bp"] = round(bp, 1)
            # Positive spread = stress
            if bp > 5:
                score -= 0.6
            elif bp > 2:
                score -= 0.3
            elif bp < 0:
                score += 0.2
            n += 1

        if "hy_oas_pct" in extra:
            oas = float(extra["hy_oas_pct"])
            components["hy_oas_pct"] = round(oas, 2)
            # Higher OAS = stress; baseline ~3.0
            if oas > 4.0:
                score -= 0.7
            elif oas > 3.5:
                score -= 0.4
            elif oas > 3.0:
                score -= 0.15
            else:
                score += 0.2
            n += 1

        if "tga_bn" in extra:
            tga = float(extra["tga_bn"])
            components["tga_bn"] = round(tga, 1)
            # Elevated TGA drains liquidity; rough threshold ~900B+
            if tga > 950:
                score -= 0.4
            elif tga > 900:
                score -= 0.2
            n += 1

        if "net_liquidity_tn" in extra:
            nl = float(extra["net_liquidity_tn"])
            components["net_liquidity_tn"] = round(nl, 2)
            # Informational; small contribution
            n += 0  # don't count in n to avoid double-weighting with TGA

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
        # Build evidence string from available components
        bits = []
        if "sofr_iorb_bp" in components:
            bits.append(f"SOFR-IORB +{components['sofr_iorb_bp']}bp")
        if "hy_oas_pct" in components:
            bits.append(f"HY OAS {components['hy_oas_pct']}%")
        if "tga_bn" in components:
            bits.append(f"TGA ${components['tga_bn']}B")
        if "usd_ret_21d" in components:
            bits.append(f"USD 1M {components['usd_ret_21d']:+.1%}")
        evidence = ", ".join(bits) if bits else "mixed signals"
        interp = f"Some signs of reduced market liquidity or funding pressure ({evidence})."
    else:
        label = "Stressed"
        interp = (
            "Elevated illiquidity / funding stress signals "
            "(SOFR-IORB positive, HY OAS elevated, TGA drain, USD strength, or credit vol). "
            "Caution on crowded or high-beta positions; local liquidity crisis risk."
        )

    return {
        "score": round(final, 3),
        "label": label,
        "components": components,
        "interpretation": interp
    }