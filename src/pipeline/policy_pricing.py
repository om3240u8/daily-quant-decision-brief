"""Render + assemble FOMC policy card. Fetch helpers live in policy_fetch."""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from pathlib import Path

from src.pipeline.policy_fetch import (
    next_fomc, days_to, fetch_kalshi, fetch_polymarket, fetch_effr, fetch_zq,
    invert_meeting, _event_blend,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "policy_pricing"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def collect_policy_pricing(today=None):
    today = today or date.today()
    meeting = next_fomc(today)
    kalshi, poly, effr, zq = fetch_kalshi(meeting), fetch_polymarket(meeting), fetch_effr(), fetch_zq(meeting)
    inv, event = invert_meeting(zq, effr, meeting), _event_blend(kalshi, poly)
    basis_ok = bool(inv.get("ok") and event["hike"] is not None)
    venues_ok = [n for n, ok in (("kalshi", kalshi.get("ok")), ("polymarket", poly.get("ok")), ("zq", inv.get("ok"))) if ok]
    snap = {"ok": bool(venues_ok), "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "meeting": meeting.isoformat(), "days_ahead": days_to(meeting, today),
            "kalshi": kalshi, "polymarket": poly, "effr": effr, "zq": zq, "zq_implied": inv, "event": event,
            "basis_hike": (inv["p_hike"] - event["hike"]) if basis_ok else None, "basis_ok": basis_ok,
            "venues_ok": venues_ok, "label": "ZQ-implied (not CME FedWatch)"}
    try:
        DATA_DIR.joinpath("latest.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
        with DATA_DIR.joinpath("history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"as_of": snap["as_of"], "meeting": snap["meeting"], "basis_hike": snap["basis_hike"],
                                "p_hold_kalshi": kalshi.get("hold"), "p_hike_kalshi": kalshi.get("hike_25"),
                                "p_hold_poly": poly.get("hold"), "p_hike_poly": poly.get("hike_25"),
                                "p_hike_zq": inv.get("p_hike"), "implied_bp": inv.get("implied_bp"),
                                "zq_px": zq.get("price"), "venues_ok": venues_ok}) + "\n")
    except Exception as e:
        print(f"policy_pricing persist failed: {e}")
    return snap

def _pct(x):
    return "–" if x is None else f"{100.0 * float(x):.0f}%"

def _basis_chip(basis, ok):
    if not ok or basis is None:
        return ("#8b949e", "n/a")
    bp = 100.0 * basis
    if abs(bp) < 5: return ("#3fb950", f"{bp:+.0f}pp quiet")
    if abs(bp) < 10: return ("#d29922", f"{bp:+.0f}pp watch")
    return ("#f85149", f"{bp:+.0f}pp dislocation")

def _empty_venue():
    return {"ok": False, "hold": None, "hike_25": None, "hike_50": None, "cut_25": None, "cut_50": None}

def policy_insight(snap):
    if not snap or not snap.get("ok"):
        return "Policy card incomplete — event books / ZQ did not all clear health checks."
    k, p, inv = snap.get("kalshi") or _empty_venue(), snap.get("polymarket") or _empty_venue(), snap.get("zq_implied") or {}
    parts = [f"Next FOMC {snap.get('meeting')} ({snap.get('days_ahead')}d)."]
    if k.get("ok") and p.get("ok"):
        parts.append(f"Event books: Kalshi hold {_pct(k.get('hold'))} / hike {_pct(k.get('hike_25'))}; Poly hold {_pct(p.get('hold'))} / hike {_pct(p.get('hike_25'))}.")
    elif k.get("ok"):
        parts.append(f"Kalshi hold {_pct(k.get('hold'))} / hike {_pct(k.get('hike_25'))} (Poly missing).")
    elif p.get("ok"):
        parts.append(f"Poly hold {_pct(p.get('hold'))} / hike {_pct(p.get('hike_25'))} (Kalshi missing).")
    if inv.get("ok"):
        parts.append(f"ZQ-implied path +{inv.get('implied_bp')}bp → bucket hike {_pct(inv.get('p_hike'))} (not CME FedWatch).")
    basis = snap.get("basis_hike")
    if snap.get("basis_ok") and basis is not None:
        note = "tight" if abs(basis) < 0.05 else ("watch" if abs(basis) < 0.10 else "wide")
        parts.append(f"Basis ZQ\u2212event hike {100*basis:+.0f}pp ({note}). Do not treat the ZQ bucket as P(statement).")
    return " ".join(parts)

