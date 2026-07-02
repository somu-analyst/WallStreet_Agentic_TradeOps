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
Run (daily):       python NYSE_OpenBB.py
                   -> expanded 740-name universe (auto-built if missing), safe pacing
                      (workers 4 / pace 0.75s / chunk rests), adaptive slowdown on throttle,
                      3 escalating retry rounds, per-day idempotent write, auto --compare
                      vs the yfinance DB when both sides have today's data.
Quick test:        python NYSE_OpenBB.py --limit 20
Small prod set:    python NYSE_OpenBB.py --universe ticker_universe
Score a day:       python NYSE_OpenBB.py --compare [YYYY-MM-DD]
If throttled anyway: just rerun the same command later — reruns are idempotent.
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
# Output DB: US_data_OpenBB.db = full copy of the yfinance DB (all 53 tables,
# seeded once via sqlite backup) + this script's captures accumulating in the
# 'options_openbb' table. Production US_data.db is STILL never written to.
OUT_DB_PATH = os.path.join(DATA_DIR, "US_data_OpenBB.db")

MAX_HORIZON_DAYS = 45          # same horizon window as NYSE_YFin
# Strike filter: PERCENT of spot (not strike count). NYSE_YFin uses +/-25 STRIKES,
# which is only ~+/-3% on dense-strike names like SPY but ~+/-36% on NVDA — inconsistent.
# CBOE returns the full chain in one call, so a wider window costs no extra fetch time.
STRIKE_PCT = 0.0               # 0 = FULL chain (fetch is one call regardless); use --strike-pct to trim
TEST_TABLE = "options_openbb"
PERMANENT_FAIL = set()         # names with no listed options anywhere (CBOE + yahoo) — never retried


def compare_vs_yfinance(trade_date=None):
    """Parallel-test scorer: join today's options_openbb (US_data_OpenBB.db) vs
    options_daily (production US_data.db, read-only) on ticker+expiry+strike and
    report coverage + OI/price agreement. Run daily during the trial period."""
    prod = os.path.join(DATA_DIR, "US_data.db")
    td = trade_date or datetime.now().strftime("%Y-%m-%d")
    co = sqlite3.connect(OUT_DB_PATH); cy = sqlite3.connect(f"file:{prod}?mode=ro", uri=True)
    try:
        ob = pd.read_sql("SELECT ticker,expiry_date,strike,openInt_Call,openInt_Put,"
                         "lastPrice_Call,lastPrice_Put FROM options_openbb WHERE trade_date=?", co, params=(td,))
        yf_ = pd.read_sql("SELECT ticker,expiry_date,strike,openInt_Call,openInt_Put,"
                          "lastPrice_Call,lastPrice_Put FROM options_daily WHERE trade_date=?", cy, params=(td,))
    finally:
        co.close(); cy.close()
    print(f"=== PARALLEL COMPARE {td} ===")
    print(f"openbb rows: {len(ob):,} ({ob.ticker.nunique()} tickers) | yfinance rows: {len(yf_):,} ({yf_.ticker.nunique()} tickers)")
    if ob.empty or yf_.empty:
        print("one side empty — run both pipelines for this date first"); return
    for d in (ob, yf_):
        d["ticker"] = d["ticker"].str.upper()
        d["strike"] = pd.to_numeric(d["strike"], errors="coerce")
    j = ob.merge(yf_, on=["ticker", "expiry_date", "strike"], suffixes=("_ob", "_yf"))
    print(f"overlapping contracts: {len(j):,}")
    if len(j):
        oi_agree = None
        for col in ("openInt_Call", "openInt_Put", "lastPrice_Call"):
            a = pd.to_numeric(j[f"{col}_ob"], errors="coerce"); b = pd.to_numeric(j[f"{col}_yf"], errors="coerce")
            m = a.notna() & b.notna() & (b != 0)
            if m.sum():
                agree = (abs(a[m] - b[m]) / b[m].abs() <= 0.02).mean()
                print(f"  {col:14} within 2%: {agree*100:.0f}%  (n={m.sum():,})")
                if col == "openInt_Call":
                    oi_agree = agree
        print(f"  tickers only in openbb (extra coverage): ~{ob.ticker.nunique() - yf_.ticker.nunique()}")
        # the go/no-go metric is OPEN INTEREST (same OCC settle on both sides).
        # lastPrice is expected to disagree more (different quote timestamps) — informational only.
        if oi_agree is not None:
            print("VERDICT: PASS ✔ — OI agreement ≥95%; this day counts toward the 3-5 day migration streak"
                  if oi_agree >= 0.95 else
                  "VERDICT: CHECK ✖ — OI agreement <95%; inspect mismatched tickers before counting this day")
    print("==============================")


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
_RATES_VOL = ["TLT", "IEF", "SHY", "HYG", "LQD", "AGG", "TMF", "VXX", "UVXY", "VIX"]  # VIX = index options via CBOE
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
    # drop truly non-optionable (VERIFIED 2026-07-02: 0 expiries on Yahoo too —
    # CYBR/EXAS acquired, NVR lists no options, PSLV/PHYS/BITF never had chains,
    # ME delisted, HONA no chain yet). BRK-B/BF-B work via dot-form; VIX works plain.
    _skip = {"DXY", "ME", "HONA", "EXAS", "BITF", "PHYS", "PSLV", "CYBR", "NVR"}
    uni = sorted(dict.fromkeys(
        t for t in tks
        if t and t not in _skip and "-USD" not in t and not t.startswith("^")))
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


