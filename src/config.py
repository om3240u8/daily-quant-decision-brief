"""
Configuration for Daily Quant Decision Brief
All tickers, proxies, and parameters in one place.
"""

from datetime import datetime

# ============================================================
# ASSET UNIVERSE
# ============================================================

EQUITIES = {
    # US
    "SPY": "S&P 500",
    "QQQ": "Nasdaq 100",
    "IWM": "Russell 2000",
    # Factors (proxies)
    "VLUE": "Value",
    "MTUM": "Momentum",
    "QUAL": "Quality",
    "USMV": "Low Vol",
    # International DM
    "VGK": "Europe",
    "EWJ": "Japan",
    "EWH": "Hong Kong",
    # EM & China
    "EEM": "Emerging Markets",
    "FXI": "China Large-Cap",
    "MCHI": "China (MSCI)",
    "EWY": "South Korea",
    "EWT": "Taiwan",
    "INDA": "India",
    "EWZ": "Brazil",
}

RATES = {
    "^TNX": "US 10Y Yield",
    "^IRX": "US 13W T-Bill",
    "^TYX": "US 30Y Yield",
    # Note: 2Y is ^FVX or use FRED for full curve
}

CREDIT = {
    "HYG": "US High Yield",
    "LQD": "US Investment Grade",
}

FX = {
    "UUP": "USD Index (proxy)",
    "FXE": "Euro",
    "FXY": "Japanese Yen",
    "FXA": "Australian Dollar",
    "CYB": "Chinese Yuan",
}

COMMODITIES = {
    "GLD": "Gold",
    "SLV": "Silver",
    "USO": "Crude Oil (WTI)",
    "BNO": "Crude Oil (Brent)",
    "CPER": "Copper",
    "UNG": "Natural Gas",
    "DBC": "Broad Commodities",
}

VOLATILITY = {
    "^VIX": "VIX",
    # VIX3M / longer-dated via other sources if available
}

CRYPTO = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
}

# Thematic ETFs for radar
THEMES = {
    "AI": {"tickers": ["BOTZ", "IRBO", "AIQ"], "name": "Artificial Intelligence"},
    "SEMI": {"tickers": ["SMH", "SOXX"], "name": "Semiconductors"},
    "RARE_EARTH": {"tickers": ["REMX"], "name": "Rare Earths & Critical Minerals"},
    "SPACE": {"tickers": ["UFO", "ARKX"], "name": "Space / Satellite"},
    "DEFENSE": {"tickers": ["ITA", "PPA"], "name": "Defense"},
    "NUCLEAR": {"tickers": ["NLR", "URA"], "name": "Nuclear / Uranium"},
    "BIOTECH": {"tickers": ["XBI", "IBB"], "name": "Biotech"},
    "CHINA_TECH": {"tickers": ["KWEB", "CQQQ"], "name": "China Tech"},
}

# ============================================================
# FRED SERIES (for rates, credit spreads, funding)
# ============================================================

FRED_SERIES = {
    "DGS2": "US 2Y Treasury",
    "DGS5": "US 5Y Treasury",
    "DGS10": "US 10Y Treasury",
    "DGS30": "US 30Y Treasury",
    "T10Y2Y": "10Y-2Y Spread",
    "T10Y3M": "10Y-3M Spread",
    "BAMLH0A0HYM2": "ICE BofA HY OAS",
    "BAMLC0A0CM": "ICE BofA IG OAS",
    "SOFR": "Secured Overnight Financing Rate",
    "DFEDTARU": "Fed Funds Upper Target",  # or FEDFUNDS
}

# ============================================================
# PARAMETERS
# ============================================================

LOOKBACK_DAYS = 504          # ~2 years trading days
RF_RATE = 0.037              # current approx 13W T-bill (update dynamically)
ANNUALIZATION = {
    "equity": 252,
    "crypto": 365,
}

REPORT_TITLE = "Daily Quant Decision Brief"
GENERATED_AT = datetime.now().strftime("%Y-%m-%d %H:%M HKT")