def policy_scenarios(snap):
    snap = snap or {}
    ev, inv = snap.get("event") or {}, snap.get("zq_implied") or {}
    hold_p = ev.get("hold") if ev.get("hold") is not None else (inv.get("p_hold") or 0.50)
    hike_p = ev.get("hike") if ev.get("hike") is not None else (inv.get("p_hike") or 0.40)
    implied_bp = inv.get("implied_bp")
    raw = [hold_p, hike_p, 0.12, 0.08]
    s = sum(raw) or 1.0
    w = [x / s for x in raw]
    later = (f"ZQ strip still prices ~{implied_bp:+.0f}bp into this meeting month and further tightening by year-end. Hold in Sep does not kill the path."
             if implied_bp is not None else "ZQ path still tighter by year-end even if September is a hold.")
    return [
        {"title": "Hold at Sep meeting", "p": w[0], "text": "Statement unchanged 15–16 Sep. Residual risk is SEP / Warsh presser, not the funds rate."},
        {"title": "+25bp at Sep meeting", "p": w[1], "text": "Target 3.75–4.00%. Front end cheapens; USD/oil already in the price if the ZQ–event basis is tight."},
        {"title": "Skip Sep, hike by Dec", "p": w[2], "text": later},
        {"title": "Data / geo shock", "p": w[3], "text": "NFP/CPI miss or oil spike re-opens a 10pp+ basis. Event books usually move first on the headline; ZQ moves on the path."},
    ]

def policy_card_html(snap):
    if not snap:
        return "<p class='footnote'>Policy pricing unavailable.</p>"
    k, p, inv = snap.get("kalshi") or _empty_venue(), snap.get("polymarket") or _empty_venue(), snap.get("zq_implied") or {}
    zq, effr = snap.get("zq") or {}, snap.get("effr") or {}
    chip_color, chip_txt = _basis_chip(snap.get("basis_hike"), snap.get("basis_ok"))
    venues = ", ".join(snap.get("venues_ok") or []) or "none"
    stale = "" if snap.get("ok") else " \u00b7 INCOMPLETE"
    avg = f"{zq['implied_avg']:.3f}%" if zq.get("implied_avg") is not None else "\u2013"
    return f"""
    <div class='policy-card'>
      <div class='policy-head'>
        <div>
          <div class='label'>FOMC {snap.get('meeting')} \u00b7 {snap.get('days_ahead')}d</div>
          <div class='policy-sub'>Event books live \u00b7 ZQ T-1 Yahoo \u00b7 {snap.get('label')}</div>
        </div>
        <div class='basis-chip' style='background:{chip_color}22;color:{chip_color};border:1px solid {chip_color}55'>{chip_txt}</div>
      </div>
      <div class='table-scroll'>
      <table>
        <thead><tr><th>Venue</th><th>Hold</th><th>+25bp</th><th>\u226550bp / cut</th><th>Object</th></tr></thead>
        <tbody>
          <tr><td>Kalshi</td><td>{_pct(k.get('hold'))}</td><td>{_pct(k.get('hike_25'))}</td><td>{_pct(k.get('hike_50'))} / {_pct(k.get('cut_25'))}</td><td>statement</td></tr>
          <tr><td>Polymarket</td><td>{_pct(p.get('hold'))}</td><td>{_pct(p.get('hike_25'))}</td><td>{_pct(p.get('hike_50'))} / {_pct(p.get('cut_25'))}</td><td>statement</td></tr>
          <tr><td>ZQ-implied</td><td>{_pct(inv.get('p_hold'))}</td><td>{_pct(inv.get('p_hike'))}</td><td>{_pct(inv.get('p_cut'))}</td><td>month-avg EFFR</td></tr>
        </tbody>
      </table>
      </div>
      <p class='footnote'>ZQ {zq.get('ticker') or '\u2013'} last {zq.get('price') if zq.get('price') is not None else '\u2013'} \u2192 implied avg {avg} \u00b7 EFFR {effr.get('effr') if effr.get('effr') is not None else '\u2013'}% ({effr.get('as_of') or '\u2013'}) \u00b7 invert {inv.get('implied_bp') if inv.get('implied_bp') is not None else '\u2013'} bp \u00b7 venues {venues}{stale} \u00b7 Poly slug {p.get('slug') or '\u2013'}</p>
    </div>
    """