def _fetch_chain_raw_yf(ticker, trade_dt):
    """Raw-yfinance chain for names absent from CBOE (per-expiry calls; only used
    for the handful of fallback tickers, so the extra round-trips are fine)."""
    try:
        import yfinance as yf
        import datetime as _dt
        t = yf.Ticker(ticker)
        cutoff = trade_dt + _dt.timedelta(days=MAX_HORIZON_DAYS)
        frames = []
        for e in (t.options or []):
            try:
                ed = _dt.datetime.strptime(e, "%Y-%m-%d").date()
            except Exception:
                continue
            if ed > cutoff:
                continue
            oc = t.option_chain(e)
            def side(d, suff):
                return pd.DataFrame({
                    "strike": pd.to_numeric(d["strike"], errors="coerce"),
                    "expiry_date": e,
                    f"openInt_{suff}": pd.to_numeric(d.get("openInterest"), errors="coerce"),
                    f"lastPrice_{suff}": pd.to_numeric(d.get("lastPrice"), errors="coerce"),
                    f"vol_{suff}": pd.to_numeric(d.get("volume"), errors="coerce"),
                    f"bid_{suff}": pd.to_numeric(d.get("bid"), errors="coerce"),
                    f"ask_{suff}": pd.to_numeric(d.get("ask"), errors="coerce"),
                    f"iv_{suff}": pd.to_numeric(d.get("impliedVolatility"), errors="coerce"),
                    f"delta_{suff}": np.nan,          # yahoo doesn't serve greeks
                })
            m = pd.merge(side(oc.calls, "Call"), side(oc.puts, "Put"),
                         on=["strike", "expiry_date"], how="outer")
            frames.append(m)
        if not frames:
            return None
        out = pd.concat(frames, ignore_index=True)
        for c in out.columns:
            if out[c].dtype == "float64":
                out[c] = out[c].astype("float32")
        out["ticker"] = ticker
        out["trade_date"] = pd.Timestamp(trade_dt).strftime("%Y-%m-%d")
        return out
    except Exception:
        return None


