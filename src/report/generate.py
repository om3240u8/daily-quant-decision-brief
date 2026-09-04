"""
Generate the responsive HTML Daily Quant Decision Brief.
Includes historical analogs, liquidity gauge (with USD), range bars,
Chart.js gauge history, discrete regime blocks, and expanded asset coverage.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from datetime import datetime
import json
import pandas as pd
import numpy as np

from src.pipeline.data_loader import load_prices, download_prices, trailing_metrics
from src.gauges.core import run_all_gauges
from src.gauges.history import compute_gauge_history
from src.themes.radar import compute_theme_metrics
from src.pipeline.events import get_upcoming_events, events_to_html
from src.pipeline.policy_pricing import (
    collect_policy_pricing,
    policy_card_html,
    policy_insight,
    policy_scenarios,
)
from src.analogs.historical import find_similar_regimes
from src.config import EQUITIES, REPORT_TITLE, CRYPTO, COMMODITIES, CREDIT


def fmt_pct(x, decimals=1):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    return f"{x*100:+.{decimals}f}%"


def fmt_num(x, decimals=2):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    return f"{x:.{decimals}f}"


def _range_bar_html(score, p5, p95, min_v, max_v, theor_lo=None, theor_hi=None, decimals=2):
    """
    Neutral CSS range track with 5–95 historical band, current marker,
    and explicit numerical bounds. If theor_lo/hi given (normalised range),
    the track is scaled to that theoretical range and bounds are labelled.
    """
    if score is None:
        return ""
    # Prefer theoretical normalised range when provided; else historical min/max
    if theor_lo is not None and theor_hi is not None:
        lo, hi = float(theor_lo), float(theor_hi)
        bound_lo_label = f"{theor_lo:.{decimals}f}"
        bound_hi_label = f"{theor_hi:.{decimals}f}"
        band_note = "theor. range"
    else:
        if p5 is None or p95 is None:
            return ""
        lo = min_v if min_v is not None else p5
        hi = max_v if max_v is not None else p95
        bound_lo_label = f"{lo:.{decimals}f}"
        bound_hi_label = f"{hi:.{decimals}f}"
        band_note = "hist. 5–95"

    span = hi - lo if hi > lo else 1.0

    # 5–95 band position (only if we have historical percentiles)
    band_html = ""
    if p5 is not None and p95 is not None:
        left_5 = max(0, min(100, (p5 - lo) / span * 100))
        width_band = max(2, min(100 - left_5, (p95 - p5) / span * 100))
        band_html = f'<div class="range-band" style="left:{left_5:.1f}%;width:{width_band:.1f}%;" title="hist 5–95: {p5:.{decimals}f} → {p95:.{decimals}f}"></div>'

    marker = max(0, min(100, (float(score) - lo) / span * 100))
    return f"""
    <div class="range-wrap">
      <div class="range-bounds"><span>{bound_lo_label}</span><span class="range-note">{band_note}</span><span>{bound_hi_label}</span></div>
      <div class="range-track" title="marker = current ({score:.{decimals}f})">
        {band_html}
        <div class="range-marker" style="left:{marker:.1f}%;"></div>
      </div>
    </div>
    """


def build_html(prices, metrics, gauges, themes, analogs, hist, policy=None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M HKT")
    risk = gauges.get("risk_on_off", {})
    vrp = gauges.get("vol_risk_premium", {})
    curve = gauges.get("yield_curve", {})
    credit = gauges.get("credit", {})
    liq = gauges.get("liquidity", {})

    us_tickers = ["SPY", "QQQ", "IWM", "VLUE", "MTUM", "QUAL", "USMV"]
    dm_tickers = ["VGK", "EWJ", "EWH"]
    em_tickers = ["EEM", "FXI", "MCHI", "EWY", "EWT", "INDA", "EWZ"]
    other_tickers = list(CRYPTO.keys()) + list(COMMODITIES.keys()) + list(CREDIT.keys()) + ["UUP", "^VIX"]

    def make_rows(ticker_list):
        rows = ""
        for t in ticker_list:
            if t not in metrics.index:
                continue
            row = metrics.loc[t]
            name = EQUITIES.get(t, t)
            if t in CRYPTO:
                name = CRYPTO[t]
            elif t in COMMODITIES:
                name = COMMODITIES[t]
            elif t in CREDIT:
                name = CREDIT[t]
            elif t == "UUP":
                name = "USD Index"
            elif t == "^VIX":
                name = "VIX"
            rows += f"""
            <tr>
              <td>{name}<br><small>{t}</small></td>
              <td class="{'pos' if row.get('ret_1D',0)>0 else 'neg'}">{fmt_pct(row.get('ret_1D'))}</td>
              <td class="{'pos' if row.get('ret_1W',0)>0 else 'neg'}">{fmt_pct(row.get('ret_1W'))}</td>
              <td class="{'pos' if row.get('ret_1M',0)>0 else 'neg'}">{fmt_pct(row.get('ret_1M'))}</td>
              <td class="{'pos' if row.get('ret_3M',0)>0 else 'neg'}">{fmt_pct(row.get('ret_3M'))}</td>
              <td>{fmt_pct(row.get('ann_ret_1y'))}</td>
              <td>{fmt_pct(row.get('vol_1y'))}</td>
              <td>{fmt_num(row.get('sharpe_1y'))}</td>
            </tr>"""
        return rows

    theme_rows = ""
    if themes is not None and not themes.empty:
        for _, r in themes.iterrows():
            theme_rows += f"""
            <tr>
              <td><strong>{r['name']}</strong><br><small>{r['tickers']}</small></td>
              <td class="{'pos' if r['ret_1m']>0 else 'neg'}">{fmt_pct(r['ret_1m'])}</td>
              <td class="{'pos' if r['ret_3m']>0 else 'neg'}">{fmt_pct(r['ret_3m'])}</td>
              <td class="{'pos' if r['rel_spy_1m']>0 else 'neg'}">{fmt_pct(r['rel_spy_1m'])}</td>
              <td>{fmt_num(r['sharpe_6m'])}</td>
            </tr>"""

    ylds = curve.get("components", {}).get("yields", {})
    spreads = curve.get("components", {}).get("spreads", {})
    curve_asof = curve.get("components", {}).get("as_of", "")

    curve_rows = ""
    for mat in ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "30Y"]:
        if mat in ylds:
            curve_rows += f"<tr><td>{mat}</td><td>{ylds[mat]:.3f}%</td></tr>"

    risk_score = risk.get("score", 0) or 0
    risk_label = risk.get("label", "N/A")
    risk_color = "#3fb950" if risk_score > 0.4 else ("#f85149" if risk_score < -0.4 else "#d29922")

    r1y = hist.get("range_1y", {})
    risk_rng = r1y.get("risk", {})
    liq_rng = r1y.get("liq", {})
    vrp_rng = r1y.get("vrp", {})

    # Theoretical normalised ranges (from gauge clip bounds)
    # Risk-On/Off: clipped to [-2, 2]; Liquidity: [-1.5, 1.5]; VRP is raw pts (no hard clip)
    risk_bar = _range_bar_html(risk_score, risk_rng.get("p5"), risk_rng.get("p95"),
                              risk_rng.get("min"), risk_rng.get("max"),
                              theor_lo=-2.0, theor_hi=2.0, decimals=2)
    liq_score = liq.get("score")
    liq_bar = _range_bar_html(liq_score, liq_rng.get("p5"), liq_rng.get("p95"),
                              liq_rng.get("min"), liq_rng.get("max"),
                              theor_lo=-1.5, theor_hi=1.5, decimals=2)
    vrp_score = vrp.get("score")
    # VRP is not forced into a fixed band; use historical range for the track
    vrp_bar = _range_bar_html(vrp_score, vrp_rng.get("p5"), vrp_rng.get("p95"),
                              vrp_rng.get("min"), vrp_rng.get("max"),
                              theor_lo=None, theor_hi=None, decimals=1)

    fwd = analogs.get("forward", {})
    analog_rows = ""
    for asset, horizons in fwd.items():
        m1 = horizons.get("1M", {})
        m3 = horizons.get("3M", {})
        analog_rows += f"""
        <tr>
          <td>{asset}</td>
          <td>{fmt_pct(m1.get('avg')) if m1.get('avg') is not None else '–'}</td>
          <td>{f"{m1.get('hit_rate')*100:.0f}%" if m1.get('hit_rate') is not None else '–'}</td>
          <td>{fmt_pct(m1.get('avg_fwd_vol')) if m1.get('avg_fwd_vol') is not None else '–'}</td>
          <td>{fmt_pct(m3.get('avg')) if m3.get('avg') is not None else '–'}</td>
          <td>{m1.get('n', 0)}</td>
        </tr>"""

    events = get_upcoming_events(45)
    events_html = events_to_html(events)

    if policy is None:
        try:
            policy = collect_policy_pricing()
        except Exception as e:
            print(f"policy_pricing failed: {e}")
            policy = {"ok": False}
    policy_html = policy_card_html(policy)
    policy_bullet = policy_insight(policy)
    scenarios = policy_scenarios(policy)
    scen_html = ""
    for s in scenarios:
        pct = f"{100.0 * s['p']:.0f}%"
        scen_html += (
            f"<div class=\"scenario\"><strong>{s['title']}</strong> · {pct}<br>"
            f"<small>{s['text']}</small></div>\n"
        )

    # ~1Y multi-gauge chart
    chart_dates = json.dumps(hist.get("dates", [])[-55:])
    chart_risk = json.dumps(hist.get("risk", [])[-55:])
    chart_liq = json.dumps(hist.get("liq", [])[-55:])
    chart_vrp = json.dumps([x if x is not None else None for x in hist.get("vrp", [])[-55:]])

    # ~3Y regime strength panel (full hist)
    dates_full = hist.get("dates", [])
    risk_full = hist.get("risk", [])
    regimes = hist.get("regime", [])
    regime3y_dates = json.dumps(dates_full)
    regime3y_risk = json.dumps(risk_full)
    regime3y_regimes = json.dumps(regimes)

    regime_blocks = ""
    regime_date_labels = ""
    if regimes and dates_full:
        blocks = []
        cur = regimes[0]
        start_i = 0
        for i in range(1, len(regimes)):
            if regimes[i] != cur:
                blocks.append((cur, start_i, i - 1))
                cur = regimes[i]
                start_i = i
        blocks.append((cur, start_i, len(regimes) - 1))
        color_map = {"RiskOn": "#238636", "Neutral": "#9e6a03", "RiskOff": "#da3633"}
        total = len(regimes) or 1
        for reg, a, b in blocks:
            w = max(1.2, (b - a + 1) / total * 100)
            title = f"{reg} · {dates_full[a]} → {dates_full[b]}"
            regime_blocks += f'<div class="reg-block" style="width:{w:.1f}%;background:{color_map.get(reg,"#484f58")}" title="{title}"></div>'

        # Date axis labels: ~6 evenly spaced
        n_lab = min(6, len(dates_full))
        if n_lab >= 2:
            indices = [int(round(i * (len(dates_full) - 1) / (n_lab - 1))) for i in range(n_lab)]
            for idx in indices:
                left_pct = idx / max(len(dates_full) - 1, 1) * 100
                # compact label: YYYY-MM
                lab = dates_full[idx][:7] if len(dates_full[idx]) >= 7 else dates_full[idx]
                regime_date_labels += f'<span class="reg-date" style="left:{left_pct:.1f}%">{lab}</span>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{REPORT_TITLE}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d29922;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
    padding: 12px; max-width: 1100px; margin: 0 auto;
  }}
  h1 {{ font-size: 1.35rem; color: var(--accent); margin-bottom: 4px; }}
  h2 {{ font-size: 1.05rem; color: var(--accent); margin: 22px 0 10px;
        border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 14px; }}
  .strip {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }}
  .gauge-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; flex: 1 1 120px; min-width: 100px;
  }}
  .gauge-card .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; }}
  .gauge-card .value {{ font-size: 1.2rem; font-weight: 700; margin: 3px 0; }}
  .gauge-card .note {{ font-size: 0.7rem; color: var(--muted); }}
  .range-wrap {{ margin-top: 6px; }}
  .range-bounds {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.62rem; color: var(--muted); margin-bottom: 2px; line-height: 1.2;
  }}
  .range-bounds .range-note {{ opacity: 0.7; font-size: 0.58rem; }}
  .range-track {{
    position: relative; height: 6px; background: #21262d; border-radius: 3px;
    overflow: visible;
  }}
  .range-band {{
    position: absolute; top: 0; height: 100%; background: #30363d; border-radius: 3px;
  }}
  .range-marker {{
    position: absolute; top: -3px; width: 4px; height: 12px;
    background: var(--accent); border-radius: 1px; transform: translateX(-50%);
  }}
  .insights {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 14px 16px; margin-bottom: 18px;
  }}
  .insights ul {{ padding-left: 18px; }}
  .insights li {{ margin-bottom: 7px; font-size: 0.92rem; }}
  table {{
    width: 100%; border-collapse: collapse; font-size: 0.82rem;
    background: var(--card); border-radius: 8px; overflow: hidden; margin-bottom: 14px;
  }}
  th, td {{ padding: 7px 9px; text-align: right; border-bottom: 1px solid var(--border); }}
  th {{ background: #1a2332; color: var(--muted); font-weight: 600; text-align: left; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .pos {{ color: var(--green); }} .neg {{ color: var(--red); }}
  .section {{ margin-bottom: 20px; }}
  details {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 10px; }}
  summary {{ padding: 10px 14px; cursor: pointer; font-weight: 600; }}
  details[open] summary {{ border-bottom: 1px solid var(--border); }}
  .details-body {{ padding: 12px 14px; font-size: 0.88rem; color: var(--muted); }}
  .scenario {{ background: #1a2332; border-radius: 6px; padding: 10px 12px; margin-bottom: 8px; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .footnote {{ font-size: 0.72rem; color: var(--muted); margin-top: 6px; }}
  .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .policy-card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; margin: 0 0 14px;
  }}
  .policy-head {{ display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; flex-wrap: wrap; }}
  .policy-sub {{ font-size: 0.72rem; color: var(--muted); }}
  .basis-chip {{
    font-size: 0.72rem; font-weight: 600; border-radius: 999px;
    padding: 3px 9px; white-space: nowrap;
  }}
  .chart-wrap {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px; margin-bottom: 12px;
  }}
  .chart-wrap canvas {{ width: 100% !important; max-height: 220px; }}
  .toggle-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; font-size: 0.78rem; }}
  .toggle-row label {{
    background: #21262d; border: 1px solid var(--border); border-radius: 6px;
    padding: 4px 10px; cursor: pointer; user-select: none;
  }}
  .toggle-row input {{ margin-right: 4px; }}
  .regime-strip {{
    display: flex; height: 14px; border-radius: 4px; overflow: hidden;
    border: 1px solid var(--border); margin: 4px 0 0;
  }}
  .reg-block {{ height: 100%; min-width: 2px; }}
  .regime-date-axis {{
    position: relative; height: 18px; margin-top: 2px; margin-bottom: 6px;
  }}
  .reg-date {{
    position: absolute; transform: translateX(-50%);
    font-size: 0.65rem; color: var(--muted); white-space: nowrap;
  }}
  .regime-legend {{
    display: flex; flex-wrap: wrap; gap: 12px; font-size: 0.72rem; color: var(--muted); margin-bottom: 10px;
  }}
  .regime-legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
  .regime-panel {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px; margin-bottom: 12px;
  }}
  .regime-panel canvas {{ width: 100% !important; max-height: 140px; }}
  .regime-panel .panel-title {{
    font-size: 0.8rem; color: var(--muted); margin-bottom: 6px;
  }}
  .range-select {{ display: flex; gap: 4px; }}
  .range-select button {{
    background: #21262d; border: 1px solid var(--border); color: var(--muted);
    border-radius: 6px; padding: 3px 10px; font-size: 0.72rem; cursor: pointer;
  }}
  .range-select button.active {{
    background: #1f6feb; border-color: #1f6feb; color: #fff;
  }}
  .regime-chart-wrap {{ position: relative; }}
  .regime-strip-wrap {{
    /* left/right set by JS to match Chart.js chartArea */
    margin-top: 2px;
  }}
  .regime-strip-wrap .regime-strip {{
    display: flex; height: 14px; border-radius: 3px; overflow: hidden;
    border: 1px solid var(--border);
  }}
  @media (max-width: 700px) {{
    .two-col {{ grid-template-columns: 1fr; }}
    body {{ padding: 8px; }}
    table {{ font-size: 0.76rem; }}
    .gauge-card {{ min-width: 90px; }}
  }}
  footer {{ margin-top: 28px; font-size: 0.72rem; color: var(--muted); text-align: center; }}
</style>
</head>
<body>

<h1>📊 {REPORT_TITLE}</h1>
<p class="subtitle">As of {now} · Global multi-asset · Quant PM lens · Yield curve: WSJ</p>

<!-- Regime Strip -->
<div class="strip">
  <div class="gauge-card">
    <div class="label">Risk-On / Off</div>
    <div class="value" style="color:{risk_color}">{risk_label}</div>
    <div class="note">Score {fmt_num(risk_score)}</div>
    {risk_bar}
  </div>
  <div class="gauge-card">
    <div class="label">Yield Curve</div>
    <div class="value">{curve.get('label', '–')}</div>
    <div class="note">10Y-2Y {fmt_num(spreads.get('10y2y'))}%</div>
  </div>
  <div class="gauge-card">
    <div class="label">Vol Risk Premium</div>
    <div class="value">{vrp.get('label', '–')}</div>
    <div class="note">VRP {fmt_num(vrp.get('score'))}</div>
    {vrp_bar}
  </div>
  <div class="gauge-card">
    <div class="label">Liquidity</div>
    <div class="value">{liq.get('label', '–')}</div>
    <div class="note">Score {fmt_num(liq.get('score'))}</div>
    {liq_bar}
  </div>
  <div class="gauge-card">
    <div class="label">Credit</div>
    <div class="value">{credit.get('label', '–')}</div>
    <div class="note">HY/IG {fmt_pct(credit.get('score'))}</div>
  </div>
</div>

<!-- Always-visible gauge history + regime strength (Option C) -->
<div class="section">
  <h2>Gauge History & Regime Timeline</h2>

  <!-- Multi-series ~1Y -->
  <div class="chart-wrap">
    <div class="toggle-row">
      <label><input type="checkbox" id="togRisk" checked> Risk-On/Off</label>
      <label><input type="checkbox" id="togLiq" checked> Liquidity</label>
      <label><input type="checkbox" id="togVrp" checked> VRP</label>
    </div>
    <canvas id="gaugeChart" height="180"></canvas>
  </div>

  <!-- Option C: continuous strength + discrete state, shared time axis + range select -->
  <div class="regime-panel">
    <div class="panel-title" style="display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;">
      <span>Regime strength — continuous Risk-On/Off + discrete state</span>
      <div class="range-select" id="regimeRangeSelect">
        <button type="button" data-range="6m">6M</button>
        <button type="button" data-range="1y">1Y</button>
        <button type="button" data-range="3y" class="active">3Y</button>
      </div>
    </div>
    <div class="regime-chart-wrap">
      <canvas id="regimeStrengthChart" height="120"></canvas>
    </div>
    <div class="regime-strip-wrap">
      <div class="regime-strip" id="regimeStrip"></div>
      <div class="regime-date-axis" id="regimeDateAxis"></div>
    </div>
    <div class="regime-legend">
      <span><i class="swatch" style="background:#238636"></i> Risk-On (&gt;+0.4)</span>
      <span><i class="swatch" style="background:#9e6a03"></i> Neutral</span>
      <span><i class="swatch" style="background:#da3633"></i> Risk-Off (&lt;−0.4)</span>
      <span style="opacity:0.85;">Dashed: ±0.4 state · ±1.0 strong</span>
    </div>
  </div>

  <p class="footnote">Top chart: last ~1Y multi-gauge (toggles). Bottom: continuous Risk score shows <em>strength</em>; colour bar shows discrete state. Shared date labels. Range bars on cards use theoretical normalised range (Risk [−2,+2], Liq [−1.5,+1.5]).</p>
</div>

<!-- PM Insights -->
<div class="insights">
  <strong>PM Insights</strong>
  <ul>
    <li><strong>Regime:</strong> {risk.get('interpretation', '')}</li>
    <li><strong>Curve:</strong> {curve.get('interpretation', '')}</li>
    <li><strong>Vol:</strong> {vrp.get('interpretation', '')}</li>
    <li><strong>Liquidity:</strong> {liq.get('interpretation', '')}</li>
    <li><strong>Analogs:</strong> {analogs.get('narrative', '')}</li>
    <li><strong>Policy:</strong> {policy_bullet}</li>
  </ul>
  <p class="footnote">[1] Risk-On/Off now includes a light inverted USD-strength term. [2] Liquidity includes inverted USD (63d primary + 21d) as global funding proxy. [3] Curve slope — Estrella-type + ACM. Data: WSJ / Yahoo. [4] Policy card = Kalshi + Polymarket statement books vs ZQ-implied path (no CME FedWatch API).</p>
</div>

<!-- Policy pricing -->
<div class="section">
  <h2>Policy Pricing — Next FOMC</h2>
  {policy_html}
  <p class="footnote">Kalshi / Polymarket pay on the announced target-range change. ZQ settles on the calendar-month average EFFR and is inverted with a mid-month day count. A wide basis means the two objects have diverged — not that one venue is "wrong."</p>
</div>

<!-- Events -->
<div class="section">
  <h2>High-Impact Event Calendar</h2>
  {events_html}
  <p class="footnote">Official BLS / BEA / Fed schedule. Impact weighting is judgmental based on typical market sensitivity.</p>
</div>

<!-- Yield Curve -->
<div class="section">
  <h2>U.S. Treasury Yield Curve <small style="color:var(--muted)">(WSJ · {curve_asof})</small></h2>
  <div class="two-col">
    <table>
      <thead><tr><th>Maturity</th><th>Yield</th></tr></thead>
      <tbody>{curve_rows}</tbody>
    </table>
    <div>
      <p style="font-size:0.9rem;margin-bottom:8px;"><strong>Key Spreads</strong></p>
      <ul style="font-size:0.88rem;padding-left:18px;color:var(--muted);">
        <li>10Y–2Y: <strong style="color:var(--text)">{fmt_num(spreads.get('10y2y'))}%</strong></li>
        <li>10Y–3M: <strong style="color:var(--text)">{fmt_num(spreads.get('10y3m'))}%</strong></li>
        <li>30Y–5Y: <strong style="color:var(--text)">{fmt_num(spreads.get('30y5y'))}%</strong></li>
      </ul>
    </div>
  </div>
  <p class="footnote">Source: WSJ Market Data – Bonds. Term-premium interpretation draws on Adrian-Crump-Moench (ACM) and related Fed research.</p>
</div>

<!-- Historical Analogs -->
<div class="section">
  <h2>Historical Analogs — Forward Returns & Vol</h2>
  <p style="font-size:0.88rem;margin-bottom:8px;">{analogs.get('narrative', '')}</p>
  <p class="footnote">{analogs.get('sample_note', '')} Regime key: {analogs.get('regime', '')}</p>
  <table>
    <thead>
      <tr><th>Asset</th><th>Avg 1M Fwd</th><th>Hit 1M</th><th>Avg Fwd Vol 1M</th><th>Avg 3M Fwd</th><th>N</th></tr>
    </thead>
    <tbody>{analog_rows if analog_rows else "<tr><td colspan='6'>Insufficient matching episodes</td></tr>"}</tbody>
  </table>
  <p class="footnote">Forward returns and realized vol under similar momentum + realized-vol regimes. Expanded universe includes EU / JP / HK / TW equities and Brent / WTI / Copper / Silver. Not a formal backtest of the full gauge set.</p>
</div>

<!-- Themes -->
<div class="section">
  <h2>Trending Themes & Fund Flow Radar</h2>
  <table>
    <thead><tr><th>Theme</th><th>1M</th><th>3M</th><th>vs SPY 1M</th><th>Sharpe 6M</th></tr></thead>
    <tbody>{theme_rows if theme_rows else "<tr><td colspan='5'>No data</td></tr>"}</tbody>
  </table>
  <p class="footnote">Equal-weight liquid thematic ETFs. Ranking combines relative strength and risk-adjusted return.</p>
</div>

<!-- EM -->
<div class="section">
  <h2>Emerging Markets Dashboard</h2>
  <table>
    <thead><tr><th>Asset</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>AnnRet 1Y</th><th>Vol 1Y</th><th>Sharpe</th></tr></thead>
    <tbody>{make_rows(em_tickers)}</tbody>
  </table>
</div>

<!-- US + DM (now includes HK) -->
<div class="section">
  <h2>US & Developed Market Equities (incl. HK)</h2>
  <table>
    <thead><tr><th>Asset</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>AnnRet 1Y</th><th>Vol 1Y</th><th>Sharpe</th></tr></thead>
    <tbody>{make_rows(us_tickers + dm_tickers)}</tbody>
  </table>
</div>

<!-- Cross asset (expanded commodities) -->
<div class="section">
  <h2>Cross-Asset (Crypto · Commodities · Credit · FX · Vol)</h2>
  <table>
    <thead><tr><th>Asset</th><th>1D</th><th>1W</th><th>1M</th><th>3M</th><th>AnnRet 1Y</th><th>Vol 1Y</th><th>Sharpe</th></tr></thead>
    <tbody>{make_rows(other_tickers)}</tbody>
  </table>
</div>

<!-- Scenarios -->
<div class="section">
  <h2>Near-Term Scenarios (into / through next FOMC)</h2>
  {scen_html}
  <p class="footnote">Hold / hike weights anchored to live event-book prices when available, else ZQ bucket. Path and shock legs are residual mass, not a fourth independent forecast.</p>
</div>

<!-- Methodology appendix -->
<details>
  <summary>Gauge Methodology — Definitions &amp; Equations</summary>
  <div class="details-body" style="color:var(--text);font-size:0.85rem;">
    <p style="margin-bottom:10px;color:var(--muted);">All scores are transparent composites of public price/yield series. Positive generally = supportive for risk assets / abundant liquidity.</p>

    <p><strong>1. Risk-On / Off</strong> · normalised range <code>[-2, +2]</code></p>
    <p style="margin:4px 0 8px;color:var(--muted);">Composite risk-appetite score. Positive = Risk-On.</p>
    <pre style="background:#0d1117;padding:8px 10px;border-radius:6px;font-size:0.78rem;overflow-x:auto;color:#c9d1d9;">S = clip( (s_eq + s_credit + s_vix + 0.5·s_btc + 0.45·s_usd) / 2.8 , −2, 2 )

s_eq     = tanh( (0.5·r_SPY,1M + 0.5·r_SPY,3M) · 10 )
s_credit = tanh( Δ(HYG/LQD)_1M · 15 )
s_vix    = clip( (25 − VIX) / 15 , −1.5, 1.5 )
s_btc    = tanh( r_BTC,1M · 5 )
s_usd    = tanh( −r_UUP,1M · 10 )   // inverted USD strength</pre>
    <p style="margin:6px 0 12px;font-size:0.78rem;color:var(--muted);">Label: Risk-On if S &gt; 0.4 · Neutral if |S| ≤ 0.4 · Risk-Off if S &lt; −0.4</p>

    <p><strong>2. Liquidity / Funding</strong> · normalised range <code>[-1.5, +1.5]</code></p>
    <p style="margin:4px 0 8px;color:var(--muted);">Higher = more abundant market + funding liquidity. Includes inverted USD as global funding channel.</p>
    <pre style="background:#0d1117;padding:8px 10px;border-radius:6px;font-size:0.78rem;overflow-x:auto;color:#c9d1d9;">S = clip( (c_spy + c_hyg + c_irx + c_usd) / n , −1.5, 1.5 )

c_spy : SPY 21d realised vol proxy  (low vol → +0.8 / high → −0.6)
c_hyg : HYG 21d realised vol        (low → +0.5 / high → −0.7)
c_irx : Δ 13W T-bill (5d)           (sharp rise → −0.4)
c_usd : 0.9·tanh(−r_UUP,63d · 8) + 0.35·tanh(−r_UUP,21d · 12)
        // stronger USD → tighter global USD funding → lower S</pre>
    <p style="margin:6px 0 12px;font-size:0.78rem;color:var(--muted);">Label: Abundant (&gt;0.5) · Normal (0–0.5) · Tightening (−0.6–0) · Stressed (&lt;−0.6)</p>

    <p><strong>3. Vol Risk Premium (VRP)</strong> · raw points (no hard clip)</p>
    <pre style="background:#0d1117;padding:8px 10px;border-radius:6px;font-size:0.78rem;overflow-x:auto;color:#c9d1d9;">VRP = VIX − 100 · σ̂_SPY,21d · √252

σ̂_SPY,21d = stdev of daily SPY returns over last 21 sessions</pre>
    <p style="margin:6px 0 12px;font-size:0.78rem;color:var(--muted);">Elevated if VRP &gt; 5 · Normal if 0–5 · Negative if VRP &lt; 0</p>

    <p><strong>4. Yield Curve</strong></p>
    <pre style="background:#0d1117;padding:8px 10px;border-radius:6px;font-size:0.78rem;overflow-x:auto;color:#c9d1d9;">slope_10y2y = y_10Y − y_2Y
slope_10y3m = y_10Y − y_3M</pre>
    <p style="margin:6px 0 12px;font-size:0.78rem;color:var(--muted);">Steep (&gt;0.5%) · Mildly Steep (0–0.5%) · Flat / Mild Inversion (−0.5–0) · Deeply Inverted (&lt;−0.5%)</p>

    <p><strong>5. Credit</strong></p>
    <pre style="background:#0d1117;padding:8px 10px;border-radius:6px;font-size:0.78rem;overflow-x:auto;color:#c9d1d9;">score = Δ(HYG / LQD)_1M</pre>
    <p style="margin:6px 0 12px;font-size:0.78rem;color:var(--muted);">Risk-On Credit if &gt; +1% · Risk-Off Credit if &lt; −1% · else Neutral</p>

    <p><strong>6. Policy pricing (next FOMC)</strong></p>
    <pre style="background:#0d1117;padding:8px 10px;border-radius:6px;font-size:0.78rem;overflow-x:auto;color:#c9d1d9;">ZQ implied avg EFFR = 100 − P_ZQ
r_post = (N·avg − n_pre·EFFR) / n_post
E[Δ bp] = 100 · (r_post − EFFR)
P_hike_ZQ ≈ clip(E[Δ bp] / 25, 0, 1)     // hold = 1 − hike if E[Δ]≥0

Kalshi / Polymarket: mid(yes bid, ask) on the meeting ladder
basis = P_hike_ZQ − 0.5·(P_hike_Kalshi + P_hike_Poly)</pre>
    <p style="margin:6px 0 12px;font-size:0.78rem;color:var(--muted);">Labelled ZQ-implied — not CME FedWatch. Event books price the statement; ZQ prices the month-average effective rate.</p>

    <p><strong>Range bars</strong></p>
    <p style="margin:4px 0 8px;font-size:0.78rem;color:var(--muted);">
      Track scaled to the theoretical normalised interval when the gauge is clipped
      (Risk [−2, +2], Liquidity [−1.5, +1.5]). Marker = current score.
      Shaded band = historical 5th–95th percentile of the same series over the last ~1Y
      (sampled). VRP uses historical min/max only (no fixed theoretical band).
    </p>
  </div>
</details>

<!-- References -->
<details>
  <summary>Key References &amp; Data Sources</summary>
  <div class="details-body">
    <p><strong>Data</strong></p>
    <ul>
      <li>U.S. Treasury yields: WSJ Market Data – Bonds / Treasury.gov (agent-refreshed when scrape fails)</li>
      <li>Asset prices: Yahoo Finance (yfinance)</li>
      <li>FOMC event books: Kalshi Trade API (unauth) series KXFEDDECISION; Polymarket Gamma events API</li>
      <li>ZQ month-code last: Yahoo Finance (e.g. ZQU26.CBT) · EFFR / DFEDTARU: FRED public CSV</li>
    </ul>
    <p><strong>Selected Research Anchors</strong></p>
    <ul>
      <li>Adrian, Crump, Moench – term structure / term premium (ACM model)</li>
      <li>Estrella &amp; Hardouvelis / Fed research – yield curve slope as predictor</li>
      <li>Carr &amp; Wu – volatility risk premium</li>
      <li>Koijen et al. – carry</li>
      <li>Brunnermeier &amp; Pedersen – funding vs market liquidity</li>
      <li>Amihud (2002) – illiquidity measure</li>
      <li>USD strength as risk-off / global funding channel (multi-asset risk literature)</li>
    </ul>
    <p>This is a decision-support tool only. Not investment advice.</p>
  </div>
</details>

<footer>
  Daily Quant Decision Brief · Policy card 2026-09-04 · Yield curve: WSJ · Not investment advice
</footer>

<script>
(function() {{
  const dates = {chart_dates};
  const risk = {chart_risk};
  const liq = {chart_liq};
  const vrp = {chart_vrp};
  const r3yDates = {regime3y_dates};
  const r3yRisk = {regime3y_risk};

  if (typeof Chart === 'undefined') return;

  // --- 1Y multi-gauge chart ---
  const ctx = document.getElementById('gaugeChart');
  if (ctx) {{
    const chart = new Chart(ctx, {{
      type: 'line',
      data: {{
        labels: dates,
        datasets: [
          {{
            label: 'Risk-On/Off',
            data: risk,
            borderColor: '#58a6ff',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.2,
            yAxisID: 'y'
          }},
          {{
            label: 'Liquidity',
            data: liq,
            borderColor: '#3fb950',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.2,
            yAxisID: 'y'
          }},
          {{
            label: 'VRP',
            data: vrp,
            borderColor: '#d29922',
            backgroundColor: 'transparent',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.2,
            yAxisID: 'y1'
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            callbacks: {{
              title: function(items) {{ return items[0] ? items[0].label : ''; }}
            }}
          }}
        }},
        scales: {{
          x: {{
            ticks: {{ maxTicksLimit: 6, color: '#8b949e', font: {{ size: 10 }} }},
            grid: {{ color: '#21262d' }}
          }},
          y: {{
            position: 'left',
            ticks: {{ color: '#8b949e', font: {{ size: 10 }} }},
            grid: {{ color: '#21262d' }},
            title: {{ display: false }}
          }},
          y1: {{
            position: 'right',
            ticks: {{ color: '#8b949e', font: {{ size: 10 }} }},
            grid: {{ drawOnChartArea: false }},
            title: {{ display: false }}
          }}
        }}
      }}
    }});

    function syncToggles() {{
      chart.data.datasets[0].hidden = !document.getElementById('togRisk').checked;
      chart.data.datasets[1].hidden = !document.getElementById('togLiq').checked;
      chart.data.datasets[2].hidden = !document.getElementById('togVrp').checked;
      chart.update();
    }}
    document.getElementById('togRisk').addEventListener('change', syncToggles);
    document.getElementById('togLiq').addEventListener('change', syncToggles);
    document.getElementById('togVrp').addEventListener('change', syncToggles);
  }}

  // --- Regime strength panel (Option C) with range select + aligned bar ---
  const allDates = {regime3y_dates};
  const allRisk = {regime3y_risk};
  const allRegimes = {regime3y_regimes};
  const colorMap = {{RiskOn: '#238636', Neutral: '#9e6a03', RiskOff: '#da3633'}};
  let regimeChart = null;

  function daysForRange(r) {{
    if (r === '6m') return 126;   // ~6m trading days at step≈5 → use calendar-ish
    if (r === '1y') return 252;
    return 756; // 3y
  }}

  function sliceByRange(rangeKey) {{
    if (!allDates || !allDates.length) return {{dates: [], risk: [], regimes: []}};
    // hist is sampled every ~5 sessions; approximate points from calendar span
    const last = allDates[allDates.length - 1];
    const lastTs = Date.parse(last);
    let cutoffDays = 1100;
    if (rangeKey === '6m') cutoffDays = 185;
    else if (rangeKey === '1y') cutoffDays = 370;
    else cutoffDays = 1100;
    const cutoff = lastTs - cutoffDays * 86400000;
    let i0 = 0;
    for (let i = 0; i < allDates.length; i++) {{
      if (Date.parse(allDates[i]) >= cutoff) {{ i0 = i; break; }}
    }}
    return {{
      dates: allDates.slice(i0),
      risk: allRisk.slice(i0),
      regimes: allRegimes.slice(i0)
    }};
  }}

  function buildBlocks(regimes, dates) {{
    if (!regimes || !regimes.length) return [];
    const blocks = [];
    let cur = regimes[0], start = 0;
    for (let i = 1; i < regimes.length; i++) {{
      if (regimes[i] !== cur) {{
        blocks.push({{reg: cur, a: start, b: i - 1}});
        cur = regimes[i]; start = i;
      }}
    }}
    blocks.push({{reg: cur, a: start, b: regimes.length - 1}});
    const total = regimes.length;
    return blocks.map(function(B) {{
      const w = Math.max(1.2, (B.b - B.a + 1) / total * 100);
      const title = B.reg + ' · ' + dates[B.a] + ' → ' + dates[B.b];
      return {{w: w, reg: B.reg, title: title}};
    }});
  }}

  function renderStrip(regimes, dates, leftPx, rightPx, widthPx) {{
    const strip = document.getElementById('regimeStrip');
    const axis = document.getElementById('regimeDateAxis');
    const wrap = document.querySelector('.regime-strip-wrap');
    if (!strip || !axis || !wrap) return;
    // Align to Chart.js chartArea
    wrap.style.marginLeft = leftPx + 'px';
    wrap.style.marginRight = rightPx + 'px';
    const blocks = buildBlocks(regimes, dates);
    strip.innerHTML = blocks.map(function(B) {{
      return '<div class="reg-block" style="width:' + B.w.toFixed(1) + '%;background:' +
        (colorMap[B.reg] || '#484f58') + '" title="' + B.title + '"></div>';
    }}).join('');
    // Date labels
    axis.innerHTML = '';
    const n = dates.length;
    if (n < 2) return;
    const nLab = Math.min(6, n);
    for (let i = 0; i < nLab; i++) {{
      const idx = Math.round(i * (n - 1) / (nLab - 1));
      const leftPct = idx / (n - 1) * 100;
      const lab = (dates[idx] || '').slice(0, 7);
      const sp = document.createElement('span');
      sp.className = 'reg-date';
      sp.style.left = leftPct.toFixed(1) + '%';
      sp.textContent = lab;
      axis.appendChild(sp);
    }}
  }}

  function drawRegime(rangeKey) {{
    const slice = sliceByRange(rangeKey);
    const ctxR = document.getElementById('regimeStrengthChart');
    if (!ctxR || typeof Chart === 'undefined') return;

    if (regimeChart) {{
      regimeChart.destroy();
      regimeChart = null;
    }}

    regimeChart = new Chart(ctxR, {{
      type: 'line',
      data: {{
        labels: slice.dates,
        datasets: [{{
          label: 'Risk-On/Off',
          data: slice.risk,
          borderColor: '#58a6ff',
          backgroundColor: 'rgba(88, 166, 255, 0.12)',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.15,
          fill: true
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        interaction: {{ mode: 'index', intersect: false }},
        layout: {{ padding: {{ left: 0, right: 0, top: 4, bottom: 0 }} }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            callbacks: {{
              label: function(c) {{
                const v = c.parsed.y;
                let state = 'Neutral';
                if (v > 0.4) state = 'Risk-On';
                else if (v < -0.4) state = 'Risk-Off';
                return 'Score ' + (v != null ? v.toFixed(2) : '–') + ' (' + state + ')';
              }}
            }}
          }}
        }},
        scales: {{
          x: {{
            ticks: {{ maxTicksLimit: 6, color: '#8b949e', font: {{ size: 10 }} }},
            grid: {{ display: false }}
          }},
          y: {{
            min: -2,
            max: 2,
            ticks: {{ color: '#8b949e', font: {{ size: 10 }} }},
            grid: {{
              color: function(ctx) {{
                const v = ctx.tick.value;
                if (v === 0) return '#484f58';
                if (v === 0.4 || v === -0.4 || v === 1 || v === -1) return '#30363d';
                return '#21262d';
              }}
            }}
          }}
        }}
      }},
      plugins: [{{
        id: 'thresholdLines',
        afterDraw: function(chart) {{
          const yScale = chart.scales.y;
          const area = chart.chartArea;
          if (!area) return;
          const ctx = chart.ctx;
          const lines = [
            {{v: 0.4, color: 'rgba(63, 185, 80, 0.5)', dash: [4, 3]}},
            {{v: -0.4, color: 'rgba(248, 81, 73, 0.5)', dash: [4, 3]}},
            {{v: 1.0, color: 'rgba(63, 185, 80, 0.35)', dash: [2, 4]}},
            {{v: -1.0, color: 'rgba(248, 81, 73, 0.35)', dash: [2, 4]}},
            {{v: 0, color: 'rgba(139, 148, 158, 0.6)', dash: []}}
          ];
          ctx.save();
          lines.forEach(function(L) {{
            const y = yScale.getPixelForValue(L.v);
            ctx.beginPath();
            ctx.strokeStyle = L.color;
            ctx.lineWidth = 1;
            ctx.setLineDash(L.dash);
            ctx.moveTo(area.left, y);
            ctx.lineTo(area.right, y);
            ctx.stroke();
          }});
          ctx.restore();
          // Align discrete bar to chartArea
          const canvas = chart.canvas;
          const fullW = canvas.parentElement ? canvas.parentElement.clientWidth : canvas.width;
          const leftPx = area.left;
          const rightPx = Math.max(0, fullW - area.right);
          renderStrip(slice.regimes, slice.dates, leftPx, rightPx, area.right - area.left);
        }}
      }}]
    }});
  }}

  // Range buttons
  const rangeBtns = document.querySelectorAll('#regimeRangeSelect button');
  rangeBtns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      rangeBtns.forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      drawRegime(btn.getAttribute('data-range'));
    }});
  }});

  // Initial draw (3Y)
  drawRegime('3y');

  // Re-align on resize
  window.addEventListener('resize', function() {{
    const active = document.querySelector('#regimeRangeSelect button.active');
    drawRegime(active ? active.getAttribute('data-range') : '3y');
  }});
}})();

</script>
</body>
</html>
"""
    return html


