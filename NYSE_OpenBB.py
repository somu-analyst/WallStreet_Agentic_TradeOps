"""
NYSE_OpenBB.py  —  OpenBB-based options fetcher (BENCHMARK / A-B test vs NYSE_YFin.py)
=====================================================================================
Purpose: measure whether OpenBB (esp. the CBOE provider, which returns a ticker's
FULL option chain in ONE call) plus parallelism beats the current yfinance pipeline
(per-expiry calls, 1 ticker at a time, 1s sleep/ticker -> 3-5 hr).

Two levers this script tests vs NYSE_YFin.py:
  1) CBOE full-chain-in-one-call  (vs yfinance option_chain() per expiry)
  2) ThreadPoolExecutor parallelism + NO inter-ticker sleep

SAFETY: writes to a SEPARATE DATABASE FILE (US_data_openbb_test.db) — the production
US_data.db is never opened for writing, so this cannot hurt it. No production-write path.

!!! UNTESTED against a live OpenBB install (openbb was not installed when written).
On first run you may need to tweak the column-name normalisation in _normalize_chain()
to match your OpenBB version's schema — the code prints the raw columns if it can't map.

Install first:   pip install openbb openbb-cboe
Run (quick test):  python NYSE_OpenBB.py --limit 50 --workers 8
Run (full):        python NYSE_OpenBB.py --workers 8
Compare provider:  python NYSE_OpenBB.py --limit 50 --provider yfinance
"""
import os
import time
import argparse
import sqlite3
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

# ---- config (mirrors NYSE_YFin.py) ------------------------------------------
DATA_DIR = r"C:\Users\srini\Options_chain_data"
US_CHARTS_DIR = os.path.join(DATA_DIR, "US_CHARTS")
UNIVERSE_FILE = os.path.join(US_CHARTS_DIR, "ticker_universe.xlsx")
UNIVERSE_SHEET_ACTIVE = "ticker_universe"
# ISOLATED output DB — production US_data.db is NEVER written to by this script.
OUT_DB_PATH = os.path.join(DATA_DIR, "US_data_openbb_test.db")

MAX_HORIZON_DAYS = 45          # same horizon window as NYSE_YFin
# Strike filter: PERCENT of spot (not strike count). NYSE_YFin uses +/-25 STRIKES,
# which is only ~+/-3% on dense-strike names like SPY but ~+/-36% on NVDA — inconsistent.
# CBOE returns the full chain in one call, so a wider window costs no extra fetch time.
STRIKE_PCT = 0.0               # 0 = FULL chain (fetch is one call regardless); use --strike-pct to trim
TEST_TABLE = "options_openbb_test"


def _load_openbb():
    """Return the obb client or exit with a clear message if not installed."""
    try:
        from openbb import obb
        return obb
    except Exception:
        print("ERROR: OpenBB not installed. Run:  pip install openbb openbb-cboe")
        raise SystemExit(1)


def load_universe(limit=None):
    """Active ticker list from ticker_universe.xlsx (same source as NYSE_YFin)."""
    try:
        df = pd.read_excel(UNIVERSE_FILE, sheet_name=UNIVERSE_SHEET_ACTIVE)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        tks = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
    except Exception as e:
        print(f"Universe file unavailable ({e}); falling back to a small default set.")
        tks = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL"]
    tks = sorted(dict.fromkeys(tks))
    return tks[:limit] if limit else tks


