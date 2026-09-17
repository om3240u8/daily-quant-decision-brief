"""FOMC policy pricing: Kalshi + Polymarket vs ZQ-implied path. No CME FedWatch API."""
from __future__ import annotations
import json, math, re, calendar
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "policy_pricing"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "DailyQuantBrief/1.0 (+research)"}
FOMC_ANNOUNCEMENTS = [
    date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
    date(2027, 1, 28), date(2027, 3, 18), date(2027, 4, 29),
    date(2027, 6, 17), date(2027, 7, 29), date(2027, 9, 16),
    date(2027, 10, 28), date(2027, 12, 9),
]
KALSHI_MONTH = {1:"JAN",2:"FEB",3:"MAR",4:"APR",5:"MAY",6:"JUN",7:"JUL",8:"AUG",9:"SEP",10:"OCT",11:"NOV",12:"DEC"}
ZQ_MONTH_CODE = {1:"F",2:"G",3:"H",4:"J",5:"K",6:"M",7:"N",8:"Q",9:"U",10:"V",11:"X",12:"Z"}
POLY_SLUG_HINTS = {
    (2026, 9): ["fed-decision-in-september-762", "fed-decision-in-september"],
    (2026, 10): ["fed-decision-in-october", "fed-decision-in-october-2026"],
    (2026, 12): ["fed-decision-in-december", "fed-decision-in-december-2026"],
}

def _get_json(url, timeout=20):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))

def _get_text(url, timeout=20):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")

def next_fomc(today=None):
    today = today or date.today()
    # After ~18:00 UTC on announcement day the statement is out — roll to the next meeting.
    now = datetime.now(timezone.utc)
    for d in FOMC_ANNOUNCEMENTS:
        if d > today:
            return d
        if d == today and now.hour < 18:
            return d
    return FOMC_ANNOUNCEMENTS[-1]

def days_to(d, today=None):
    return (d - (today or date.today())).days

def _mid(bid, ask, last):
    def f(x):
        try:
            return float(x) if x not in (None, "", "0", "0.0000") else None
        except (TypeError, ValueError):
            return None
    b, a, last_f = f(bid), f(ask) if ask not in (None, "") else None, f(last)
    if b is not None and a is not None and a > 0:
        return a if b <= 0 else (b + a) / 2.0
    return last_f

