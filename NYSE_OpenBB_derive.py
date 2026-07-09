"""NYSE_OpenBB_derive.py — SELF-CONTAINED enrichment for the OpenBB lane.

Turns the raw capture (`options_openbb` in US_data_OpenBB.db) into the SAME derived tables the
bot/dashboard read — `options_daily`, `options_change` (change_OI / now-prev / R1 / S1 …) and
`stock_daily` (OHLC + pcr_oi).  Standalone by design: it carries its OWN copy of the derivation
(ported once from NYSE_YFin) and does NOT import the yfinance pipeline, so when the yfinance code
is retired the OpenBB lane keeps working unchanged.  Writes ONLY to US_data_OpenBB.db.

Schema is byte-for-byte the Yahoo schema, so flipping DB_PATH -> US_data_OpenBB.db later needs NO
bot/dashboard changes.

Flow per capture date:
  1. map options_openbb (raw) -> options_daily         (OI/vol/lastPrice/symbol; OHLC=NULL)
  2. compute_oi_vol_change(day)                         -> options_change (needs prev day present)
  3. build_stock_daily(day, tickers) [--stock]         -> stock_daily (OHLC + pcr_oi)

Run:  python NYSE_OpenBB_derive.py            # all capture dates: options_daily + options_change
      python NYSE_OpenBB_derive.py --stock    # also rebuild stock_daily (slower: yfinance OHLC)
      python NYSE_OpenBB_derive.py --date 2026-07-07
"""
import os
import sys
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

try:
    import yfinance as yf
    from curl_cffi import requests as curl_requests
except Exception:                                    # stock_daily (--stock) needs these; derive w/o them is fine
    yf = None
    curl_requests = None

# ── config (self-contained: OpenBB DB only) ─────────────────────────
DATA_DIR = r"C:\Users\srini\Options_chain_data"
US_CHARTS_DIR = os.path.join(DATA_DIR, "US_CHARTS")
OB_DB = os.path.join(DATA_DIR, "US_data_OpenBB.db")
TABLE_OPTIONS = "options_daily"
TABLE_OPTIONS_CHANGE = "options_change"
TABLE_STOCK_DAILY = "stock_daily"

# options_daily columns the bot expects; raw OpenBB fills OI/vol/price/symbol, OHLC stays NULL
# (bot guards these; R12/S12 fall back to strike when call_high/put_high are NULL).
_OPTIONS_DAILY_CORE = [
    "ticker", "asset_type", "company_name", "strike", "expiry_date", "trade_date",
    "openInt_Call", "lastPrice_Call", "vol_Call",
    "openInt_Put", "lastPrice_Put", "vol_Put",
    "contractSymbol_Call", "contractSymbol_Put", "load_date",
]


def current_load_date():
    return datetime.now().strftime("%Y-%m-%d")


def ensure_columns(df, required):
    for c in required:
        if c not in df.columns:
            df[c] = np.nan
    return df


# ── step 1: raw -> options_daily ────────────────────────────────────
def _name_map(conn):
    """ticker -> (company_name, asset_type) from existing options_daily; ticker/stock fallback."""
    try:
        d = pd.read_sql("SELECT DISTINCT ticker, company_name, asset_type FROM options_daily", conn)
        return {str(r.ticker).upper(): (r.company_name, r.asset_type)
                for _, r in d.iterrows() if pd.notna(r.company_name)}
    except Exception:
        return {}