def _normalize_chain(df):
    """Map an OpenBB options-chain dataframe to a canonical schema. OpenBB column
    names vary slightly by version/provider, so map defensively."""
    cols = {c.lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    m = {
        "expiration": pick("expiration", "expiration_date", "expiry"),
        "strike": pick("strike", "strike_price"),
        "option_type": pick("option_type", "type", "put_call"),
        "open_interest": pick("open_interest", "openinterest", "oi"),
        "volume": pick("volume", "vol"),
        "last": pick("last_trade_price", "last_price", "close", "lastprice", "mark"),
        "contract": pick("contract_symbol", "contractsymbol", "symbol"),
        "underlying": pick("underlying_price", "underlyingprice", "spot"),
        # backtest-grade extras (CBOE has all of these; yfinance DB never did)
        "bid": pick("bid"),
        "ask": pick("ask"),
        "iv": pick("implied_volatility", "impliedvolatility", "iv"),
        "delta": pick("delta"),
    }
    if not (m["expiration"] and m["strike"] and m["option_type"]):
        raise KeyError(f"Cannot map option columns. Got: {list(df.columns)}")
    return m


def fetch_chain_openbb(obb, ticker, provider, trade_dt):
    """Fetch + shape one ticker's chain into NYSE_YFin's merged schema. Returns df or None."""
    try:
        res = obb.derivatives.options.chains(symbol=ticker, provider=provider)
        df = res.to_dataframe()
        if df is None or len(df) == 0:
            return None
    except Exception as e:
        print(f"  {ticker}: chain fetch failed ({e})")
        return None

    try:
        m = _normalize_chain(df)
    except KeyError as e:
        print(f"  {ticker}: {e}")
        return None

    df = df.copy()
    df["_exp"] = pd.to_datetime(df[m["expiration"]], errors="coerce")
    df["_strike"] = pd.to_numeric(df[m["strike"]], errors="coerce")
    df["_type"] = df[m["option_type"]].astype(str).str.lower().str[0]   # 'c' / 'p'
    df = df.dropna(subset=["_exp", "_strike"])

    # horizon filter (<= 45d)
    cutoff = pd.Timestamp(trade_dt) + pd.Timedelta(days=MAX_HORIZON_DAYS)
    df = df[df["_exp"] <= cutoff]
    if df.empty:
        return None

    # spot for strike-window filter
    spot = None
    if m["underlying"]:
        try:
            spot = float(pd.to_numeric(df[m["underlying"]], errors="coerce").dropna().iloc[0])
        except Exception:
            spot = None
    if spot is None:
        try:
            spot = float(obb.equity.price.quote(symbol=ticker).to_dataframe()["last_price"].iloc[0])
        except Exception:
            spot = None

    calls = df[df["_type"] == "c"]; puts = df[df["_type"] == "p"]

    def side(d, suff):
        def num(key):
            return pd.to_numeric(d[m[key]], errors="coerce").values if m[key] else np.nan
        out = pd.DataFrame({
            "strike": d["_strike"].values,
            "expiry_date": d["_exp"].dt.strftime("%Y-%m-%d").values,
            f"contractSymbol_{suff}": d[m["contract"]].values if m["contract"] else None,
            f"openInt_{suff}": num("open_interest"),
            f"lastPrice_{suff}": num("last"),
            f"vol_{suff}": num("volume"),
            # backtest-grade columns not in the yfinance pipeline
            f"bid_{suff}": num("bid"),
            f"ask_{suff}": num("ask"),
            f"iv_{suff}": num("iv"),
            f"delta_{suff}": num("delta"),
        })
        return out

    merged = pd.merge(side(calls, "Call"), side(puts, "Put"),
                      on=["strike", "expiry_date"], how="outer")

    # strike window: percent of spot (consistent across tickers; 0 = full chain)
    if spot is not None and STRIKE_PCT > 0 and not merged.empty:
        lo, hi = spot * (1 - STRIKE_PCT), spot * (1 + STRIKE_PCT)
        merged = merged[(merged["strike"] >= lo) & (merged["strike"] <= hi)].copy()

    if merged.empty:
        return None
    merged["ticker"] = ticker
    merged["trade_date"] = pd.Timestamp(trade_dt).strftime("%Y-%m-%d")
    return merged


def main():
    ap = argparse.ArgumentParser(description="OpenBB options fetch benchmark vs NYSE_YFin.py")
    ap.add_argument("--limit", type=int, default=None, help="only first N tickers (quick benchmark)")
    ap.add_argument("--workers", type=int, default=8, help="parallel fetch workers (no inter-ticker sleep)")
    ap.add_argument("--provider", default="cboe", help="OpenBB options provider (cboe|yfinance|...)")
    ap.add_argument("--strike-pct", type=float, default=None,
                    help="strike window as fraction of spot (e.g. 0.30 = ±30%%; 0 = full chain)")
    args = ap.parse_args()
    if args.strike_pct is not None:
        global STRIKE_PCT
        STRIKE_PCT = args.strike_pct

    obb = _load_openbb()
    tickers = load_universe(args.limit)
    trade_dt = datetime.now().date()
    table = TEST_TABLE
    print(f"OpenBB fetch: {len(tickers)} tickers · provider={args.provider} · workers={args.workers}")
    print(f"Output (isolated): {OUT_DB_PATH} · table={table}  (production US_data.db untouched)")

    t0 = time.time()
    frames, done, empty = [], 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(fetch_chain_openbb, obb, tk, args.provider, trade_dt): tk for tk in tickers}
        for fut in as_completed(futs):
            df = fut.result()
            done += 1
            if df is not None and len(df):
                frames.append(df)
            else:
                empty += 1
            if done % 25 == 0:
                print(f"  {done}/{len(tickers)} done · {time.time()-t0:.0f}s elapsed")
    elapsed = time.time() - t0

    rows = 0
    if frames:
        allrows = pd.concat(frames, ignore_index=True)
        rows = len(allrows)
        conn = sqlite3.connect(OUT_DB_PATH)     # separate file — cannot affect US_data.db
        try:
            allrows.to_sql(table, conn, if_exists="replace", index=False)
        finally:
            conn.close()

    # ---- benchmark summary ----
    per = elapsed / max(len(tickers), 1)
    print("\n================ OpenBB benchmark ================")
    print(f"tickers      : {len(tickers)}  (empty/failed: {empty})")
    print(f"rows written : {rows}  -> table '{table}'")
    print(f"total time   : {elapsed:.1f}s   ({elapsed/60:.1f} min)")
    print(f"per ticker   : {per:.2f}s")
    print(f"yfinance NYSE_YFin baseline is ~3s/ticker + 1s sleep = ~4s/ticker SEQUENTIAL.")
    print(f"  => est yfinance time for {len(tickers)} tickers: {len(tickers)*4/60:.1f} min sequential")
    print(f"  => OpenBB here: {elapsed/60:.1f} min  ({(len(tickers)*4)/max(elapsed,1):.1f}x speedup vs that baseline)")
    print("==================================================")


if __name__ == "__main__":
    main()