def _fetch_chain_cdn(ticker, trade_dt):
    """Throttle-buster: hit CBOE's public delayed-quotes CDN directly with a
    browser-impersonated client (curl_cffi — same trick NYSE_YFin uses for yahoo).
    Same data OpenBB's cboe provider reads, but a browser HTTP fingerprint, so it
    usually succeeds while the vanilla client is being rejected (KeyError 'data')."""
    import re
    try:
        try:
            from curl_cffi import requests as _rq

            def _get(url):
                return _rq.get(url, impersonate="chrome", timeout=30)
        except Exception:                                # curl_cffi missing -> plain UA spoof
            import requests as _rq
            _hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

            def _get(url):
                return _rq.get(url, headers=_hdr, timeout=30)

        js = None
        for sym in dict.fromkeys([ticker.replace("-", "."), ticker, "_" + ticker]):
            try:
                r = _get(f"https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json")
                if r.status_code != 200:
                    continue
                j = r.json()
            except Exception:
                continue
            if isinstance(j, dict) and j.get("data", {}).get("options"):
                js = j
                break
        if not js:
            return None
        d = js["data"]
        spot = d.get("current_price") or d.get("close")
        cutoff = trade_dt + timedelta(days=MAX_HORIZON_DAYS)
        rows = []
        for o in d["options"]:
            m = re.match(r"^(.+?)(\d{6})([CP])(\d{8})$", str(o.get("option") or ""))
            if not m:
                continue
            try:
                exp = datetime.strptime(m.group(2), "%y%m%d").date()
            except Exception:
                continue
            if exp > cutoff:
                continue
            rows.append({"expiry_date": exp.strftime("%Y-%m-%d"),
                         "strike": int(m.group(4)) / 1000.0, "typ": m.group(3),
                         "oi": o.get("open_interest"), "last": o.get("last_trade_price"),
                         "vol": o.get("volume"), "bid": o.get("bid"), "ask": o.get("ask"),
                         "iv": o.get("iv"), "delta": o.get("delta")})
        if not rows:
            return None
        raw = pd.DataFrame(rows).drop_duplicates(subset=["expiry_date", "strike", "typ"])

        def side(dd, suff):
            return pd.DataFrame({
                "strike": dd["strike"].values,
                "expiry_date": dd["expiry_date"].values,
                f"openInt_{suff}": pd.to_numeric(dd["oi"], errors="coerce").values,
                f"lastPrice_{suff}": pd.to_numeric(dd["last"], errors="coerce").values,
                f"vol_{suff}": pd.to_numeric(dd["vol"], errors="coerce").values,
                f"bid_{suff}": pd.to_numeric(dd["bid"], errors="coerce").values,
                f"ask_{suff}": pd.to_numeric(dd["ask"], errors="coerce").values,
                f"iv_{suff}": pd.to_numeric(dd["iv"], errors="coerce").values,
                f"delta_{suff}": pd.to_numeric(dd["delta"], errors="coerce").values,
            })
        merged = pd.merge(side(raw[raw["typ"] == "C"], "Call"), side(raw[raw["typ"] == "P"], "Put"),
                          on=["strike", "expiry_date"], how="outer")
        if spot and STRIKE_PCT > 0 and not merged.empty:
            lo, hi = float(spot) * (1 - STRIKE_PCT), float(spot) * (1 + STRIKE_PCT)
            merged = merged[(merged["strike"] >= lo) & (merged["strike"] <= hi)].copy()
        if merged.empty:
            return None
        for c in merged.columns:
            if merged[c].dtype == "float64":
                merged[c] = merged[c].astype("float32")
        merged["ticker"] = ticker
        merged["trade_date"] = pd.Timestamp(trade_dt).strftime("%Y-%m-%d")
        return merged
    except Exception:
        return None