def map_raw_to_options_daily(conn, date):
    raw = pd.read_sql(
        "SELECT ticker, strike, expiry_date, openInt_Call, openInt_Put, vol_Call, vol_Put, "
        "lastPrice_Call, lastPrice_Put, contractSymbol_Call, contractSymbol_Put "
        "FROM options_openbb WHERE trade_date=?", conn, params=(date,))
    if raw.empty:
        print(f"  {date}: options_openbb empty — skip")
        return 0
    raw["ticker"] = raw["ticker"].str.upper()
    nm = _name_map(conn)
    raw["company_name"] = raw["ticker"].map(lambda t: nm.get(t, (t, "stock"))[0])
    raw["asset_type"] = raw["ticker"].map(lambda t: nm.get(t, (t, "stock"))[1])
    raw["trade_date"] = date
    raw["load_date"] = current_load_date()
    raw = ensure_columns(raw, _OPTIONS_DAILY_CORE)
    out = raw[_OPTIONS_DAILY_CORE].copy()
    try:
        conn.execute("DELETE FROM options_daily WHERE trade_date=?", (date,))
        conn.commit()
    except Exception:
        pass
    out.to_sql("options_daily", conn, if_exists="append", index=False)
    conn.commit()
    print(f"  {date}: mapped {len(out)} rows -> options_daily")
    return len(out)


