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


def load_universe(limit=None, sheet=UNIVERSE_SHEET_ACTIVE):
    """Ticker list from ticker_universe.xlsx (same file as NYSE_YFin; sheet selectable)."""
    try:
        df = pd.read_excel(UNIVERSE_FILE, sheet_name=sheet)
        col = "ticker" if "ticker" in df.columns else df.columns[0]
        tks = [str(t).strip().upper() for t in df[col].dropna().tolist() if str(t).strip()]
    except Exception as e:
        print(f"Universe sheet '{sheet}' unavailable ({e}); falling back to a small default set.")
        tks = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL"]
    tks = sorted(dict.fromkeys(tks))
    return tks[:limit] if limit else tks


# ── EXPANDED UNIVERSE (S&P500 + NDX + buzz/global/commodity/crypto tiers) ──
EXPANDED_SHEET = "openbb_universe"
# Curated tiers (options-listed only; spot crypto pairs like BTC-USD have no options)
_BUZZ = ["GME", "AMC", "PLTR", "SOFI", "HOOD", "RKLB", "SMCI", "IONQ", "RGTI", "QUBT",
         "ACHR", "JOBY", "HIMS", "OKLO", "SMR", "RDDT", "DJT", "LUNR", "ASTS", "NBIS",
         "TEM", "APP", "CRWV", "SNOW", "NET", "DDOG", "CRWD", "ZS", "PANW", "MSTR"]
_GLOBAL_ADR = ["TSM", "BABA", "ASML", "SAP", "NVO", "TM", "SONY", "SHOP", "SE", "MELI",
               "PDD", "JD", "BIDU", "NIO", "GRAB", "ARM", "INFY", "IBN", "UL", "BP"]
_COUNTRY_ETF = ["EEM", "EFA", "VEA", "VWO", "FXI", "KWEB", "EWJ", "EWZ", "INDA", "EWY",
                "EWT", "EWG", "EWU", "EWC", "EWA"]
_COMMODITY = ["GLD", "SLV", "USO", "UNG", "CPER", "PPLT", "PALL", "URA", "DBA", "WEAT",
              "CORN", "GDX", "GDXJ", "SIL", "XME", "SLX", "LIT"]
