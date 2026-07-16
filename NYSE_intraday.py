"""NYSE_intraday.py — market-hours intraday capture lane (2026-07-15).

Writes US_intraday.db (its OWN file — no writer contention with the EOD jobs):
  intraday_bars  : 1-minute OHLCV bars, FOCUS universe = open-position tickers
                   (trades table, main DB) + ~30 liquid leaders. One batched
                   yf.download per sweep; full-day upsert each sweep so gaps
                   self-heal (Yahoo keeps ~7 days of 1m history — persistence
                   here IS the value).
  intraday_chain : option-chain snapshots every CHAIN_EVERY_MIN, open-position
                   tickers only. Source = CBOE CDN delayed quotes (15-min
                   delayed, refreshes all day, keyless): spot, ATM IV,
                   call/put volume, PCR-vol, top-volume strikes.

NOTE: OI updates once daily (OCC) — the intraday edge is volume-pace /
IV-shift / price ONLY. Consumers live in telegram_bot_optimized.py:
/live writeup, /heat scanner, heat_streamer_alert (push on state change).

Run:  python NYSE_intraday.py          loop during market hours, exit after close
      python NYSE_intraday.py --once   single sweep (bars + chains), any time
Console output is ASCII-only (Windows cp1252).
"""
import os
import re
import sys
import time
import json
import sqlite3
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

DATA_DIR = r"C:\Users\srini\Options_chain_data"
IDB_PATH = os.path.join(DATA_DIR, "US_intraday.db")
MAIN_DB = os.environ.get("NYSE_DB_PATH") or os.path.join(DATA_DIR, "US_data_OpenBB.db")

# ~30 liquid leaders always captured alongside open positions
LEADERS = [
    "SPY", "QQQ", "IWM", "DIA", "SMH", "SOXX", "XLF", "XLE", "XLK", "XLV",
    "XLI", "XBI", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA",
    "AMD", "AVGO", "MU", "NFLX", "JPM", "GS", "BA", "CAT", "XOM", "CVX", "PLTR",
]

SWEEP_SEC = 60            # 1-minute bar sweep cadence
CHAIN_EVERY_MIN = 30      # option-chain snapshot cadence (open positions only)
KEEP_DAYS = 45            # purge rows older than this at startup

# Market-hours gate in UTC: union of EDT (13:30-20:00) and EST (14:30-21:00)
# sessions +5 min tail, so the lane runs the full session year-round without a
# tz database; at most one quiet extra hour on each edge (harmless upserts).
GATE_OPEN_MIN = 13 * 60 + 30
GATE_CLOSE_MIN = 21 * 60 + 5

_OPT_RE = re.compile(r"^([A-Z]+)(\d{6})([CP])(\d{8})$")


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}Z] {msg}", flush=True)


