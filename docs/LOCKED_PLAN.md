# Daily Quant Decision Brief — Locked Plan

**Locked on:** 2026-08-08  
**Status:** Ready for implementation

---

## 1. Purpose & Philosophy

A mobile-first, quant-PM-grade daily decision tool that answers:

- What is the current cross-asset regime?
- Where are attractive / unattractive risk premia?
- What is driving markets today and what is the near-term path set?
- Which themes are gaining real traction (performance + flows) and remain worth exploring?
- What should a global multi-asset book lean into or reduce?

**Core principles**
- Critical insights first, supporting data second.
- Transparent methodology and data limitations.
- Data + historical evidence + scenario thinking + independent research anchors.
- Designed for day-start consumption.

---

## 2. Delivery Format

- **Primary output**: Single self-contained responsive HTML file (mobile-first).
- Light JavaScript (Chart.js or equivalent) for gauges, sparklines, interactive heatmaps, and collapsible sections.
- Dark theme, card-based layout.
- Critical information visible in the first screen on mobile; detail expandable.
- Self-contained (can be saved/opened offline).
- Generated for day-start use.

---

## 3. Asset & Factor Universe (Global)

**Equities**  
US (SPX, NDX, RUT + style factors), Europe, Japan, broad EM + key countries/regions (Taiwan, Korea, India, Brazil, etc.), China broken out.

**Rates**  
US full curve (2s/5s/10s/30s + real yields), German Bund, JGB. Slope and curvature measures.

**Credit**  
US IG + HY OAS.

**FX**  
DXY + major pairs + G10/EM carry basket.

**Commodities**  
Energy (WTI), Gold, Copper + broad proxy. Curve/roll where available.

**Volatility**  
VIX + term structure, bond vol proxy (MOVE or closest public equivalent), basic equity skew proxies.

**Crypto**  
BTC + ETH only.

**Emerging Markets** (full pillar)  
Equity, FX, hard-currency debt proxy, selected local rates, China vs rest-of-EM relative value.

**Liquidity / Funding**  
SOFR and related spreads, simple market-liquidity proxies.

---

## 4. Gauges (Beyond Price Action)

Each gauge includes: current reading, historical percentile/z-score, short sparkline, one-sentence interpretation, and transparent formula.

| Gauge | Core Inputs | Theoretical Basis |
|-------|-------------|-------------------|
| Risk-On / Risk-Off | Equity momentum, credit spreads, FX carry, inverted vol, safe-haven residual | Risk-appetite & safe-haven factor literature |
| Yield Curve & Term Premium | Level, slope (2s10s etc.), curvature, simple term-premium estimate | ACM-style, Brooks-Moskowitz, Macrosynergy approaches |
| Vol Risk Premium & Term Structure | VIX – realized, VIX vs longer-dated, front vs back | Classic vol risk premium + term-structure timing research |
| Skew / Tail Risk | Best available public equity skew proxies + risk-reversal style measures | Option-implied crash risk / risk-aversion premium |
| Carry & Basis | FX rate differentials + returns, commodity roll, funding spreads, crypto funding rates | Koijen et al. carry, CIP deviations, commodity basis |
| Credit Risk Premium | HY/IG OAS levels and changes | Standard credit risk premium |
| Liquidity / Funding Stress | SOFR-related spreads, volume/Amihud-style proxies | Brunnermeier-Pedersen funding & market liquidity |

Clear caveats will be stated where public data is incomplete (especially full option surfaces).

---

## 5. Thematic / Trend Section (Idea Exploration)

Dedicated “Trending Themes & Fund Flow Radar”.

**Starting theme set** (dynamic, data-rotated):  
AI / GenAI, Semiconductors, Rare Earths & Critical Minerals, Space / Satellite tech, plus rotating names (Defense, Nuclear, Biotech, China tech, Robotics, etc.).

**Per theme**:
- Multi-horizon relative performance and risk-adjusted metrics
- Best available flow / attention proxies (ETF AUM changes, relative volume)
- Crowding / valuation context where possible
- Correlation to broad risk-on
- Short idea flags (dislocations or second-order expressions)

---

## 6. Report Structure (Final Order)

1. **Header / Regime Strip** — Date, overall Risk-On/Off score, top gauges, next major event
2. **PM Insights** — 3–5 high-conviction, critical bullets
3. **Narrative Drivers + High-Impact Event Calendar** (weighted by market importance; Fed, BOJ, ECB, PBOC, key data)
4. **Emerging Markets Dashboard**
5. **Trending Themes & Fund Flow Radar**
6. **Cross-Asset Relative Value & Dislocations**
7. **Detailed Gauges & Risk Premia**
8. **Asset-Class Deep Dives** (collapsible)
9. **Scenarios, Probabilities, Historical Analogs & Research Anchors**
10. **Appendix** — Methodology, exact proxies, data sources, full tables, limitations

---

## 7. Decision / Scenarios Section Requirements

- Current regime diagnosis (data-driven)
- Conditional leanings for a global multi-asset book
- 2–4 plausible near-term paths with rough probabilities (anchored to current pricing + historical transition frequencies + structured judgment)
- Historical analogs of similar gauge configurations
- References to independent research (ACM term premium, carry literature, vol risk premium papers, multi-asset factor studies, central-bank research, etc.)

Simple historical performance of regime filters on the chosen proxies will be shown.

---

## 8. Data & Methodology Principles

- Prefer official high-quality public sources (FRED, New York Fed, Fed yield curve, liquid ETF proxies, CBOE-style vol).
- All calculations transparent and reproducible.
- Explicit documentation of limitations (especially skew surfaces and precise real-time flows).
- No black-box scores.

---

## 9. Timing & Maintenance

- Generated for day-start use.
- Architecture supports later addition of a lighter intraday version if required.
- Themes and EM country weights remain rules-based and dynamic.
