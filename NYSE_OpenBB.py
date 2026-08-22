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
try:
    import yfinance as yf
    from curl_cffi import requests as curl_requests
except Exception:
    yf = None
    curl_requests = None

# ---- config (mirrors NYSE_YFin.py) ------------------------------------------
DATA_DIR = r"C:\Users\srini\Options_chain_data"
US_CHARTS_DIR = os.path.join(DATA_DIR, "US_CHARTS")
# ticker_universe.xlsx moved into NYSE_DATA (next to the scripts) 2026-07-20; prefer that,
# fall back to the old US_CHARTS location for safety.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = (os.path.join(_SCRIPT_DIR, "ticker_universe.xlsx")
                 if os.path.exists(os.path.join(_SCRIPT_DIR, "ticker_universe.xlsx"))
                 else os.path.join(US_CHARTS_DIR, "ticker_universe.xlsx"))
UNIVERSE_SHEET_ACTIVE = "ticker_universe"
# Output DB: US_data_OpenBB.db = full copy of the yfinance DB (all 53 tables,
# seeded once via sqlite backup) + this script's captures accumulating in the
# 'options_openbb' table. Production US_data.db is STILL never written to.
OUT_DB_PATH = os.path.join(DATA_DIR, "US_data_OpenBB.db")
OB_DB = OUT_DB_PATH   # alias used by derive + skew functions below

MAX_HORIZON_DAYS = 45          # same horizon window as NYSE_YFin
# Strike filter: PERCENT of spot (not strike count). NYSE_YFin uses +/-25 STRIKES,
# which is only ~+/-3% on dense-strike names like SPY but ~+/-36% on NVDA — inconsistent.
# CBOE returns the full chain in one call, so a wider window costs no extra fetch time.
STRIKE_PCT = 0.0               # 0 = FULL chain (fetch is one call regardless); use --strike-pct to trim
TEST_TABLE = "options_openbb"
PERMANENT_FAIL = set()         # names with no listed options anywhere (CBOE + yahoo) — never retried
SKIP_FILE = os.path.join(DATA_DIR, "openbb_skip.txt")   # persistent optionless list (self-healing)