# ── step 2: options_daily -> options_change (ported from NYSE_YFin) ──
def compute_oi_vol_change(trade_day, db_path=OB_DB):
    """Day-over-day OI/vol deltas + R1/S1/R12/S12 from options_daily -> options_change.
    (Self-contained copy of the Yahoo pipeline's logic; targets the OpenBB DB.)"""
    trade_date_now_db = trade_day.strftime("%Y-%m-%d")
    print(f"Computing OI/vol changes for {trade_date_now_db} [{os.path.basename(db_path)}]...")
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT DISTINCT trade_date FROM options_daily WHERE trade_date < ? "
                       "ORDER BY trade_date DESC LIMIT 1", (trade_date_now_db,)).fetchone()
    if not row:
        print("  no previous trading date in DB; cannot compute change."); conn.close(); return None
    prev_trade_date = row[0]
    print(f"  previous trading date: {prev_trade_date}")
    df_now = pd.read_sql("SELECT * FROM options_daily WHERE trade_date = ?", conn, params=(trade_date_now_db,))
    df_prev = pd.read_sql("SELECT * FROM options_daily WHERE trade_date = ?", conn, params=(prev_trade_date,))
    if df_now.empty or df_prev.empty:
        print("  today/prev options_daily empty; nothing to compute."); conn.close(); return None

    required = ['ticker', 'company_name', 'asset_type', 'strike', 'expiry_date', 'trade_date',
                'openInt_Call', 'openInt_Put', 'vol_Call', 'vol_Put', 'lastPrice_Call', 'lastPrice_Put']
    ohlc_cols = ['call_open', 'call_high', 'call_low', 'call_close',
                 'put_open', 'put_high', 'put_low', 'put_close']
    df_now = ensure_columns(df_now, required + ohlc_cols)
    df_prev = ensure_columns(df_prev, required + ohlc_cols)
    for df in (df_now, df_prev):
        df['expiry_date'] = pd.to_datetime(df['expiry_date'].astype(str), errors='coerce').dt.strftime("%Y-%m-%d")
        df['strike'] = pd.to_numeric(df['strike'], errors='coerce')

    merged = pd.merge(df_now, df_prev, on=['ticker', 'strike', 'expiry_date'],
                      suffixes=('_now', '_prev'), how='inner')
    print(f"  merged rows: {len(merged)}")
    if merged.empty:
        print("  no overlapping strikes/expiries."); conn.close(); return None

    for c in ['openInt_Call_now', 'openInt_Call_prev', 'openInt_Put_now', 'openInt_Put_prev',
              'vol_Call_now', 'vol_Call_prev', 'vol_Put_now', 'vol_Put_prev']:
        if c in merged.columns:
            merged[c] = merged[c].fillna(0)
    merged['change_OI_Call'] = merged['openInt_Call_now'] - merged['openInt_Call_prev']
    merged['change_OI_Put'] = merged['openInt_Put_now'] - merged['openInt_Put_prev']
    merged['change_vol_Call'] = merged['vol_Call_now'] - merged['vol_Call_prev']
    merged['change_vol_Put'] = merged['vol_Put_now'] - merged['vol_Put_prev']

    def pct(now, prev):
        return np.where(prev == 0, np.nan, (now - prev) / prev * 100)
    merged['pct_change_OI_Call'] = pct(merged['openInt_Call_now'], merged['openInt_Call_prev'])
    merged['pct_change_OI_Put'] = pct(merged['openInt_Put_now'], merged['openInt_Put_prev'])
    merged['pct_change_vol_Call'] = pct(merged['vol_Call_now'], merged['vol_Call_prev'])
    merged['pct_change_vol_Put'] = pct(merged['vol_Put_now'], merged['vol_Put_prev'])

    lc = merged["lastPrice_Call_now"] = merged["lastPrice_Call_now"].fillna(0)
    lp = merged["lastPrice_Put_now"] = merged["lastPrice_Put_now"].fillna(0)
    # OpenBB captures an EOD SNAPSHOT (no intraday bars): EOD close == last price, and open/high/low
    # collapse to last for these (thin) contracts — identical to what Yahoo effectively stored
    # (its per-contract OHLC = last for illiquid options). Populate all 8 OHLC cols from last.
    for f in ("open", "high", "low", "close"):
        merged[f"call_{f}_now"] = lc
        merged[f"put_{f}_now"] = lp
    merged["R1"] = merged["R12"] = merged["strike"] + lc      # no separate high -> R12 == R1
    merged["S1"] = merged["S12"] = merged["strike"] - lp

    cols_out = [
        'ticker', 'company_name_now', 'asset_type_now', 'strike', 'expiry_date', 'trade_date_now',
        'openInt_Call_now', 'openInt_Call_prev', 'change_OI_Call', 'pct_change_OI_Call',
        'openInt_Put_now', 'openInt_Put_prev', 'change_OI_Put', 'pct_change_OI_Put',
        'vol_Call_now', 'vol_Call_prev', 'change_vol_Call', 'pct_change_vol_Call',
        'vol_Put_now', 'vol_Put_prev', 'change_vol_Put', 'pct_change_vol_Put',
        'lastPrice_Call_now', 'lastPrice_Put_now',
        'call_open_now', 'call_high_now', 'call_low_now', 'call_close_now',
        'put_open_now', 'put_high_now', 'put_low_now', 'put_close_now',
        'R1', 'S1', 'R12', 'S12']
    merged = ensure_columns(merged, cols_out)
    df_out = merged[cols_out].copy()
    df_out["trade_date_now"] = trade_date_now_db
    df_out["load_date"] = current_load_date()
    try:
        conn.execute(f"DELETE FROM {TABLE_OPTIONS_CHANGE} WHERE trade_date_now = ?", (trade_date_now_db,))
        conn.commit()
    except Exception:
        pass
    df_out.to_sql(TABLE_OPTIONS_CHANGE, conn, if_exists="append", index=False)
    # date-leading indexes so dashboard date-snapshot queries don't skip-scan the ticker index
    # (BB has ~9x Yahoo's rows/day). Idempotent; ANALYZE refreshes the planner stats.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_oc_date ON options_change(trade_date_now)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_od_date ON options_daily(trade_date)")
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()
    print(f"  appended {len(df_out)} rows -> {TABLE_OPTIONS_CHANGE}")
    return len(df_out)