_CRYPTO_EQ = ["IBIT", "FBTC", "ETHA", "BITO", "COIN", "MARA", "RIOT", "CLSK", "HUT", "BITF"]
_RATES_VOL = ["TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "TMF", "VXX", "UVXY"]
# Thematic tiers (individual stocks, not just ETFs)
_SEMIS = ["NVDA", "AMD", "AVGO", "MU", "QCOM", "MRVL", "TXN", "AMAT", "LRCX", "KLAC",
          "ARM", "INTC", "ON", "ADI", "NXPI", "MCHP", "TER", "ENTG", "SWKS", "QRVO",
          "COHR", "ALAB", "TSM", "ASML"]
_ROBOTICS_AI = ["ISRG", "ROK", "PATH", "SYM", "CGNX", "ZBRA", "TER", "PONY",
                "BOTZ", "ROBO", "ARKQ"]
_SPACE = ["RKLB", "ASTS", "LUNR", "RDW", "PL", "BKSY", "SPCE", "IRDM", "GSAT",
          "HEI", "KTOS", "AVAV", "UFO", "ARKX"]
_NUCLEAR = ["OKLO", "SMR", "NNE", "CCJ", "LEU", "UEC", "DNN", "NXE", "UUUU",
            "BWXT", "CEG", "VST", "TLN", "URNM", "URNJ"]
_CYBER = ["CRWD", "ZS", "PANW", "FTNT", "OKTA", "S", "NET", "CYBR", "TENB",
          "RPD", "QLYS", "CHKP", "GEN", "AKAM", "HACK", "CIBR", "BUG"]
_COMMODITY_STOCKS = ["NEM", "FCX", "SCCO", "AA", "CLF", "NUE", "STLD", "GOLD", "AEM",
                     "WPM", "FNV", "RGLD", "KGC", "HL", "PAAS", "MP", "ALB", "SQM",
                     "XOM", "CVX", "COP", "OXY", "SLB", "HAL", "DVN", "FANG", "EOG",
                     "LNG", "EQT", "AR", "RRC", "BTU", "AMR"]
# "Next wave" tiers — for EARLY tracking via /building /uoa /rs (not chase-buying)
_AI_SOFT = ["PLTR", "SNOW", "MDB", "AI", "SOUN", "BBAI", "UPST", "TEM", "DUOL",
            "APP", "NOW", "ADBE", "CRM", "IGV", "AIQ", "WCLD"]
_QUANTUM = ["IONQ", "RGTI", "QUBT", "QBTS", "ARQQ"]
_AI_INFRA_POWER = ["VRT", "ETN", "GEV", "ANET", "CIEN", "CRDO", "MOD", "POWL",
                   "EME", "PWR", "DLR", "EQIX", "NRG", "DELL", "IREN", "APLD",
                   "WULF", "CORZ", "NBIS", "CRWV"]
_DEFENSE_TECH = ["KTOS", "AVAV", "AXON", "LMT", "RTX", "NOC", "GD", "LHX", "LDOS", "ITA"]
_BIOTECH_NEXT = ["LLY", "NVO", "VKTX", "AMGN", "REGN", "VRTX", "CRSP", "NTLA",
                 "BEAM", "RXRX", "ILMN", "XBI", "ARKG"]
_FINTECH = ["HOOD", "SOFI", "AFRM", "TOST", "NU", "PYPL", "XYZ", "COIN"]
_BIO_AI = ["RXRX", "TEM", "SDGR", "ABSI", "DNA", "TWST", "PACB", "GH", "NTRA",
           "CERT", "MRNA", "EXAS", "ME"]   # AI drug discovery / techbio / AI dx
_BROAD_ETF = ["SPY", "QQQ", "IWM", "DIA", "MDY", "RSP", "XLK", "XLE", "XLF", "XLV", "XLI",
              "XLB", "XLU", "XLY", "XLP", "XLRE", "XLC", "SMH", "SOXX", "SOXL", "SQQQ",
              "TQQQ", "ARKK", "XBI", "ITB", "JETS", "TAN"]


def _wiki_tickers(url, col_candidates=("Symbol", "Ticker")):
    """Constituent tickers from a Wikipedia list page (free, no key)."""
    import urllib.request
    from io import StringIO
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    for t in pd.read_html(StringIO(html)):
        for col in col_candidates:
            if col in t.columns:
                return [str(x).strip().upper().replace(".", "-") for x in t[col].dropna() if str(x).strip()]
    return []


def build_expanded_universe():
    """Build the expanded universe -> new sheet 'openbb_universe' (production sheets untouched)."""
    tks = []
    try:
        sp = _wiki_tickers("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        print(f"S&P 500 from Wikipedia: {len(sp)}")
        tks += sp
    except Exception as e:
        print(f"S&P 500 fetch failed ({e}) — continuing without")
    try:
        ndx = _wiki_tickers("https://en.wikipedia.org/wiki/Nasdaq-100")
        print(f"Nasdaq-100 from Wikipedia: {len(ndx)}")
        tks += ndx
    except Exception as e:
        print(f"Nasdaq-100 fetch failed ({e}) — continuing without")
    tks += (_BUZZ + _GLOBAL_ADR + _COUNTRY_ETF + _COMMODITY + _CRYPTO_EQ + _RATES_VOL + _BROAD_ETF
            + _SEMIS + _ROBOTICS_AI + _SPACE + _NUCLEAR + _CYBER + _COMMODITY_STOCKS
            + _AI_SOFT + _QUANTUM + _AI_INFRA_POWER + _DEFENSE_TECH + _BIOTECH_NEXT + _FINTECH
            + _BIO_AI)
    # keep the current active names too (nothing lost)
    tks += load_universe(sheet=UNIVERSE_SHEET_ACTIVE)
    uni = sorted(dict.fromkeys(t for t in tks if t and t not in ("DXY",)))
    df = pd.DataFrame({"ticker": uni})
    with pd.ExcelWriter(UNIVERSE_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
        df.to_excel(w, sheet_name=EXPANDED_SHEET, index=False)
    print(f"Wrote {len(uni)} tickers -> sheet '{EXPANDED_SHEET}' (production sheets untouched)")
    return uni


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
    ap.add_argument("--universe", default=UNIVERSE_SHEET_ACTIVE,
                    help=f"universe sheet name (e.g. {EXPANDED_SHEET})")
    ap.add_argument("--build-universe", action="store_true",
                    help="build the expanded S&P500+NDX+tiers universe sheet and exit")
    ap.add_argument("--pace", type=float, default=0.15,
                    help="per-request stagger seconds (rate-limit guard; 0 = blast)")
    args = ap.parse_args()
    if args.strike_pct is not None:
        global STRIKE_PCT
        STRIKE_PCT = args.strike_pct
    if args.build_universe:
        build_expanded_universe()
        return

    obb = _load_openbb()
    tickers = load_universe(args.limit, sheet=args.universe)
    trade_dt = datetime.now().date()
    table = TEST_TABLE
    print(f"OpenBB fetch: {len(tickers)} tickers · provider={args.provider} · workers={args.workers}")
    print(f"Output (isolated): {OUT_DB_PATH} · table={table}  (production US_data.db untouched)")

    t0 = time.time()
    frames, failed = [], []

    def run_pass(tks, workers, pace, label):
        """One fetch pass. `pace` = per-submit stagger (sec) so we stay under
        CBOE's rate limit (8 workers unpaced -> throttled after ~60 tickers)."""
        ok = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {}
            for tk in tks:
                futs[ex.submit(fetch_chain_openbb, obb, tk, args.provider, trade_dt)] = tk
                time.sleep(pace)
            for i, fut in enumerate(as_completed(futs), 1):
                df = fut.result()
                if df is not None and len(df):
                    frames.append(df); ok += 1
                else:
                    failed.append(futs[fut])
                if i % 50 == 0:
                    print(f"  [{label}] {i}/{len(tks)} · {time.time()-t0:.0f}s elapsed")
        return ok

    ok1 = run_pass(tickers, args.workers, args.pace, "pass1")
    retry = list(dict.fromkeys(failed)); failed = []
    ok2 = 0
    if retry:
        print(f"Retrying {len(retry)} failures slowly (backoff 20s)…")
        time.sleep(20)
        ok2 = run_pass(retry, 2, max(args.pace, 0.35), "retry")
    empty = len(failed)
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