def main():
    print("=== Daily Quant Decision Brief Generator ===")

    try:
        prices = load_prices()
        if prices.empty or len(prices) < 50:
            prices = download_prices(period="5y")
    except Exception as e:
        print(f"Load failed ({e}), downloading...")
        prices = download_prices(period="5y")

    print(f"Prices shape: {prices.shape}")

    metrics = trailing_metrics(prices)
    gauges = run_all_gauges(prices)
    themes = compute_theme_metrics(prices)
    hist = compute_gauge_history(prices, lookback_days=756, step=5)

    risk_score = gauges.get("risk_on_off", {}).get("score", 0) or 0
    slope = gauges.get("yield_curve", {}).get("score")
    vrp_score = gauges.get("vol_risk_premium", {}).get("score")

    analogs = find_similar_regimes(prices, risk_score, slope, vrp_score)

    print("Gauges:", {k: (v.get("label") if isinstance(v, dict) else v) for k, v in gauges.items()})
    print("Analogs episodes:", analogs.get("n_episodes"), "|", analogs.get("regime"))
    print("History points:", len(hist.get("dates", [])))

    print("Fetching policy pricing (Kalshi / Polymarket / ZQ)...")
    try:
        policy = collect_policy_pricing()
        print("Policy venues:", policy.get("venues_ok"), "basis", policy.get("basis_hike"))
    except Exception as e:
        print(f"policy_pricing failed: {e}")
        policy = {"ok": False}

    html = build_html(prices, metrics, gauges, themes, analogs, hist, policy=policy)

    out_dir = Path(__file__).resolve().parents[2] / "output"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = out_dir / f"brief_{stamp}.html"
    out_path.write_text(html, encoding="utf-8")
    (out_dir / "latest.html").write_text(html, encoding="utf-8")

    print(f"\nReport → {out_path}")
    return str(out_path)


if __name__ == "__main__":
    main()