def _conn():
    c = sqlite3.connect(IDB_PATH, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def ensure_schema():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS intraday_bars (
            ticker TEXT NOT NULL, trade_date TEXT NOT NULL, ts TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume INTEGER,
            PRIMARY KEY (ticker, ts))""")
        c.execute("""CREATE TABLE IF NOT EXISTS intraday_chain (
            ticker TEXT NOT NULL, trade_date TEXT NOT NULL, ts_utc TEXT NOT NULL,
            spot REAL, atm_iv REAL, call_vol INTEGER, put_vol INTEGER,
            pcr_vol REAL, top_call_strike REAL, top_call_vol INTEGER,
            top_put_strike REAL, top_put_vol INTEGER,
            PRIMARY KEY (ticker, ts_utc))""")
        c.execute("CREATE INDEX IF NOT EXISTS ix_bars_day ON intraday_bars(trade_date, ticker)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_chain_day ON intraday_chain(trade_date, ticker)")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).date().isoformat()
        c.execute("DELETE FROM intraday_bars WHERE trade_date < ?", (cutoff,))
        c.execute("DELETE FROM intraday_chain WHERE trade_date < ?", (cutoff,))


def focus_universe():
    """Open-position tickers (main DB) + leaders, deduped, order preserved."""
    pos = []
    try:
        with sqlite3.connect(MAIN_DB, timeout=15) as c:
            pos = [str(r[0]).upper() for r in c.execute(
                "SELECT DISTINCT ticker FROM trades WHERE status='OPEN'").fetchall()]
    except Exception as e:
        log(f"WARN positions read failed ({e}); leaders only")
    seen, out = set(), []
    for t in pos + LEADERS:
        t = t.strip().upper()
        if t and t not in seen and "." not in t:   # skip .NS etc — US lane only
            seen.add(t)
            out.append(t)
    return out, pos


def sweep_bars(tickers):
    """One batched 1m download; upsert ALL of today's bars (self-healing)."""
    try:
        df = yf.download(tickers, period="1d", interval="1m", group_by="ticker",
                         threads=True, progress=False, auto_adjust=False, prepost=False)
    except Exception as e:
        log(f"WARN bar download failed: {e}")
        return 0
    if df is None or df.empty:
        return 0
    rows = []
    for tk in tickers:
        try:
            sub = df[tk] if len(tickers) > 1 else df
        except Exception:
            continue
        if sub is None or sub.empty or "Close" not in sub:
            continue
        sub = sub.dropna(subset=["Close"])
        for ts, r in sub.iterrows():
            try:
                ts_l = ts.tz_localize(None) if ts.tzinfo else ts   # exchange-local (ET) naive
            except Exception:
                ts_l = ts
            rows.append((tk, ts_l.date().isoformat(), ts_l.strftime("%Y-%m-%d %H:%M"),
                         float(r["Open"]), float(r["High"]), float(r["Low"]),
                         float(r["Close"]), int(r.get("Volume") or 0)))
    if rows:
        with _conn() as c:
            c.executemany("INSERT OR REPLACE INTO intraday_bars VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _cboe_chain(tk):
    url = f"https://cdn.cboe.com/api/global/delayed_quotes/options/{tk.upper()}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def snapshot_chain(tk):
    """CBOE CDN delayed chain -> one summary row, or None."""
    try:
        data = _cboe_chain(tk).get("data") or {}
    except Exception as e:
        log(f"WARN chain {tk}: {e}")
        return None
    opts = data.get("options") or []
    spot = data.get("current_price") or data.get("close")
    if not opts or not spot:
        return None
    spot = float(spot)
    today = datetime.now(timezone.utc).date()
    cvol = pvol = 0
    call_by_strike, put_by_strike = {}, {}
    atm = []                                   # (expiry, iv) near-the-money
    for o in opts:
        m = _OPT_RE.match(str(o.get("option", "")))
        if not m:
            continue
        _, ymd, cp, kraw = m.groups()
        try:
            exp = datetime.strptime(ymd, "%y%m%d").date()
        except ValueError:
            continue
        if exp < today:
            continue
        strike = int(kraw) / 1000.0
        vol = int(o.get("volume") or 0)
        if cp == "C":
            cvol += vol
            call_by_strike[strike] = call_by_strike.get(strike, 0) + vol
        else:
            pvol += vol
            put_by_strike[strike] = put_by_strike.get(strike, 0) + vol
        iv = o.get("iv")
        if iv and abs(strike - spot) / spot <= 0.03:
            atm.append((exp, float(iv)))
    atm_iv = None
    if atm:
        near = min(e for e, _ in atm)          # nearest live expiry only
        ivs = [v for e, v in atm if e == near and 0 < v < 5]
        if ivs:
            atm_iv = sum(ivs) / len(ivs)
    tc = max(call_by_strike.items(), key=lambda kv: kv[1]) if call_by_strike else (None, 0)
    tp = max(put_by_strike.items(), key=lambda kv: kv[1]) if put_by_strike else (None, 0)
    now = datetime.now(timezone.utc)
    return (tk, (now - timedelta(hours=5)).date().isoformat(), now.strftime("%Y-%m-%dT%H:%M"),
            spot, atm_iv, cvol, pvol, round(pvol / cvol, 3) if cvol else None,
            tc[0], tc[1], tp[0], tp[1])


def sweep_chains(pos_tickers):
    rows = [r for r in (snapshot_chain(t) for t in pos_tickers) if r]
    if rows:
        with _conn() as c:
            c.executemany("INSERT OR REPLACE INTO intraday_chain VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                          rows)
    return len(rows)


def in_market_window(now_utc):
    if now_utc.weekday() >= 5:
        return False
    hm = now_utc.hour * 60 + now_utc.minute
    return GATE_OPEN_MIN <= hm <= GATE_CLOSE_MIN


def main():
    once = "--once" in sys.argv
    ensure_schema()
    tickers, pos = focus_universe()
    log(f"focus universe: {len(tickers)} tickers ({len(pos)} open-position + leaders)")
    last_chain = None
    last_universe = time.time()
    while True:
        now = datetime.now(timezone.utc)
        if once or in_market_window(now):
            if time.time() - last_universe > 1800:          # refresh positions every 30 min
                tickers, pos = focus_universe()
                last_universe = time.time()
            n = sweep_bars(tickers)
            log(f"bars upserted: {n}")
            if pos and (last_chain is None or (now - last_chain).total_seconds() >= CHAIN_EVERY_MIN * 60):
                k = sweep_chains(pos)
                last_chain = now
                log(f"chain snapshots: {k}/{len(pos)}")
            if once:
                log("single sweep done")
                return
        else:
            hm = now.hour * 60 + now.minute
            if hm > GATE_CLOSE_MIN and now.weekday() < 5:
                log("market closed - exiting (relaunch tomorrow or leave to a scheduler)")
                return
            log("outside market window - sleeping 5 min")
            time.sleep(300)
            continue
        time.sleep(SWEEP_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("stopped by user")