def _clip01(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return max(0.0, min(1.0, float(x)))

def fetch_kalshi(meeting):
    yy, mon = str(meeting.year)[-2:], KALSHI_MONTH[meeting.month]
    prefix = f"KXFEDDECISION-{yy}{mon}-"
    wanted = {f"{prefix}H0":"hold", f"{prefix}H25":"hike_25", f"{prefix}H26":"hike_50", f"{prefix}C25":"cut_25", f"{prefix}C26":"cut_50"}
    out = {"ok": False, "venue": "kalshi", "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "tickers": {}, "hold": None, "hike_25": None, "hike_50": None, "cut_25": None, "cut_50": None, "error": None}
    try:
        data = _get_json("https://external-api.kalshi.com/trade-api/v2/markets?series_ticker=KXFEDDECISION&status=open&limit=200")
        for m in data.get("markets") or []:
            t = m.get("ticker") or ""
            if t in wanted:
                spec = {"ticker": t, "p": _clip01(_mid(m.get("yes_bid_dollars"), m.get("yes_ask_dollars"), m.get("last_price_dollars"))),
                        "bid": m.get("yes_bid_dollars"), "ask": m.get("yes_ask_dollars"), "last": m.get("last_price_dollars")}
                out[wanted[t]] = spec["p"]
                out["tickers"][wanted[t]] = spec
        out["ok"] = out["hold"] is not None or out["hike_25"] is not None
        if not out["ok"]:
            out["error"] = f"no open contracts matching {prefix}*"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out

def _poly_search_slug(meeting):
    month_name = meeting.strftime("%B")
    for q in [f"Fed decision in {month_name} {meeting.year}", f"Fed Decision in {month_name}"]:
        try:
            data = _get_json("https://gamma-api.polymarket.com/public-search?" + urlencode({"q": q}))
            events = data.get("events") if isinstance(data, dict) else data
            for e in events or []:
                slug, title = (e.get("slug") or ""), (e.get("title") or "")
                blob = (slug + title).lower()
                if "fed" not in blob or month_name.lower() not in blob:
                    continue
                end = e.get("endDate") or ""
                if str(meeting.year) in end or str(meeting.year) in slug or re.search(r"-\d+$", slug):
                    return slug
        except Exception:
            continue
    hints = POLY_SLUG_HINTS.get((meeting.year, meeting.month), [])
    return hints[0] if hints else None

def _classify_poly_outcome(label):
    s = (label or "").lower()
    if "50" in s and ("increase" in s or "hike" in s):
        return "hike_50"
    if "50" in s and ("decrease" in s or "cut" in s):
        return "cut_50"
    if "25" in s and ("increase" in s or "hike" in s):
        return "hike_25"
    if "25" in s and ("decrease" in s or "cut" in s):
        return "cut_25"
    if "no change" in s or "hold" in s or "unchanged" in s:
        return "hold"
    return None

def fetch_polymarket(meeting):
    out = {"ok": False, "venue": "polymarket", "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "slug": None, "hold": None, "hike_25": None, "hike_50": None, "cut_25": None, "cut_50": None, "volume": None, "error": None}
    slugs, seen = [], set()
    discovered = _poly_search_slug(meeting)
    if discovered:
        slugs.append(discovered)
    slugs.extend(POLY_SLUG_HINTS.get((meeting.year, meeting.month), []))
    for slug in slugs:
        if not slug or slug in seen:
            continue
        seen.add(slug)
        try:
            data = _get_json(f"https://gamma-api.polymarket.com/events?slug={slug}")
            if isinstance(data, list):
                data = data[0] if data else {}
            if not data:
                continue
            end = data.get("endDate") or ""
            if end and str(meeting.year - 1) in end and str(meeting.year) not in end:
                continue
            out["slug"] = data.get("slug") or slug
            out["volume"] = data.get("volume")
            for m in data.get("markets") or []:
                key = _classify_poly_outcome(m.get("groupItemTitle") or m.get("question") or "")
                if not key:
                    continue
                prices = m.get("outcomePrices")
                if isinstance(prices, str):
                    try:
                        prices = json.loads(prices)
                    except Exception:
                        prices = None
                if isinstance(prices, list) and prices:
                    try:
                        out[key] = _clip01(float(prices[0]))
                    except (TypeError, ValueError):
                        pass
            out["ok"] = out["hold"] is not None or out["hike_25"] is not None
            if out["ok"]:
                return out
        except Exception as e:
            out["error"] = f"{type(e).__name__}: {e}"
    if not out["ok"] and not out["error"]:
        out["error"] = "no matching open Polymarket Fed event"
    return out

def fetch_effr():
    out = {"ok": False, "effr": None, "target_upper": 3.75, "as_of": None, "error": None}
    try:
        rows = [ln.strip() for ln in _get_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=EFFR").splitlines() if ln.strip() and not ln.startswith("DATE")]
        for ln in reversed(rows):
            parts = ln.split(",")
            if len(parts) >= 2 and parts[1] not in (".", ""):
                out["effr"], out["as_of"], out["ok"] = float(parts[1]), parts[0], True
                break
    except Exception as e:
        out["error"] = f"EFFR {type(e).__name__}: {e}"
    try:
        rows = [ln.strip() for ln in _get_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU").splitlines() if ln.strip() and not ln.startswith("DATE")]
        for ln in reversed(rows):
            parts = ln.split(",")
            if len(parts) >= 2 and parts[1] not in (".", ""):
                out["target_upper"] = float(parts[1])
                break
    except Exception:
        pass
    if not out["ok"]:
        out["effr"] = 3.63
        out["error"] = (out.get("error") or "") + " | using fallback EFFR 3.63"
    return out

def _zq_ticker(meeting):
    return f"ZQ{ZQ_MONTH_CODE[meeting.month]}{str(meeting.year)[-2:]}.CBT"

def add_month(d):
    """First day of the calendar month after d (used only for ZQ month code)."""
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)

# Implemented target *upper* after printed decisions. Used when FRED DFEDTARU lags.
IMPLEMENTED_TARGET_UPPER = {
    date(2026, 9, 16): 4.00,
}

def expected_pre_rate(effr, today=None):
    """
    Rate assumed to print on pre-meeting days of the *next* meeting month.
    Prefer FRED EFFR when it sits inside the corridor; switch to target mid
    when EFFR is stale vs a printed implementation.
    """
    today = today or date.today()
    raw = effr.get("effr") if effr else None
    fred_upper = effr.get("target_upper") if effr else None
    implemented = None
    now = datetime.now(timezone.utc)
    for d, u in sorted(IMPLEMENTED_TARGET_UPPER.items()):
        if d < today or (d == today and now.hour >= 18):
            implemented = u
    uppers = [x for x in (fred_upper, implemented) if x is not None]
    upper = max(uppers) if uppers else None
    mid = (upper - 0.125) if upper is not None else None
    if mid is not None and (raw is None or (mid - float(raw)) > 0.12):
        return float(mid), "target_mid"
    if raw is None:
        return None, "missing"
    return float(raw), "effr"

def fetch_zq(meeting):
    out = {"ok": False, "ticker": _zq_ticker(meeting), "price": None, "implied_avg": None, "as_of": None, "error": None}
    tickers = [out["ticker"], f"ZQ{ZQ_MONTH_CODE[meeting.month]}{str(meeting.year)[-2:]}"]
    errors = []
    try:
        import yfinance as yf
        for t in tickers:
            try:
                hist = yf.Ticker(t).history(period="10d")
            except Exception as e:
                errors.append(f"yf {t}: {e}"); hist = None
            if hist is None or getattr(hist, "empty", True):
                continue
            px = float(hist["Close"].dropna().iloc[-1])
            ts = str(hist.index[-1].date()) if hasattr(hist.index[-1], "date") else str(hist.index[-1])
            if 80 < px < 100:
                out.update(ticker=t, price=px, implied_avg=100.0-px, as_of=ts, ok=True)
                return out
    except Exception as e:
        errors.append(f"yfinance: {e}")
    for t in tickers:
        try:
            data = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/" + t + "?range=10d&interval=1d")
            res = ((data.get("chart") or {}).get("result") or [None])[0]
            if not res:
                continue
            closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            ts_list = res.get("timestamp") or []
            px = next((c for c in reversed(closes) if c is not None), None)
            ts = datetime.fromtimestamp(ts_list[-1], tz=timezone.utc).date().isoformat() if ts_list else None
            if px is not None and 80 < float(px) < 100:
                out.update(ticker=t, price=float(px), implied_avg=100.0-float(px), as_of=ts, ok=True)
                return out
        except Exception as e:
            errors.append(f"chart {t}: {e}")
    out["error"] = "; ".join(errors) or f"no usable Yahoo print for {tickers}"
    return out

def invert_meeting(zq, effr, meeting, zq_next=None):
    """
    Recover a post-meeting EFFR path from 30-day ZQ.

    same_month: R_post = (n*R_m - n_pre*R_pre) / n_post   [identified iff n_post >= 8]
    next_month: R_post = R_{m+1}                           [used when n_post is tiny]
    """
    out = {
        "ok": False, "pre_rate": None, "post_rate": None, "implied_bp": None,
        "p_hike": None, "p_hold": None, "p_cut": None, "n_pre": None, "n_post": None,
        "error": None, "method": None, "pre_source": None,
        "r_meeting_month": None, "r_next_month": None, "spread_on_bp": None,
        "same_month_bp": None, "zq_next_ticker": None,
    }
    n = calendar.monthrange(meeting.year, meeting.month)[1]
    # Announcement day remains pre; funds change next calendar day.
    n_pre = min(max(meeting.day, 1), n)
    n_post = max(n - n_pre, 1)
    out["n_pre"], out["n_post"] = n_pre, n_post

    pre, pre_src = expected_pre_rate(effr)
    out["pre_source"] = pre_src
    if pre is None:
        out["error"] = "pre-rate missing"
        return out
    out["pre_rate"] = round(float(pre), 4)

    r_m = float(zq["implied_avg"]) if zq and zq.get("ok") and zq.get("implied_avg") is not None else None
    r_n = float(zq_next["implied_avg"]) if zq_next and zq_next.get("ok") and zq_next.get("implied_avg") is not None else None
    out["r_meeting_month"] = None if r_m is None else round(r_m, 4)
    out["r_next_month"] = None if r_n is None else round(r_n, 4)
    out["zq_next_ticker"] = (zq_next or {}).get("ticker")
    if r_m is not None and r_n is not None:
        out["spread_on_bp"] = round(100.0 * (r_n - r_m), 2)

    same_post = same_bp = None
    if r_m is not None:
        same_post = (n * r_m - n_pre * float(pre)) / n_post
        same_bp = 100.0 * (same_post - float(pre))
        out["same_month_bp"] = round(same_bp, 2)

    use_next = (n_post < 8 and r_n is not None) or (r_m is None and r_n is not None)
    if use_next:
        method, post, implied_bp = "next_month", r_n, 100.0 * (r_n - float(pre))
    elif r_m is not None and n_post >= 8:
        method, post, implied_bp = "same_month", same_post, same_bp
    else:
        out["error"] = f"ZQ invert unidentified n_post={n_post} r_m={r_m} r_n={r_n}"
        return out

    if abs(implied_bp) > 50:
        out.update(method=method, post_rate=round(float(post), 4), implied_bp=round(implied_bp, 2),
                   error=f"ZQ invert unstable method={method} implied_bp={implied_bp:.1f}")
        return out

    if implied_bp >= 0:
        p_hike, p_cut = max(0.0, min(1.0, implied_bp / 25.0)), 0.0
        p_hold = max(0.0, 1.0 - p_hike)
    else:
        p_cut, p_hike = max(0.0, min(1.0, abs(implied_bp) / 25.0)), 0.0
        p_hold = max(0.0, 1.0 - p_cut)

    out.update(ok=True, method=method, post_rate=round(float(post), 4), implied_bp=round(implied_bp, 2),
               p_hike=round(p_hike, 4), p_hold=round(p_hold, 4), p_cut=round(p_cut, 4))
    return out

def _event_blend(kalshi, poly):
    keys = ["hold", "hike_25", "hike_50", "cut_25", "cut_50"]
    blend = {k: None for k in keys}
    for k in keys:
        vals = []
        if kalshi.get("ok") and kalshi.get(k) is not None: vals.append(kalshi[k])
        if poly.get("ok") and poly.get(k) is not None: vals.append(poly[k])
        if vals: blend[k] = sum(vals) / len(vals)
    hike = None
    if blend["hike_25"] is not None or blend["hike_50"] is not None:
        hike = (blend["hike_25"] or 0) + (blend["hike_50"] or 0)
    return {"n_ok": int(bool(kalshi.get("ok"))) + int(bool(poly.get("ok"))), "probs": blend, "hike": hike, "hold": blend["hold"]}
