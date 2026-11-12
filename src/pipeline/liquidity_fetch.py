"""
Live liquidity / funding series for the Liquidity gauge.
Pulls public FRED CSVs (no API key) for SOFR, IORB, HY OAS, TGA, Fed assets, ON RRP.
Computes SOFR-IORB spread and net liquidity (WALCL - TGA - RRP).
Persists latest snapshot so the report always uses freshly researched values.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "liquidity"
DATA_DIR.mkdir(parents=True, exist_ok=True)

def _get_csv(series_id: str, timeout: int = 20) -> list[tuple[str, float]]:
    """Return list of (date, value) from FRED public CSV, newest last."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    rows = []
    for ln in r.text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("DATE") or ln.startswith("observation_date"):
            continue
        parts = ln.split(",")
        if len(parts) >= 2 and parts[1] not in (".", "", "nan"):
            try:
                rows.append((parts[0], float(parts[1])))
            except ValueError:
                continue
    return rows

def _latest(rows: list[tuple[str, float]]) -> tuple[str, float] | None:
    return rows[-1] if rows else None

def fetch_liquidity_series() -> dict:
    """
    Fetch live series and return a dict suitable for liquidity_gauge(extra=...).
    Keys: sofr_iorb_bp, hy_oas_pct, tga_bn, net_liquidity_tn, plus metadata.
    """
    out = {
        "ok": False,
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {},
        "errors": [],
    }
    try:
        sofr_rows = _get_csv("SOFR")
        iorb_rows = _get_csv("IORB")
        hy_rows = _get_csv("BAMLH0A0HYM2")
        tga_rows = _get_csv("WDTGAL")          # Wednesday TGA level
        walcl_rows = _get_csv("WALCL")         # Fed total assets
        rrp_rows = _get_csv("RRPONTSYD")       # ON RRP
    except Exception as e:
        out["errors"].append(f"fetch: {type(e).__name__}: {e}")
        return out

    sofr = _latest(sofr_rows)
    iorb = _latest(iorb_rows)
    hy = _latest(hy_rows)
    tga = _latest(tga_rows)
    walcl = _latest(walcl_rows)
    rrp = _latest(rrp_rows)

    if sofr:
        out["sources"]["SOFR"] = {"value": sofr[1], "as_of": sofr[0]}
    if iorb:
        out["sources"]["IORB"] = {"value": iorb[1], "as_of": iorb[0]}
    if hy:
        out["sources"]["HY_OAS"] = {"value": hy[1], "as_of": hy[0]}
    if tga:
        out["sources"]["TGA"] = {"value": tga[1], "as_of": tga[0]}
    if walcl:
        out["sources"]["WALCL"] = {"value": walcl[1], "as_of": walcl[0]}
    if rrp:
        out["sources"]["RRP"] = {"value": rrp[1], "as_of": rrp[0]}

    # SOFR - IORB in bp
    if sofr and iorb:
        spread_bp = round((sofr[1] - iorb[1]) * 100, 1)
        out["sofr_iorb_bp"] = spread_bp
        out["sofr"] = sofr[1]
        out["iorb"] = iorb[1]

    if hy:
        out["hy_oas_pct"] = round(hy[1], 2)

    # TGA in $B (FRED WDTGAL is in millions)
    if tga:
        out["tga_bn"] = round(tga[1] / 1000.0, 1)

    # Net liquidity = Fed assets - TGA - ON RRP (all in $T)
    if walcl and tga and rrp:
        # WALCL is in millions, TGA in millions, RRP in billions? Check units.
        # WALCL: millions of dollars
        # WDTGAL: millions of dollars
        # RRPONTSYD: billions of dollars
        net_tn = (walcl[1] - tga[1]) / 1_000_000.0 - rrp[1] / 1_000.0
        out["net_liquidity_tn"] = round(net_tn, 2)

    out["ok"] = bool(out.get("sofr_iorb_bp") is not None and out.get("hy_oas_pct") is not None)
    return out

def collect_liquidity(persist: bool = True) -> dict:
    """Fetch, optionally persist, and return the extra dict for the gauge."""
    snap = fetch_liquidity_series()
    if persist:
        try:
            DATA_DIR.joinpath("latest.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
            with DATA_DIR.joinpath("history.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "as_of": snap["as_of"],
                    "sofr_iorb_bp": snap.get("sofr_iorb_bp"),
                    "hy_oas_pct": snap.get("hy_oas_pct"),
                    "tga_bn": snap.get("tga_bn"),
                    "net_liquidity_tn": snap.get("net_liquidity_tn"),
                    "ok": snap["ok"],
                }) + "\n")
        except Exception as e:
            print(f"liquidity persist failed: {e}")
    return snap
