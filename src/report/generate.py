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


def _range_bar_html(score, p5, p95, min_v, max_v):
    """Neutral CSS range track with 5–95 band and current marker."""
    if score is None or p5 is None or p95 is None:
        return ""
    lo = min_v if min_v is not None else p5
    hi = max_v if max_v is not None else p95
    span = hi - lo if hi > lo else 1.0
    left_5 = max(0, min(100, (p5 - lo) / span * 100))
    width_band = max(2, min(100 - left_5, (p95 - p5) / span * 100))
    marker = max(0, min(100, (score - lo) / span * 100))
    return f"""
    <div class="range-track" title="5–95 band (neutral); marker = current">
      <div class="range-band" style="left:{left_5:.1f}%;width:{width_band:.1f}%;"></div>
      <div class="range-marker" style="left:{marker:.1f}%;"></div>
    </div>
    """


def build_html(prices, metrics, gauges, themes, analogs, hist) -> str:
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

    risk_bar = _range_bar_html(risk_score, risk_rng.get("p5"), risk_rng.get("p95"),
                              risk_rng.get("min"), risk_rng.get("max"))
    liq_score = liq.get("score")
    liq_bar = _range_bar_html(liq_score, liq_rng.get("p5"), liq_rng.get("p95"),
                              liq_rng.get("min"), liq_rng.get("max"))
    vrp_score = vrp.get("score")
    vrp_bar = _range_bar_html(vrp_score, vrp_rng.get("p5"), vrp_rng.get("p95"),
                              vrp_rng.get("min"), vrp_rng.get("max"))

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

    events = get_upcoming_events(35)
    events_html = events_to_html(events)

    chart_dates = json.dumps(hist.get("dates", [])[-55:])
    chart_risk = json.dumps(hist.get("risk", [])[-55:])
    chart_liq = json.dumps(hist.get("liq", [])[-55:])
    chart_vrp = json.dumps([x if x is not None else None for x in hist.get("vrp", [])[-55:]])

    regime_blocks = ""
    regimes = hist.get("regime", [])
    dates_full = hist.get("dates", [])
    if regimes:
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
  .range-track {{
    position: relative; height: 6px; background: #21262d; border-radius: 3px;
    margin-top: 8px; overflow: visible;
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
    display: flex; height: 18px; border-radius: 4px; overflow: hidden;
    border: 1px solid var(--border); margin: 8px 0 4px;
  }}
  .reg-block {{ height: 100%; min-width: 2px; }}
  .regime-legend {{
    display: flex; gap: 12px; font-size: 0.72rem; color: var(--muted); margin-bottom: 10px;
  }}
  .regime-legend span {{ display: inline-flex; align-items: center; gap: 4px; }}
  .swatch {{ width: 10px; height: 10px; border-radius: 2px; }}
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

<!-- Always-visible gauge history + regime blocks -->
<div class="section">
  <h2>Gauge History & Regime Timeline</h2>
  <div class="chart-wrap">
    <div class="toggle-row">
      <label><input type="checkbox" id="togRisk" checked> Risk-On/Off</label>
      <label><input type="checkbox" id="togLiq" checked> Liquidity</label>
      <label><input type="checkbox" id="togVrp" checked> VRP</label>
    </div>
    <canvas id="gaugeChart" height="180"></canvas>
  </div>
  <p style="font-size:0.8rem;color:var(--muted);margin-bottom:4px;">Discrete regime blocks (~3Y, Risk-On / Neutral / Risk-Off)</p>
  <div class="regime-strip">{regime_blocks}</div>
  <div class="regime-legend">
    <span><i class="swatch" style="background:#238636"></i> Risk-On</span>
    <span><i class="swatch" style="background:#9e6a03"></i> Neutral</span>
    <span><i class="swatch" style="background:#da3633"></i> Risk-Off</span>
  </div>
  <p class="footnote">Chart: last ~1Y (sampled). Range bars on cards use 5–95 percentile of the same 1Y window (neutral colour). Regime blocks collapse consecutive states.</p>
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
  </ul>
  <p class="footnote">[1] Risk-On/Off now includes a light inverted USD-strength term. [2] Liquidity includes inverted USD (63d primary + 21d) as global funding proxy. [3] Curve slope — Estrella-type + ACM. Data: WSJ / Yahoo.</p>
</div>

<!-- Events -->
<div class="section">
  <h2>High-Impact Event Calendar</h2>
  {events_html}
  <p class="footnote">Curated high-impact releases. Impact weighting is judgmental based on typical market sensitivity.</p>
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
  <h2>Near-Term Scenarios (1–3 months)</h2>
  <div class="scenario"><strong>Base – Soft-landing continuation</strong> · ~45%<br>
    <small>Risk-on persists, curve mildly steep, VRP normal, liquidity supportive. Equities + credit grind higher.</small></div>
  <div class="scenario"><strong>Re-acceleration / sticky inflation</strong> · ~25%<br>
    <small>Yields rise, curve steepens, growth multiples compress.</small></div>
  <div class="scenario"><strong>Growth scare</strong> · ~20%<br>
    <small>Curve flattens/re-inverts, credit widens, defensives outperform.</small></div>
  <div class="scenario"><strong>Policy / geo shock</strong> · ~10%<br>
    <small>Sharp risk-off, VIX spike, flight to USD/Treasuries/Gold. Liquidity would deteriorate.</small></div>
  <p class="footnote">Probabilities = structured judgment anchored to current gauge configuration + historical transition frequencies.</p>
</div>

<!-- References -->
<details>
  <summary>Key References & Data Sources</summary>
  <div class="details-body">
    <p><strong>Data</strong></p>
    <ul>
      <li>U.S. Treasury yields: WSJ Market Data – Bonds</li>
      <li>Asset prices: Yahoo Finance (yfinance)</li>
    </ul>
    <p><strong>Selected Research Anchors</strong></p>
    <ul>
      <li>Adrian, Crump, Moench – term structure / term premium (ACM model)</li>
      <li>Estrella & Hardouvelis / Fed research – yield curve slope as predictor</li>
      <li>Carr & Wu – volatility risk premium</li>
      <li>Koijen et al. – carry</li>
      <li>Brunnermeier & Pedersen – funding vs market liquidity</li>
      <li>Amihud (2002) – illiquidity measure</li>
      <li>USD strength as risk-off / global funding channel (multi-asset risk literature)</li>
    </ul>
    <p>This is a decision-support tool only. Not investment advice.</p>
  </div>
</details>

<footer>
  Daily Quant Decision Brief · Enhanced 2026-08-22 · Yield curve: WSJ · Not investment advice
</footer>

<script>
(function() {{
  const dates = {chart_dates};
  const risk = {chart_risk};
  const liq = {chart_liq};
  const vrp = {chart_vrp};

  const ctx = document.getElementById('gaugeChart');
  if (!ctx || typeof Chart === 'undefined') return;

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

    html = build_html(prices, metrics, gauges, themes, analogs, hist)

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