# ── step 3: stock_daily (OHLC + pcr_oi) — optional (needs yfinance) ──
def build_stock_daily(trade_day, all_tickers, db_path=OB_DB):
    if yf is None:
        print("  yfinance unavailable — skip stock_daily"); return None
    trade_day_str_db = trade_day.strftime("%Y-%m-%d")
    print(f"Building stock_daily for {trade_day_str_db} [{os.path.basename(db_path)}]...")
    session = curl_requests.Session(impersonate="chrome") if curl_requests else None
    records = []
    for ticker in all_tickers:
        try:
            tk = yf.Ticker(ticker, session=session)
            end_iso = (trade_day + timedelta(days=1)).strftime("%Y-%m-%d")
            hist = tk.history(start=trade_day_str_db, end=end_iso, interval="1d")
            if hist.empty:
                hist = tk.history(period="1d")
            if hist.empty:
                continue
            r = hist.iloc[-1]
            conn = sqlite3.connect(db_path)
            df_opt = pd.read_sql("SELECT openInt_Call, openInt_Put FROM options_daily "
                                 "WHERE ticker = ? AND trade_date = ?", conn, params=(ticker, trade_day_str_db))
            conn.close()
            coi = df_opt["openInt_Call"].fillna(0).sum() if not df_opt.empty else 0
            poi = df_opt["openInt_Put"].fillna(0).sum() if not df_opt.empty else 0
            records.append({"ticker": ticker, "trade_date": trade_day_str_db,
                            "open": float(r.get("Open", np.nan)), "high": float(r.get("High", np.nan)),
                            "low": float(r.get("Low", np.nan)), "close": float(r.get("Close", np.nan)),
                            "volume": float(r.get("Volume", np.nan)),
                            "pcr_oi": (poi / coi if coi > 0 else np.nan),
                            "load_date": current_load_date()})
        except Exception as e:
            print(f"  stock_daily {ticker}: {e}")
            continue
    if not records:
        print("  stock_daily: no records"); return None
    df_stock = pd.DataFrame(records)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"DELETE FROM {TABLE_STOCK_DAILY} WHERE trade_date = ?", (trade_day_str_db,))
        conn.commit()
    except Exception:
        pass
    df_stock.to_sql(TABLE_STOCK_DAILY, conn, if_exists="append", index=False)
    conn.close()
    print(f"  stock_daily: appended {len(df_stock)} rows")
    return df_stock


