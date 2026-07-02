"""NYSE_OpenBB_EOD.py — EOD *price* fetcher via OpenBB (the yfinance-style lane).

Companion to NYSE_OpenBB.py (which fetches OPTION CHAINS). This one pulls multi-year
daily OHLCV bars for the tracked universe and upserts them into `stock_history`
(ticker, trade_date, open, high, low, close, volume) — the DB-first history layer
the bot/dashboard read via `_daily_history`, and what the risk-off backtest uses.

OpenBB standardises ~100 providers. We pass provider="yfinance" for the freshest
EOD bar (OpenBB's default provider can lag a day), then fall back to its default.

Run:
    python NYSE_OpenBB_EOD.py                 # refresh whole tracked universe, ~2y
    python NYSE_OpenBB_EOD.py SPY QQQ SMH     # only these tickers
    python NYSE_OpenBB_EOD.py --years 5 SPY   # custom lookback
"""
import os
import sys
import sqlite3
import datetime as dt

DATA_DIR = r"C:\Users\srini\Options_chain_data"
DB_PATH = os.path.join(DATA_DIR, "US_data.db")


def _parse_args(argv):
    years, tickers, i = 2.0, [], 0
    while i < len(argv):
        a = argv[i]
        if a in ("--years", "-y") and i + 1 < len(argv):
            years = float(argv[i + 1]); i += 2; continue
        tickers.append(a.upper()); i += 1
    return years, tickers


def _default_universe(conn):
    """Whatever the DB already tracks — keeps this in sync with the bot's universe."""
    rows = conn.execute("SELECT DISTINCT ticker FROM stock_daily ORDER BY ticker").fetchall()
    if not rows:
        rows = conn.execute("SELECT DISTINCT ticker FROM stock_history ORDER BY ticker").fetchall()
    return [r[0] for r in rows]


def fetch_openbb(tk, start_date):
    """Return list of (ticker, YYYY-MM-DD, o, h, l, c, v), or [] on failure.
    Tries the freshest provider first (yfinance), then OpenBB's default fallback."""
    import pandas as pd
    from openbb import obb
    last_err = None
    for kwargs in ({"provider": "yfinance"}, {}):
        try:
            d = obb.equity.price.historical(symbol=tk, start_date=start_date, **kwargs).to_dataframe()
            if d is None or len(d) == 0:
                continue
            d = d.reset_index()
            cl = {c.lower(): c for c in d.columns}
            dcol = cl.get("date") or cl.get("index")

            def g(row, name):
                return float(row[cl[name]]) if name in cl and pd.notna(row[cl[name]]) else None

            out = []
            for _, row in d.iterrows():
                ds = pd.Timestamp(row[dcol]).strftime("%Y-%m-%d")
                out.append((tk, ds, g(row, "open"), g(row, "high"), g(row, "low"),
                            g(row, "close"), g(row, "volume")))
            if out:
                return out
        except Exception as e:                       # noqa: BLE001
            last_err = e
    if last_err:
        print(f"    ! {tk}: {str(last_err)[:90]}")
    return []


def upsert(conn, rows):
    conn.executemany(
        "INSERT OR REPLACE INTO stock_history "
        "(ticker, trade_date, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()


def main():
    years, tickers = _parse_args(sys.argv[1:])
    start = (dt.date.today() - dt.timedelta(days=int(years * 365.25))).isoformat()
    print(f"NYSE_OpenBB_EOD — DB={DB_PATH}")
    print(f"Lookback {years:g}y (from {start}) · provider=yfinance→default fallback\n")
    conn = sqlite3.connect(DB_PATH)
    try:
        universe = tickers or _default_universe(conn)
        print(f"Universe: {len(universe)} tickers\n")
        ok = miss = total = 0
        latest = None
        for n, tk in enumerate(universe, 1):
            rows = fetch_openbb(tk, start)
            if rows:
                upsert(conn, rows)
                ok += 1; total += len(rows)
                latest = max(latest, rows[-1][1]) if latest else rows[-1][1]
                print(f"  [{n:>3}/{len(universe)}] {tk:6} {len(rows):>4} bars → {rows[-1][1]}")
            else:
                miss += 1
                print(f"  [{n:>3}/{len(universe)}] {tk:6} no data")
        print(f"\nDone. {ok} ok / {miss} missing · {total:,} bars · latest EOD = {latest}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