def _load_skip():
    """Names PROVEN optionless (CBOE + yahoo both empty). Every run appends what it
    proves; load_universe excludes them — so a bad symbol errors exactly once, ever.
    To give a name another chance (e.g. it relists options), delete its line."""
    try:
        with open(SKIP_FILE, encoding="utf-8") as f:
            return {ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")}
    except FileNotFoundError:
        return set()


def _add_to_skip(names):
    new = sorted({str(n).upper() for n in names} - _load_skip())
    if new:
        with open(SKIP_FILE, "a", encoding="utf-8") as f:
            f.write("".join(n + "\n" for n in new))
    return new

_NYSE_HOL_CACHE = {}


def _nyse_holidays(year):
    """Full-day NYSE holidays for ANY year — computed from the exchange rules
    (no yearly upkeep): New Year, MLK, Washington's Bday, Good Friday, Memorial,
    Juneteenth, Independence, Labor, Thanksgiving, Christmas, with Sat->Fri /
    Sun->Mon observance shifts (NYSE skips New Year observance when Jan 1 is Sat)."""
    if year in _NYSE_HOL_CACHE:
        return _NYSE_HOL_CACHE[year]
    from datetime import date as _d

    def obs(d):                                  # weekend observance shift
        if d.weekday() == 5:
            return d - timedelta(days=1)
        if d.weekday() == 6:
            return d + timedelta(days=1)
        return d

    def nth_weekday(month, weekday, n):          # e.g. 3rd Monday of Jan
        d = _d(year, month, 1)
        return d + timedelta(days=(weekday - d.weekday()) % 7 + (n - 1) * 7)

    # Easter Sunday (Anonymous Gregorian computus) -> Good Friday = Easter - 2
    a = year % 19; b, c = divmod(year, 100)
    dd, e = divmod(b, 4); f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - dd - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    easter = _d(year, (h + l - 7 * m + 114) // 31, ((h + l - 7 * m + 114) % 31) + 1)

    hs = {nth_weekday(1, 0, 3),                  # MLK — 3rd Mon Jan
          nth_weekday(2, 0, 3),                  # Washington — 3rd Mon Feb
          easter - timedelta(days=2),            # Good Friday
          _d(year, 5, 31) - timedelta(days=_d(year, 5, 31).weekday()),  # Memorial — last Mon May
          obs(_d(year, 6, 19)),                  # Juneteenth
          obs(_d(year, 7, 4)),                   # Independence Day
          nth_weekday(9, 0, 1),                  # Labor — 1st Mon Sep
          nth_weekday(11, 3, 4),                 # Thanksgiving — 4th Thu Nov
          obs(_d(year, 12, 25))}                 # Christmas
    ny = _d(year, 1, 1)                          # New Year: Sat -> NOT observed (NYSE rule)
    if ny.weekday() == 6:
        hs.add(ny + timedelta(days=1))
    elif ny.weekday() != 5:
        hs.add(ny)
    _NYSE_HOL_CACHE[year] = hs
    return hs


def _is_trading_day(d):
    return d.weekday() < 5 and d not in _nyse_holidays(d.year)


def _effective_trade_date():
    """The market session the CBOE feed is actually serving right now (mirrors
    run_all_offhours gating): weekends/holidays -> last trading day; pre-market
    NY (<09:30) -> previous trading day (feed still shows yesterday's EOD marks);
    otherwise today. Prevents Saturday runs stamping Friday data as Saturday."""
    try:
        from zoneinfo import ZoneInfo
        now_ny = datetime.now(ZoneInfo("America/New_York"))
    except Exception:                            # no tz db -> assume local ≈ fine
        now_ny = datetime.now()
    d = now_ny.date()
    if _is_trading_day(d) and (now_ny.hour, now_ny.minute) < (9, 30):
        d = d - timedelta(days=1)                # pre-market: feed = yesterday's close
    while not _is_trading_day(d):
        d = d - timedelta(days=1)                # weekend / holiday -> last session
    return d


def compare_vs_yfinance(trade_date=None):
    """Parallel-test scorer: join today's options_openbb (US_data_OpenBB.db) vs
    options_daily (production US_data.db, read-only) on ticker+expiry+strike and
    report coverage + OI/price agreement. Run daily during the trial period."""
    prod = os.path.join(DATA_DIR, "US_data.db")
    td = trade_date or _effective_trade_date().strftime("%Y-%m-%d")
    co = sqlite3.connect(OUT_DB_PATH, timeout=30); cy = sqlite3.connect(f"file:{prod}?mode=ro", uri=True)
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
        d["ticker"] = d["ticker"].str.upper().str.lstrip("^")   # yfinance ^VIX == openbb VIX
        d["strike"] = pd.to_numeric(d["strike"], errors="coerce")
    j = ob.merge(yf_, on=["ticker", "expiry_date", "strike"], suffixes=("_ob", "_yf"))
    print(f"overlapping contracts: {len(j):,}")
    if len(j):
        oi_med = px_agree = None
        for col in ("openInt_Call", "openInt_Put", "lastPrice_Call"):
            a = pd.to_numeric(j[f"{col}_ob"], errors="coerce"); b = pd.to_numeric(j[f"{col}_yf"], errors="coerce")
            m = a.notna() & b.notna() & (b != 0)
            if m.sum():
                rel = abs(a[m] - b[m]) / b[m].abs()
                agree = (rel <= 0.02).mean()
                print(f"  {col:14} within 2%: {agree*100:.0f}%  median diff: {rel.median()*100:.2f}%  (n={m.sum():,})")
                if col == "openInt_Call":
                    oi_med = rel.median()
                if col == "lastPrice_Call":
                    px_agree = agree
        print(f"  tickers only in openbb (extra coverage): ~{ob.ticker.nunique() - yf_.ticker.nunique()}")
        # Verdict uses MEDIAN OI diff + price agreement — robust metrics. Verified 2026-07-03:
        # on every audited disagreement the fresh CBOE feed matched the OpenBB value exactly and
        # yahoo held stale/near-zero OI, so a strike-level agreement %% mostly measures yahoo's
        # data quality, not ours. Median OI diff ~0 + prices agreeing => both capture the market.
        if oi_med is not None:
            ok = oi_med <= 0.02 and (px_agree is None or px_agree >= 0.90)
            # ASCII-only: cp1252 consoles crash on check-mark glyphs (seen 2026-07-14)
            print("VERDICT: PASS - median OI diff <=2% and prices agree; day counts toward the migration streak"
                  if ok else
                  "VERDICT: CHECK - median OI diff >2% (or prices diverging); inspect before counting this day")
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
    skip = _load_skip()
    dropped = sorted(set(tks) & skip)
    if dropped:
        print(f"skipping {len(dropped)} proven-optionless names (openbb_skip.txt): {', '.join(dropped)}")
    tks = [t for t in tks if t not in skip]
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
        # .date() matters: `exp` below is a date, and comparing date > datetime raises
        # TypeError. That exception was swallowed by the outer handler, so this CDN
        # fallback returned None for EVERY ticker, always -- silently. Nothing noticed
        # because it is only a fallback and the primary OpenBB path was succeeding; it
        # would have surfaced the first night the vanilla client got throttled, which is
        # exactly the situation this "throttle-buster" exists to rescue (found 2026-08-22
        # while probing whether the capture survives a datacenter IP).
        cutoff = (trade_dt + timedelta(days=MAX_HORIZON_DAYS)).date()
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
    # underlying_price (2026-07-30): the chain fetch ALREADY carries the spot used above for
    # the strike-window filter -- it was being computed and thrown away. Persisting it means
    # build_stock_daily can source `close` straight from this capture, zero extra API calls,
    # no yfinance dependency for that step (user ask: "why are we using yahoo, use only bb").
    merged["underlying_price"] = np.float32(spot) if spot is not None else np.nan
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
    ap.add_argument("--fresh", action="store_true",
                    help="wipe the day's rows and refetch EVERYTHING (disables auto-resume)")
    ap.add_argument("--compare", nargs="?", const="today", default=None,
                    help="parallel-test scorer: compare openbb vs yfinance for a date (default today) and exit")
    ap.add_argument("--full", action="store_true",
                    help="after capture, automatically run skew_snapshot then derive (--stock) "
                         "for the captured day plus any date missing downstream")
    ap.add_argument("--rebuild", action="store_true",
                    help="with --full: redo EVERY capture date instead of just the captured day "
                         "(one-shot recovery / after a derive formula change)")
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
    trade_dt = _effective_trade_date()
    if trade_dt != datetime.now().date():
        print(f"off-hours/holiday run -> storing as last market session: {trade_dt}")
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
    # timeout=30 (2026-07-30, after a real crash): an ad-hoc script writing to the same DB
    # from another process caused an immediate "database is locked" here instead of a wait,
    # killing the whole 734-ticker run at 11%. Every writer to this DB needs to wait on a
    # transient lock rather than error out -- see the matching fix in get_conn() elsewhere.
    conn = sqlite3.connect(OUT_DB_PATH, timeout=30)
    # underlying_price column (2026-07-30): ALTER is a no-op once it exists, safe every run —
    # same idempotent-migration pattern used elsewhere in this codebase (e.g. watchlist.asset_class).
    try:
        conn.execute(f"ALTER TABLE {TEST_TABLE} ADD COLUMN underlying_price REAL")
        conn.commit()
    except Exception:
        pass
    # ── RESUME (2026-07-18): chunks APPEND + commit as they land, so a halted/killed
    # run leaves whole tickers safely in the DB. Default = skip those and fetch only
    # what's missing for the day (laptop closed mid-run, Ctrl+C, crash — just rerun).
    # --fresh restores the old wipe-and-refetch-everything behavior. ──
    _done = set()
    if not args.fresh:
        try:
            _done = {r[0] for r in conn.execute(
                f"SELECT DISTINCT ticker FROM {table} WHERE trade_date=?", (today_str,))}
        except Exception:
            _done = set()
    if _done:
        _before = len(tickers)
        tickers = [t for t in tickers if t not in _done]
        log(f"RESUME: {len(_done)} tickers already captured for {today_str} "
            f"-> fetching remaining {len(tickers)}/{_before} (use --fresh to refetch all)")
    else:
        # nothing to resume: clear the day once, then APPEND per chunk (crash-safe)
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
        newly = _add_to_skip(perm)
        log(f"no options   : {', '.join(perm)}  (not optionable anywhere"
            + (f" — auto-added to openbb_skip.txt, never fetched again" if newly else " — already in openbb_skip.txt")
            + ")")
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

    # --full: capture -> skew -> derive, in-process (no subprocess)
    if getattr(args, "full", False):
        _sc = sqlite3.connect(OB_DB, timeout=30)
        if getattr(args, "rebuild", False):
            _dates = [r[0] for r in _sc.execute(
                "SELECT DISTINCT trade_date FROM options_openbb ORDER BY trade_date")]
            print(f"\n--rebuild: whole-history pass over {len(_dates)} capture dates")
        else:
            _dates = _derive_scope(_sc)
            print(f"\nderive scope: {_dates or 'nothing to do'}")
        # SKEW RUNS FIRST, and the order matters: _build_serving_layer merges skew_snapshot
        # for the SAME date, so with skew last a day's atm_iv/skew25/pcvol were written NULL
        # and only got filled when the next night's whole-history rebuild happened to redo
        # them. Measured 2026-08-12: daily_ticker_summary 2026-08-11 had 0/734 atm_iv while
        # every older date had ~720. Scoping to one day without this reorder would have made
        # those three columns permanently NULL.
        print(f"\n{'='*60}\n  skew_snapshot\n{'='*60}")
        try:
            if _dates:
                build_skew(_sc, dates=_dates)
        finally:
            _sc.close()
        print(f"\n{'='*60}\n  derive (options_daily/options_change/stock_daily)\n{'='*60}")
        derive(dates=_dates, do_stock=True)


# ═══════════════════════════════════════════════════════════════════════════════
# DERIVE — raw options_openbb -> options_daily / options_change / stock_daily
# (ported from NYSE_OpenBB_derive.py; runs in-process when --full is passed)
# ═══════════════════════════════════════════════════════════════════════════════

_OPTIONS_DAILY_CORE = [
    "ticker", "asset_type", "company_name", "strike", "expiry_date", "trade_date",
    "openInt_Call", "lastPrice_Call", "vol_Call",
    "openInt_Put", "lastPrice_Put", "vol_Put",
    "contractSymbol_Call", "contractSymbol_Put", "load_date",
]


def _current_load_date():
    return datetime.now().strftime("%Y-%m-%d")


def _ensure_columns(df, required):
    for c in required:
        if c not in df.columns:
            df[c] = np.nan
    return df


def _name_map(conn):
    try:
        d = pd.read_sql("SELECT DISTINCT ticker, company_name, asset_type FROM options_daily", conn)
        return {str(r.ticker).upper(): (r.company_name, r.asset_type)
                for _, r in d.iterrows() if pd.notna(r.company_name)}
    except Exception:
        return {}


def _map_raw_to_options_daily(conn, date):
    raw = pd.read_sql(
        "SELECT ticker, strike, expiry_date, openInt_Call, openInt_Put, vol_Call, vol_Put, "
        "lastPrice_Call, lastPrice_Put, contractSymbol_Call, contractSymbol_Put "
        "FROM options_openbb WHERE trade_date=?", conn, params=(date,))
    if raw.empty:
        print(f"  {date}: options_openbb empty — skip"); return 0
    raw["ticker"] = raw["ticker"].str.upper()
    nm = _name_map(conn)
    raw["company_name"] = raw["ticker"].map(lambda t: nm.get(t, (t, "stock"))[0])
    raw["asset_type"]   = raw["ticker"].map(lambda t: nm.get(t, (t, "stock"))[1])
    raw["trade_date"]   = date
    raw["load_date"]    = _current_load_date()
    raw = _ensure_columns(raw, _OPTIONS_DAILY_CORE)
    out = raw[_OPTIONS_DAILY_CORE].copy()
    try:
        conn.execute("DELETE FROM options_daily WHERE trade_date=?", (date,)); conn.commit()
    except Exception:
        pass
    out.to_sql("options_daily", conn, if_exists="append", index=False)
    conn.commit()
    print(f"  {date}: mapped {len(out)} rows -> options_daily")
    return len(out)


def _compute_oi_vol_change(trade_day, db_path=OB_DB):
    trade_date_now_db = trade_day.strftime("%Y-%m-%d")
    print(f"Computing OI/vol changes for {trade_date_now_db}...")
    conn = sqlite3.connect(db_path, timeout=30)
    row = conn.execute("SELECT DISTINCT trade_date FROM options_daily WHERE trade_date < ? "
                       "ORDER BY trade_date DESC LIMIT 1", (trade_date_now_db,)).fetchone()
    if not row:
        print("  no previous date — skip"); conn.close(); return None
    prev = row[0]
    df_now  = pd.read_sql("SELECT * FROM options_daily WHERE trade_date=?", conn, params=(trade_date_now_db,))
    df_prev = pd.read_sql("SELECT * FROM options_daily WHERE trade_date=?", conn, params=(prev,))
    if df_now.empty or df_prev.empty:
        print("  today/prev empty — skip"); conn.close(); return None
    req  = ['ticker','company_name','asset_type','strike','expiry_date','trade_date',
            'openInt_Call','openInt_Put','vol_Call','vol_Put','lastPrice_Call','lastPrice_Put']
    ohlc = ['call_open','call_high','call_low','call_close','put_open','put_high','put_low','put_close']
    df_now  = _ensure_columns(df_now,  req + ohlc)
    df_prev = _ensure_columns(df_prev, req + ohlc)
    for df in (df_now, df_prev):
        df['expiry_date'] = pd.to_datetime(df['expiry_date'].astype(str), errors='coerce').dt.strftime("%Y-%m-%d")
        df['strike'] = pd.to_numeric(df['strike'], errors='coerce')
    merged = pd.merge(df_now, df_prev, on=['ticker','strike','expiry_date'], suffixes=('_now','_prev'), how='inner')
    if merged.empty:
        print("  no overlapping rows"); conn.close(); return None
    for c in ['openInt_Call_now','openInt_Call_prev','openInt_Put_now','openInt_Put_prev',
              'vol_Call_now','vol_Call_prev','vol_Put_now','vol_Put_prev']:
        if c in merged.columns: merged[c] = merged[c].fillna(0)
    merged['change_OI_Call']  = merged['openInt_Call_now'] - merged['openInt_Call_prev']
    merged['change_OI_Put']   = merged['openInt_Put_now']  - merged['openInt_Put_prev']
    merged['change_vol_Call'] = merged['vol_Call_now']     - merged['vol_Call_prev']
    merged['change_vol_Put']  = merged['vol_Put_now']      - merged['vol_Put_prev']
    def pct(now, prev): return np.where(prev == 0, np.nan, (now - prev) / prev * 100)
    merged['pct_change_OI_Call']  = pct(merged['openInt_Call_now'],  merged['openInt_Call_prev'])
    merged['pct_change_OI_Put']   = pct(merged['openInt_Put_now'],   merged['openInt_Put_prev'])
    merged['pct_change_vol_Call'] = pct(merged['vol_Call_now'],      merged['vol_Call_prev'])
    merged['pct_change_vol_Put']  = pct(merged['vol_Put_now'],       merged['vol_Put_prev'])
    lc = merged["lastPrice_Call_now"] = merged["lastPrice_Call_now"].fillna(0)
    lp = merged["lastPrice_Put_now"]  = merged["lastPrice_Put_now"].fillna(0)
    for f in ("open","high","low","close"):
        merged[f"call_{f}_now"] = lc; merged[f"put_{f}_now"] = lp
    merged["R1"] = merged["R12"] = merged["strike"] + lc
    merged["S1"] = merged["S12"] = merged["strike"] - lp
    cols_out = [
        'ticker','company_name_now','asset_type_now','strike','expiry_date','trade_date_now',
        'openInt_Call_now','openInt_Call_prev','change_OI_Call','pct_change_OI_Call',
        'openInt_Put_now','openInt_Put_prev','change_OI_Put','pct_change_OI_Put',
        'vol_Call_now','vol_Call_prev','change_vol_Call','pct_change_vol_Call',
        'vol_Put_now','vol_Put_prev','change_vol_Put','pct_change_vol_Put',
        'lastPrice_Call_now','lastPrice_Put_now',
        'call_open_now','call_high_now','call_low_now','call_close_now',
        'put_open_now','put_high_now','put_low_now','put_close_now',
        'R1','S1','R12','S12']
    merged = _ensure_columns(merged, cols_out)
    df_out = merged[cols_out].copy()
    df_out["trade_date_now"] = trade_date_now_db
    df_out["load_date"] = _current_load_date()
    try:
        conn.execute("DELETE FROM options_change WHERE trade_date_now=?", (trade_date_now_db,)); conn.commit()
    except Exception:
        pass
    df_out.to_sql("options_change", conn, if_exists="append", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oc_date ON options_change(trade_date_now)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_od_date ON options_daily(trade_date)")
    conn.execute("ANALYZE"); conn.commit(); conn.close()
    print(f"  appended {len(df_out)} rows -> options_change")
    return len(df_out)


def _finnhub_eod(tickers, timeout=10):
    """{ticker: OHLC} from Finnhub /quote. Empty dict when no key.

    THE POINT OF THIS LANE: yfinance is scraped, and a DATACENTER IP gets flagged by Yahoo
    within roughly 50 requests -- this step makes ~730 a night, so the whole EOD pipeline is
    unrunnable from any cloud host on yfinance alone. Finnhub is a keyed, official API, so
    IP reputation does not apply. Measured 0.13s per quote; the binding limit is the free
    tier's 60 calls/min, so ~730 tickers costs ~12 min.

    /quote returns o/h/l/c but NO volume -- volume comes back NaN here, deliberately, rather
    than being faked from another source.
    """
    key = os.environ.get("FINNHUB_API_KEY") or os.environ.get("FINNHUB_KEY")
    if not key:
        return {}
    import urllib.request as _u, json as _j, time as _t
    out, budget = {}, 60.0 / 60.0        # free tier: 60/min -> 1s spacing
    for i, tk in enumerate(tickers):
        try:
            with _u.urlopen(f"https://finnhub.io/api/v1/quote?symbol={tk}&token={key}",
                            timeout=timeout) as r:
                d = _j.loads(r.read())
            if d.get("c"):
                out[tk] = {"open": d.get("o"), "high": d.get("h"),
                           "low": d.get("l"), "close": d.get("c"), "volume": np.nan}
        except Exception:
            pass
        if i % 55 == 54:                  # stay under the per-minute cap
            _t.sleep(60 * budget)
    return out


def _capture_eod(trade_day_str, db_path=OB_DB):
    """{ticker: OHLC} from the spot ALREADY captured in options_openbb — zero API calls.

    `underlying_price` was persisted for exactly this (2026-07-30). It covers ~99.6% of the
    universe. IT IS NOT THE OFFICIAL CLOSE: it is the spot at chain-capture time, measured
    0.00-0.87% from the settled close. That is why this is the LAST resort and not the
    default -- writing an intraday value into a `close` column is the same class of error
    that corrupted stock_history on 2026-07-30 (AAPL 312.33 vs a true 333.43).
    """
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        df = pd.read_sql(
            "SELECT ticker, MAX(underlying_price) AS px FROM options_openbb "
            "WHERE trade_date=? AND underlying_price IS NOT NULL GROUP BY ticker",
            conn, params=(trade_day_str,))
        conn.close()
    except Exception:
        return {}
    return {r["ticker"]: {"open": np.nan, "high": np.nan, "low": np.nan,
                          "close": float(r["px"]), "volume": np.nan}
            for _, r in df.iterrows() if r["px"] and r["px"] == r["px"]}


def _build_stock_daily(trade_day, all_tickers, db_path=OB_DB):
    trade_day_str = trade_day.strftime("%Y-%m-%d")
    print(f"Building stock_daily for {trade_day_str}...")
    # Source order is env-selectable so a cloud host can avoid yfinance entirely without a
    # code change, and so the local nightly run keeps its existing behaviour by default.
    #   NYSE_PRICE_SOURCE = yfinance (default) | finnhub | capture
    src = (os.environ.get("NYSE_PRICE_SOURCE") or "yfinance").strip().lower()
    prices = {}
    if src == "finnhub":
        prices = _finnhub_eod(all_tickers)
        print(f"  price source: finnhub ({len(prices)}/{len(all_tickers)})")
    elif src == "capture":
        prices = _capture_eod(trade_day_str, db_path)
        print(f"  price source: captured spot ({len(prices)}/{len(all_tickers)}) "
              f"— NOT the official close, see _capture_eod")
    if not prices and src != "yfinance":
        prices = _capture_eod(trade_day_str, db_path)
        print(f"  falling back to captured spot ({len(prices)})")
    if not prices and yf is None:
        print("  no price source available — skip stock_daily"); return None

    # ONE query for the whole day's OI instead of one per ticker. The old loop opened a new
    # sqlite connection per ticker -- 730 connects a night (~4s/date, ID 229).
    try:
        _c = sqlite3.connect(db_path, timeout=30)
        _oi = pd.read_sql(
            "SELECT ticker, SUM(COALESCE(openInt_Call,0)) AS coi, "
            "SUM(COALESCE(openInt_Put,0)) AS poi FROM options_daily "
            "WHERE trade_date=? GROUP BY ticker", _c, params=(trade_day_str,))
        _c.close()
        oi_map = {r["ticker"]: (r["coi"], r["poi"]) for _, r in _oi.iterrows()}
    except Exception:
        oi_map = {}

    session = curl_requests.Session(impersonate="chrome") if (curl_requests and yf) else None
    records = []
    for ticker in all_tickers:
        try:
            px = prices.get(ticker)
            if px is None:
                if yf is None:
                    continue
                tk  = yf.Ticker(ticker, session=session)
                end = (trade_day + timedelta(days=1)).strftime("%Y-%m-%d")
                hist = tk.history(start=trade_day_str, end=end, interval="1d")
                if hist.empty: hist = tk.history(period="1d")
                if hist.empty: continue
                r = hist.iloc[-1]
                px = {"open": float(r.get("Open", np.nan)), "high": float(r.get("High", np.nan)),
                      "low": float(r.get("Low", np.nan)), "close": float(r.get("Close", np.nan)),
                      "volume": float(r.get("Volume", np.nan))}
            coi, poi = oi_map.get(ticker, (0, 0))
            records.append({"ticker": ticker, "trade_date": trade_day_str,
                            "open": px["open"], "high": px["high"],
                            "low": px["low"], "close": px["close"],
                            "volume": px["volume"],
                            "pcr_oi": (poi / coi if coi > 0 else np.nan),
                            "load_date": _current_load_date()})
        except Exception as e:
            print(f"  stock_daily {ticker}: {e}"); continue
    if not records:
        print("  stock_daily: no records"); return None
    df_stock = pd.DataFrame(records)
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        conn.execute("DELETE FROM stock_daily WHERE trade_date=?", (trade_day_str,)); conn.commit()
    except Exception:
        pass
    df_stock.to_sql("stock_daily", conn, if_exists="append", index=False)
    conn.close()
    print(f"  stock_daily: {len(df_stock)} rows")
    return df_stock


def _build_serving_layer(conn, dates=None):
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_ticker_summary (
        trade_date TEXT, ticker TEXT, n_strikes INTEGER,
        call_oi REAL, put_oi REAL, pcr_oi REAL,
        call_oi_chg REAL, put_oi_chg REAL, net_oi_chg REAL,
        call_vol REAL, put_vol REAL, call_notional REAL, put_notional REAL,
        spot REAL, atm_iv REAL, skew25 REAL, pcvol REAL, gex_notional REAL,
        PRIMARY KEY (trade_date, ticker))""")
    try: conn.execute("ALTER TABLE daily_ticker_summary ADD COLUMN gex_notional REAL")
    except Exception: pass
    if dates is None:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT trade_date_now FROM options_change").fetchall()]
    for d in dates:
        agg = pd.read_sql("""SELECT UPPER(ticker) ticker, COUNT(*) n_strikes,
            SUM(COALESCE(openInt_Call_now,0)) call_oi, SUM(COALESCE(openInt_Put_now,0)) put_oi,
            SUM(COALESCE(change_OI_Call,0)) call_oi_chg, SUM(COALESCE(change_OI_Put,0)) put_oi_chg,
            SUM(COALESCE(vol_Call_now,0)) call_vol, SUM(COALESCE(vol_Put_now,0)) put_vol,
            SUM(COALESCE(lastPrice_Call_now,0)*COALESCE(openInt_Call_now,0)*100) call_notional,
            SUM(COALESCE(lastPrice_Put_now,0)*COALESCE(openInt_Put_now,0)*100) put_notional,
            SUM(COALESCE(openInt_Call_now,0)*strike) _c_oi_k,
            SUM(COALESCE(openInt_Put_now,0)*strike) _p_oi_k
            FROM options_change WHERE trade_date_now=? GROUP BY UPPER(ticker)""", conn, params=(d,))
        if agg.empty: continue
        agg = agg.drop_duplicates(subset=["ticker"])
        agg["pcr_oi"]       = agg.put_oi / agg.call_oi.replace(0, np.nan)
        agg["net_oi_chg"]   = agg.call_oi_chg - agg.put_oi_chg
        agg["gex_notional"] = agg["_c_oi_k"] - agg["_p_oi_k"]
        sd = pd.read_sql("SELECT UPPER(ticker) ticker, close spot FROM stock_daily WHERE trade_date=?",
                         conn, params=(d,)).drop_duplicates("ticker")
        agg = agg.merge(sd, on="ticker", how="left")
        try:
            sk = pd.read_sql("SELECT UPPER(ticker) ticker, atm_iv, skew25, pcvol FROM skew_snapshot "
                             "WHERE trade_date=?", conn, params=(d,)).drop_duplicates("ticker")
            agg = agg.merge(sk, on="ticker", how="left")
        except Exception:
            agg["atm_iv"] = agg["skew25"] = agg["pcvol"] = np.nan
        agg = agg.drop_duplicates(subset=["ticker"])
        agg["trade_date"] = d
        cols = ["trade_date","ticker","n_strikes","call_oi","put_oi","pcr_oi",
                "call_oi_chg","put_oi_chg","net_oi_chg","call_vol","put_vol",
                "call_notional","put_notional","spot","atm_iv","skew25","pcvol","gex_notional"]
        for c in cols:
            if c not in agg.columns: agg[c] = np.nan
        try:
            conn.execute("DELETE FROM daily_ticker_summary WHERE trade_date=?", (d,))
            agg[cols].to_sql("daily_ticker_summary", conn, if_exists="append", index=False)
            print(f"  serving layer {d}: {len(agg)} tickers")
        except Exception as e:
            print(f"  serving layer {d} failed: {e}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dts_date ON daily_ticker_summary(trade_date)")
    conn.commit()


def _build_fundamentals(conn, min_oi=10000, max_names=500):
    if yf is None:
        print("  yfinance unavailable — skip fundamentals"); return 0
    import datetime as _dt
    today = _dt.date.today().isoformat()
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_fundamentals (
        ticker TEXT PRIMARY KEY, asof TEXT, beta REAL, market_cap REAL, sector TEXT)""")
    d = conn.execute("SELECT MAX(trade_date_now) FROM options_change").fetchone()[0]
    liq = [r[0] for r in conn.execute(
        "SELECT UPPER(ticker) FROM options_change WHERE trade_date_now=? GROUP BY UPPER(ticker) "
        "HAVING SUM(COALESCE(openInt_Call_now,0)+COALESCE(openInt_Put_now,0))>=? "
        "ORDER BY 1 LIMIT ?", (d, min_oi, max_names)).fetchall() if not r[0].startswith("^")]
    done = {r[0] for r in conn.execute("SELECT ticker FROM daily_fundamentals WHERE asof=?", (today,))}
    todo = [t for t in liq if t not in done]
    print(f"  fundamentals: {len(liq)} liquid, {len(todo)} to fetch")
    n = 0
    for tk in todo:
        try:
            i = yf.Ticker(tk).info or {}
            conn.execute("INSERT OR REPLACE INTO daily_fundamentals (ticker,asof,beta,market_cap,sector) "
                         "VALUES (?,?,?,?,?)", (tk, today, i.get("beta"), i.get("marketCap"),
                                                i.get("sector") or ""))
            n += 1
            if n % 25 == 0: conn.commit()
        except Exception:
            continue
    conn.commit()
    print(f"  fundamentals: {n} tickers written")
    return n


def _derive_scope(conn, target=None):
    """The dates the nightly derive actually has to touch.

    Every step here is a PURE function of data that does not change after capture:
    step 1 rewrites options_daily from options_openbb, step 2 joins a day against the one
    before it, step 4 aggregates that day's options_change. Re-running an old date therefore
    reproduces byte-identical rows. The old loop ran all of them every night anyway — 29
    capture dates, ~50 min of the ~57 min derive, growing ~2 min per night as history
    accrues (measured 2026-08-12, see IDEA_TRACKER 224-229).

    Scope = the captured day PLUS any capture date genuinely MISSING downstream, so a night
    that died mid-run still self-heals on the next one without paying for a full rebuild.
    Whole history remains available on demand via --rebuild.
    """
    cap = [r[0] for r in conn.execute(
        "SELECT DISTINCT trade_date FROM options_openbb ORDER BY trade_date")]
    if not cap:
        return []
    want = {target or cap[-1]}
    for tbl, col in (("options_daily", "trade_date"), ("options_change", "trade_date_now"),
                     ("stock_daily", "trade_date"), ("daily_ticker_summary", "trade_date"),
                     ("skew_snapshot", "trade_date")):
        try:
            have = {r[0] for r in conn.execute(f"SELECT DISTINCT {col} FROM {tbl}")}
        except Exception:
            continue                      # table not created yet — first run
        want |= (set(cap) - have)
    return [d for d in cap if d in want]


def derive(dates=None, do_stock=False):
    """Full derive pipeline: options_daily -> options_change -> stock_daily -> serving layer."""
    conn = sqlite3.connect(OB_DB, timeout=30)
    all_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT trade_date FROM options_openbb ORDER BY trade_date")]
    dates = all_dates if dates is None else [d for d in dates if d]
    if not dates:
        print("derive: nothing in scope — skipping"); conn.close(); return
    print(f"\nOpenBB derive -> {OB_DB}\ncapture dates: {len(all_dates)} "
          f"({all_dates[0]}..{all_dates[-1]})\nprocessing: {dates}")
    print("\nSTEP 1: map raw -> options_daily")
    # STEP 2 joins each day against the PREVIOUS capture date, so that day must exist in
    # options_daily — it normally does, from its own night. Map it only when it is actually
    # missing instead of re-mapping the whole history to guarantee it.
    have = {r[0] for r in conn.execute("SELECT DISTINCT trade_date FROM options_daily")}
    need = set(dates)
    for d in dates:
        prevs = [x for x in all_dates if x < d]
        if prevs and prevs[-1] not in have:
            need.add(prevs[-1])
    for d in sorted(need):
        _map_raw_to_options_daily(conn, d)
    conn.close()
    print("\nSTEP 2: compute_oi_vol_change")
    for d in dates:
        try: _compute_oi_vol_change(datetime.strptime(d, "%Y-%m-%d"))
        except Exception as e: print(f"  {d}: change failed: {e}")
    if do_stock:
        print("\nSTEP 3: build_stock_daily")
        c = sqlite3.connect(OB_DB, timeout=30)
        tickers = [r[0] for r in c.execute(
            "SELECT DISTINCT ticker FROM options_daily WHERE trade_date=?", (dates[-1],))]
        c.close()
        for d in dates:
            try: _build_stock_daily(datetime.strptime(d, "%Y-%m-%d"), tickers)
            except Exception as e: print(f"  {d}: stock_daily failed: {e}")
    print("\nSTEP 4: build serving layer")
    c = sqlite3.connect(OB_DB, timeout=30)
    try: _build_serving_layer(c, dates=dates)
    except Exception as e: print(f"  serving layer failed: {e}")
    finally: c.close()
    print("\nSTEP 5: build fundamentals")
    c = sqlite3.connect(OB_DB, timeout=30)
    try: _build_fundamentals(c)
    except Exception as e: print(f"  fundamentals failed: {e}")
    finally: c.close()


# ═══════════════════════════════════════════════════════════════════════════════
# SKEW SNAPSHOT — IV metrics panel from options_openbb
# (ported from skew_snapshot.py; runs in-process when --full is passed)
# ═══════════════════════════════════════════════════════════════════════════════

def _skew_metrics(g):
    g = g.copy()
    for c in ("iv_Call","iv_Put","delta_Call","delta_Put","vol_Call","vol_Put",
              "openInt_Call","openInt_Put","bid_Call","ask_Call","bid_Put","ask_Put"):
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g = g[(g.dte >= 10) & (g.dte <= 45)]
    if g.empty: return None
    exp = g.expiry_date.value_counts().idxmax()
    e   = g[g.expiry_date == exp]
    gc  = e[(e.iv_Call > 0.01) & e.delta_Call.between(0.05, 0.7)]
    gp  = e[(e.iv_Put  > 0.01) & e.delta_Put.between(-0.7, -0.05)]
    if len(gc) < 2 or len(gp) < 2: return None
    c25 = gc.iloc[(gc.delta_Call - 0.25).abs().argmin()]
    c50 = gc.iloc[(gc.delta_Call - 0.50).abs().argmin()]
    p25 = gp.iloc[(gp.delta_Put  + 0.25).abs().argmin()]
    p50 = gp.iloc[(gp.delta_Put  + 0.50).abs().argmin()]
    def relspr(row, side):
        b, a = row[f"bid_{side}"], row[f"ask_{side}"]
        m = (b + a) / 2
        return (a - b) / m if (m and m > 0 and a >= b) else np.nan
    liq = np.nanmedian([relspr(c50, "Call"), relspr(p50, "Put")])
    vc, vp = e.vol_Call.sum(), e.vol_Put.sum()
    oc, op = e.openInt_Call.sum(), e.openInt_Put.sum()
    return {"skew25": p25.iv_Put - c25.iv_Call,
            "atm_iv": np.nanmean([c50.iv_Call, p50.iv_Put]),
            "pc_iv":  p50.iv_Put - c50.iv_Call,
            "pcvol":  (vp / vc) if vc else np.nan,
            "pcoi":   (op / oc) if oc else np.nan,
            "liq": liq}


def build_skew(conn, dates=None):
    """Compute skew_snapshot metrics from options_openbb into skew_snapshot table.

    `dates=None` still means every capture date (manual rebuilds rely on that); the nightly
    path passes the derive scope so it does one day instead of the whole history.
    """
    conn.execute("""CREATE TABLE IF NOT EXISTS skew_snapshot (
        trade_date TEXT, ticker TEXT, skew25 REAL, atm_iv REAL, pc_iv REAL,
        pcvol REAL, pcoi REAL, liq REAL, PRIMARY KEY (trade_date, ticker))""")
    conn.commit()
    if dates is None:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT trade_date FROM options_openbb ORDER BY trade_date")]
    print(f"skew_snapshot: dates {dates}")
    for d in dates:
        df = pd.read_sql(
            "SELECT ticker,strike,expiry_date,iv_Call,iv_Put,delta_Call,delta_Put,"
            "vol_Call,vol_Put,openInt_Call,openInt_Put,bid_Call,ask_Call,bid_Put,ask_Put "
            "FROM options_openbb WHERE trade_date=?", conn, params=(d,))
        df["dte"] = (pd.to_datetime(df.expiry_date, errors="coerce") - pd.to_datetime(d)).dt.days
        rows = []
        for tk, g in df.groupby("ticker"):
            m = _skew_metrics(g)
            if m:
                rows.append((d, tk, m["skew25"], m["atm_iv"], m["pc_iv"],
                             m["pcvol"], m["pcoi"], m["liq"]))
        conn.executemany("INSERT OR REPLACE INTO skew_snapshot "
                         "(trade_date,ticker,skew25,atm_iv,pc_iv,pcvol,pcoi,liq) "
                         "VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        print(f"  skew {d}: {len(rows)} tickers")


if __name__ == "__main__":
    main()