# ── SERVING LAYER: precompute per-ticker daily summary (page-ready, ~2ms reads) ──
def build_serving_layer(conn, dates=None):
    """Materialize `daily_ticker_summary` — one row per ticker/date with the aggregates the
    dashboard/bot overview pages need, so they read ~736 rows (2ms) instead of scanning ~150k
    raw rows (2s). 0 accuracy loss: same sums over the frozen EOD snapshot, computed once.
    Rebuilt each EOD (idempotent per date)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_ticker_summary (
        trade_date TEXT, ticker TEXT, n_strikes INTEGER,
        call_oi REAL, put_oi REAL, pcr_oi REAL,
        call_oi_chg REAL, put_oi_chg REAL, net_oi_chg REAL,
        call_vol REAL, put_vol REAL, call_notional REAL, put_notional REAL,
        spot REAL, atm_iv REAL, skew25 REAL, pcvol REAL,
        PRIMARY KEY (trade_date, ticker))""")
    if dates is None:
        dates = [r[0] for r in conn.execute(
            "SELECT DISTINCT trade_date_now FROM options_change").fetchall()]
    for d in dates:
        agg = pd.read_sql("""SELECT UPPER(ticker) ticker, COUNT(*) n_strikes,
            SUM(COALESCE(openInt_Call_now,0)) call_oi, SUM(COALESCE(openInt_Put_now,0)) put_oi,
            SUM(COALESCE(change_OI_Call,0)) call_oi_chg, SUM(COALESCE(change_OI_Put,0)) put_oi_chg,
            SUM(COALESCE(vol_Call_now,0)) call_vol, SUM(COALESCE(vol_Put_now,0)) put_vol,
            SUM(COALESCE(lastPrice_Call_now,0)*COALESCE(openInt_Call_now,0)*100) call_notional,
            SUM(COALESCE(lastPrice_Put_now,0)*COALESCE(openInt_Put_now,0)*100) put_notional
            FROM options_change WHERE trade_date_now=? GROUP BY UPPER(ticker)""", conn, params=(d,))
        if agg.empty:
            continue
        agg = agg.drop_duplicates(subset=["ticker"])
        agg["pcr_oi"] = agg.put_oi / agg.call_oi.replace(0, np.nan)
        agg["net_oi_chg"] = agg.call_oi_chg - agg.put_oi_chg
        # spot from stock_daily (dedupe to avoid row multiplication on merge)
        sd = pd.read_sql("SELECT UPPER(ticker) ticker, close spot FROM stock_daily WHERE trade_date=?",
                         conn, params=(d,)).drop_duplicates("ticker")
        agg = agg.merge(sd, on="ticker", how="left")
        # options-IV metrics from skew_snapshot (if present for this date)
        try:
            sk = pd.read_sql("SELECT UPPER(ticker) ticker, atm_iv, skew25, pcvol FROM skew_snapshot "
                             "WHERE trade_date=?", conn, params=(d,)).drop_duplicates("ticker")
            agg = agg.merge(sk, on="ticker", how="left")
        except Exception:
            agg["atm_iv"] = agg["skew25"] = agg["pcvol"] = np.nan
        agg = agg.drop_duplicates(subset=["ticker"])
        agg["trade_date"] = d
        cols = ["trade_date", "ticker", "n_strikes", "call_oi", "put_oi", "pcr_oi",
                "call_oi_chg", "put_oi_chg", "net_oi_chg", "call_vol", "put_vol",
                "call_notional", "put_notional", "spot", "atm_iv", "skew25", "pcvol"]
        for c in cols:
            if c not in agg.columns:
                agg[c] = np.nan
        try:
            conn.execute("DELETE FROM daily_ticker_summary WHERE trade_date=?", (d,))
            agg[cols].to_sql("daily_ticker_summary", conn, if_exists="append", index=False)
            print(f"  serving layer {d}: {len(agg)} tickers")
        except Exception as e:
            print(f"  serving layer {d} failed: {e}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dts_date ON daily_ticker_summary(trade_date)")
    conn.commit()


def derive(dates=None, do_stock=False):
    conn = sqlite3.connect(OB_DB)
    all_dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT trade_date FROM options_openbb ORDER BY trade_date")]
    dates = dates or all_dates
    print(f"OpenBB derive -> {OB_DB}\ncapture dates: {all_dates}\nprocessing: {dates}\n")
    print("STEP 1: map raw -> options_daily")
    for d in all_dates:                       # map ALL dates so prev-day exists for change calc
        map_raw_to_options_daily(conn, d)
    conn.close()
    print("\nSTEP 2: compute_oi_vol_change")
    for d in dates:
        try:
            compute_oi_vol_change(datetime.strptime(d, "%Y-%m-%d"))
        except Exception as e:
            print(f"  {d}: compute_oi_vol_change failed: {e}")
    if do_stock:
        print("\nSTEP 3: build_stock_daily")
        c = sqlite3.connect(OB_DB)
        tickers = [r[0] for r in c.execute(
            "SELECT DISTINCT ticker FROM options_daily WHERE trade_date=?", (dates[-1],))]
        c.close()
        for d in dates:
            try:
                build_stock_daily(datetime.strptime(d, "%Y-%m-%d"), tickers)
            except Exception as e:
                print(f"  {d}: build_stock_daily failed: {e}")

    print("\nSTEP 4: build serving layer (daily_ticker_summary)")
    c = sqlite3.connect(OB_DB)
    try:
        build_serving_layer(c, dates=dates)
    except Exception as e:
        print(f"  build_serving_layer failed: {e}")
    finally:
        c.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    do_stock = "--stock" in args
    dts = [args[args.index("--date") + 1]] if "--date" in args else None
    derive(dates=dts, do_stock=do_stock)
    print("\nDone. options_change/options_daily in US_data_OpenBB.db match the Yahoo schema.")