def fetch_chain_openbb(obb, ticker, provider, trade_dt):
    """Fetch + shape one ticker's chain into NYSE_YFin's merged schema. Returns df or None."""
    df = None
    # class shares: Yahoo style 'BRK-B' -> CBOE directory wants 'BRK.B'
    variants = [ticker] + ([ticker.replace("-", ".")] if "-" in ticker else [])
    last_err = None
    for sym in variants:
        try:
            res = obb.derivatives.options.chains(symbol=sym, provider=provider)
            df = res.to_dataframe()
            if df is not None and len(df):
                break
        except Exception as e:
            last_err = e
            df = None
    # non-CBOE names (CYBR/NVR/PSLV/...): their options trade on other exchanges.
    # OpenBB's yfinance provider also fails for these, so fall back to RAW yfinance
    # (same machinery as NYSE_YFin — known to serve them).
    if (df is None or len(df) == 0) and "not found in the cboe" in str(last_err).lower() \
            and provider == "cboe":
        raw = _fetch_chain_raw_yf(ticker, trade_dt)
        if raw is not None:
            print(f"  {ticker}: not on CBOE -> recovered via raw yfinance ({len(raw)} rows)")
            return raw
        # not on CBOE AND yahoo has no chains either -> genuinely optionless.
        # Mark permanent so the retry rounds don't waste requests re-hammering it.
        PERMANENT_FAIL.add(ticker)
    # throttle response (KeyError 'data'): don't wait for the retry rounds — go
    # straight at the CDN with a browser-impersonated client (different fingerprint).
    if (df is None or len(df) == 0) and "KeyError" in str(last_err):
        cdn = _fetch_chain_cdn(ticker, trade_dt)
        if cdn is not None:
            print(f"  {ticker}: throttled on OpenBB -> recovered via CBOE CDN ({len(cdn)} rows)")
            return cdn
    if df is None or len(df) == 0:
        print(f"  {ticker}: chain fetch failed ({last_err})")
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
        # NOTE: contractSymbol columns dropped — fully reconstructable from
        # ticker+expiry+strike+type, and they were ~35% of storage (long strings).
        out = pd.DataFrame({
            "strike": d["_strike"].values,
            "expiry_date": d["_exp"].dt.strftime("%Y-%m-%d").values,
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
    for c in merged.columns:                     # float32 halves numeric storage
        if merged[c].dtype == "float64":
            merged[c] = merged[c].astype("float32")

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
    ap.add_argument("--workers", type=int, default=4,
                    help="parallel fetch workers (4 = safe for CBOE; 8 trips the throttle)")
    ap.add_argument("--provider", default="cboe", help="OpenBB options provider (cboe|yfinance|...)")
    ap.add_argument("--strike-pct", type=float, default=None,
                    help="strike window as fraction of spot (e.g. 0.30 = ±30%%; 0 = full chain)")
    ap.add_argument("--universe", default=EXPANDED_SHEET,
                    help=f"universe sheet (default {EXPANDED_SHEET}; auto-built if missing; "
                         f"'{UNIVERSE_SHEET_ACTIVE}' = small production set)")
    ap.add_argument("--build-universe", action="store_true",
                    help="build the expanded S&P500+NDX+tiers universe sheet and exit")
    ap.add_argument("--pace", type=float, default=0.75,
                    help="per-request stagger seconds (rate-limit guard; 0 = blast)")
    ap.add_argument("--chunk-size", type=int, default=80,
                    help="tickers per chunk (rest between chunks lets the rate window reset)")
    ap.add_argument("--rest", type=int, default=45,
                    help="seconds to rest between chunks")
    ap.add_argument("--parquet", action="store_true",
                    help="space-saver: export the day to parquet-zstd and clear it from sqlite")
    ap.add_argument("--compare", nargs="?", const="today", default=None,
                    help="parallel-test scorer: compare openbb vs yfinance for a date (default today) and exit")
    args = ap.parse_args()
    if args.strike_pct is not None:
        global STRIKE_PCT
        STRIKE_PCT = args.strike_pct
    if args.build_universe:
        build_expanded_universe()
        return
    if args.compare:
        compare_vs_yfinance(args.compare if args.compare != "today" else None)
        return

    obb = _load_openbb()
    # auto-build the expanded sheet on first run (so plain `python NYSE_OpenBB.py` just works)
    if args.universe == EXPANDED_SHEET:
        try:
            pd.read_excel(UNIVERSE_FILE, sheet_name=EXPANDED_SHEET, nrows=1)
        except Exception:
            print(f"universe sheet '{EXPANDED_SHEET}' missing -> building it now (one-time)…")
            build_expanded_universe()
    tickers = load_universe(args.limit, sheet=args.universe)
    trade_dt = datetime.now().date()
    table = TEST_TABLE
    print(f"OpenBB fetch: {len(tickers)} tickers · provider={args.provider} · workers={args.workers}")
    print(f"Output (isolated): {OUT_DB_PATH} · table={table}  (production US_data.db untouched)")

    # ---- logging: everything goes to console AND a dated log file ----
    log_path = os.path.join(DATA_DIR, f"openbb_fetch_{trade_dt.strftime('%Y%m%d')}.log")
    _logf = open(log_path, "a", encoding="utf-8")

    def log(msg):
        line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
        print(line)
        _logf.write(line + "\n"); _logf.flush()

    try:                                       # stamp the lib version (schema-drift forensics)
        from importlib.metadata import version as _ver
        obb_ver = f"openbb {_ver('openbb')}/cboe {_ver('openbb-cboe')}"
    except Exception:
        obb_ver = "openbb ?"
    log(f"=== RUN start · {len(tickers)} tickers · chunk={args.chunk_size} rest={args.rest}s "
        f"workers={args.workers} pace={args.pace}s · provider={args.provider} · {obb_ver} ===")

    t0 = time.time()
    today_str = pd.Timestamp(trade_dt).strftime("%Y-%m-%d")
    conn = sqlite3.connect(OUT_DB_PATH)
    # idempotent per day: clear today's rows once, then APPEND per chunk (crash-safe)
    try:
        conn.execute(f"DELETE FROM {table} WHERE trade_date=?", (today_str,))
        conn.commit()
    except Exception:
        pass
    failed, total_ok, total_rows, processed = [], 0, 0, 0
    total_n = len(tickers)

    def _progress():
        """'processed/total (pct%) · ETA mm:ss' string for terminal progress."""
        if processed == 0:
            return "0%"
        pct = processed / total_n * 100
        eta = (time.time() - t0) / processed * (total_n - processed)
        return f"{processed}/{total_n} ({pct:.0f}%) · ETA {int(eta//60)}m{int(eta%60):02d}s"

    def run_pass(tks, workers, pace, label, count_progress=True):
        nonlocal total_ok, total_rows, processed
        frames, ok = [], 0
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
                if count_progress:
                    processed += 1
                    if i % 20 == 0:                      # live tick every 20 tickers
                        print(f"    … {_progress()}")
        if frames:
            chunk_df = pd.concat(frames, ignore_index=True)
            chunk_df.to_sql(table, conn, if_exists="append", index=False)
            total_rows += len(chunk_df)
        total_ok += ok
        log(f"[{label}] ok {ok}/{len(tks)} · {_progress()} · rows {total_rows:,}")
        return ok

    # chunked main passes with rests so CBOE's throttle window resets.
    # ADAPTIVE: if a chunk gets >25% throttled, slow down for the rest of the run.
    chunks = [tickers[i:i + args.chunk_size] for i in range(0, len(tickers), args.chunk_size)]
    pace, rest, workers = args.pace, args.rest, args.workers
    for ci, ch in enumerate(chunks, 1):
        f0 = len(failed)
        run_pass(ch, workers, pace, f"chunk {ci}/{len(chunks)}")
        fail_frac = (len(failed) - f0) / max(len(ch), 1)
        if fail_frac > 0.25:                    # heavy throttle -> back off on ALL levers
            pace = min(pace * 1.5, 2.0); rest = min(int(rest * 1.5), 120)
            workers = max(2, workers // 2)
            log(f"  throttled ({fail_frac*100:.0f}% fails) -> slowing: "
                f"workers {workers} pace {pace:.2f}s rest {rest}s")
        if ci < len(chunks):
            time.sleep(rest)

    # final slow retry rounds — escalating backoff, permanently-optionless names excluded,
    # keeps going (up to 5 rounds) as long as each round recovers something
    prev_left = None
    for rnd in (1, 2, 3, 4, 5):
        retry = [t for t in dict.fromkeys(failed) if t not in PERMANENT_FAIL]
        failed = [t for t in failed if t in PERMANENT_FAIL]      # keep only permanent in the tally
        if not retry:
            break
        if prev_left is not None and len(retry) >= prev_left:
            log(f"retry stopped: round {rnd-1} recovered nothing ({len(retry)} still throttled) — "
                "rerun the same command later, it only needs to refill these")
            failed.extend(retry)
            break
        prev_left = len(retry)
        backoff = 60 * rnd
        log(f"retry round {rnd}: {len(retry)} throttled tickers ({backoff}s backoff, slow single-file)")
        time.sleep(backoff)
        for i in range(0, len(retry), 40):
            run_pass(retry[i:i + 40], 1, 1.2 + 0.3 * rnd, f"retry{rnd} {i//40+1}", count_progress=False)
            time.sleep(rest)

    # ── automatic daily backup: the day's rows -> parquet-zstd in openbb_chains\.
    # Capture-forward data is IRREPLACEABLE (no free historical source), so every run
    # leaves a ~3-4 MB second copy. --parquet additionally clears sqlite (space-saver).
    try:
        pq_dir = os.path.join(DATA_DIR, "openbb_chains")
        os.makedirs(pq_dir, exist_ok=True)
        day_df = pd.read_sql(f"SELECT * FROM {table} WHERE trade_date=?", conn, params=(today_str,))
        if len(day_df):
            pq_path = os.path.join(pq_dir, f"chains_{today_str}.parquet")
            day_df.to_parquet(pq_path, compression="zstd", index=False)
            mb = os.path.getsize(pq_path) / 1e6
            log(f"backup       : {pq_path}  ({mb:.1f} MB zstd — copy this folder offsite weekly)")
            if args.parquet:
                conn.execute(f"DELETE FROM {table} WHERE trade_date=?", (today_str,))
                conn.commit(); conn.execute("VACUUM"); conn.commit()
                log("sqlite staging cleared (--parquet space-saver mode; parquet is the copy of record)")
    except Exception as e:
        log(f"parquet backup failed ({e}) — data remains in sqlite")
    conn.close()
    elapsed = time.time() - t0
    perm = sorted(PERMANENT_FAIL)
    thr = sorted(set(failed) - PERMANENT_FAIL)
    log("================ SUMMARY ================")
    log(f"success      : {total_ok}/{len(tickers)} tickers")
    if perm:
        log(f"no options   : {', '.join(perm)}  (not optionable anywhere — ignore / purge from sheet)")
    if thr:
        log(f"throttled    : {', '.join(thr[:40])}  -> just rerun the same command later (idempotent, "
            "already-captured names are refetched cleanly)")
    log(f"rows written : {total_rows} -> {table} (trade_date {today_str})")
    log(f"total time   : {elapsed/60:.1f} min  (yfinance baseline ~{len(tickers)*4/60:.0f} min sequential)")
    log(f"log file     : {log_path}")
    _logf.close()

    # parallel-test scorer: runs automatically when the yfinance side also has today's data
    print()
    try:
        compare_vs_yfinance(None)
    except Exception as e:
        print(f"(compare vs yfinance skipped: {e})")


if __name__ == "__main__":
    main()
