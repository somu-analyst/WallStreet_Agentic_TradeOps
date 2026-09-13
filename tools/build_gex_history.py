# -*- coding: utf-8 -*-
"""Rebuild a historical GEX panel so the gamma-wall signal can finally be SCORED.

WHY THIS EXISTS
    `gamma_wall_trades` is empty. GEX, the zero-gamma flip and the call/put walls are computed
    LIVE and never stored, so every claim made about them -- that price pins to the wall, that
    negative GEX means trending -- has never been checked against what price actually did next.
    CLAUDE.md is explicit that "test" here means proving a signal would have been right, and
    that is impossible without a panel.

    This writes one row per (ticker, capture date) into `gex_history`. Once it exists, the wall
    and flip can be joined to forward returns and run through tools/walkforward.py like any
    other signal.

WHAT IT GETS RIGHT THAT A NAIVE VERSION WOULD NOT
    Spot is read from the SNAPSHOT, not from today. `_compute_gex` scales by spot squared and
    locates the flip relative to spot, so passing the current price into a July date produces
    numbers that look plausible and mean nothing.

    Nothing here chooses a parameter, so it is a fixed-signal computation and may be scored with
    `daily_ic` directly. The moment a threshold gets tuned -- "how far from the wall counts as
    near" -- that tuning has to go through walk_forward instead (bot-conventions.md).

Usage:
    python tools/build_gex_history.py --limit 20        # try it on 20 tickers first
    python tools/build_gex_history.py                   # full panel
    python tools/build_gex_history.py --since 2026-08-01
"""
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DDL = """
CREATE TABLE IF NOT EXISTS gex_history (
    trade_date   TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    spot         REAL,
    expiry       TEXT,
    dte          INTEGER,
    total_gex    REAL,
    total_gex_m  REAL,
    zero_gamma   REAL,
    call_wall    REAL,
    put_wall     REAL,
    gex_signal   TEXT,
    regime       TEXT,
    PRIMARY KEY (trade_date, ticker)
)
"""


def main():
    argv = sys.argv[1:]
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    since = argv[argv.index("--since") + 1] if "--since" in argv else None

    import telegram_bot_optimized as bot
    conn = bot.get_conn()
    conn.execute(DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gexh_date ON gex_history(trade_date)")
    conn.commit()

    # Spot must be the price the chain was written against on THAT date -- GEX scales by spot
    # squared and the flip is located relative to spot, so today's price in a July row produces
    # numbers that look convincing and mean nothing.
    #
    # underlying_price is the first choice but is only populated on 23 of 42 capture dates; the
    # earlier ones are null or zero. Filtering on `> 0` therefore silently dropped 20 dates and
    # the first build covered 30 Jul - 28 Aug rather than the full history, which is exactly the
    # kind of quiet halving of a sample that makes a backtest look conclusive when it is thin
    # (found 2026-09-01). stock_daily.close covers all 20, so fall back to it rather than
    # discard the date.
    q = ("SELECT o.trade_date, o.ticker, "
         "       COALESCE(NULLIF(MAX(o.underlying_price), 0), MAX(s.close)) AS spot "
         "FROM options_openbb o "
         "LEFT JOIN stock_daily s ON s.ticker = o.ticker AND s.trade_date = o.trade_date ")
    params = []
    if since:
        q += "WHERE o.trade_date >= ? "
        params.append(since)
    q += ("GROUP BY o.trade_date, o.ticker HAVING spot > 0 "
          "ORDER BY o.trade_date, o.ticker")
    rows = conn.execute(q, params).fetchall()
    if limit:
        seen, keep = set(), []
        for d, t, s in rows:                       # keep `limit` distinct tickers, all dates
            if t not in seen and len(seen) >= limit:
                continue
            seen.add(t); keep.append((d, t, s))
        rows = keep

    done = conn.execute("SELECT trade_date || '|' || ticker FROM gex_history").fetchall()
    done = {r[0] for r in done}
    todo = [r for r in rows if f"{r[0]}|{r[1]}" not in done]
    print(f"{len(rows):,} ticker-days in scope · {len(done):,} already built · {len(todo):,} to do")
    if not todo:
        print("nothing to do"); conn.close(); return 0

    t0, wrote, empty = time.time(), 0, 0
    for i, (date_str, tk, spot) in enumerate(todo, 1):
        try:
            g = bot._compute_gex(tk, conn, float(spot), as_of=date_str)
        except Exception:
            empty += 1
            continue
        if not g or g.get("expiry") is None:
            empty += 1                             # no liquid expiry that day -- not an error
            continue
        conn.execute(
            "INSERT OR REPLACE INTO gex_history (trade_date,ticker,spot,expiry,dte,total_gex,"
            "total_gex_m,zero_gamma,call_wall,put_wall,gex_signal,regime) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (date_str, tk, float(spot), g.get("expiry"), g.get("dte"), g.get("total_gex"),
             g.get("total_gex_m"), g.get("zero_gamma"), g.get("call_wall"), g.get("put_wall"),
             g.get("gex_signal"), g.get("regime")))
        wrote += 1
        if i % 500 == 0:
            conn.commit()
            rate = i / max(time.time() - t0, .01)
            print(f"  {i:,}/{len(todo):,} · {wrote:,} written · {empty:,} no-expiry · "
                  f"{rate:.0f}/s · ETA {(len(todo)-i)/max(rate,.01)/60:.0f}m")
    conn.commit()

    n, d, t = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT trade_date), COUNT(DISTINCT ticker) "
        "FROM gex_history").fetchone()
    print(f"\ngex_history: {n:,} rows · {d} dates · {t:,} tickers · {time.time()-t0:.0f}s")
    print(f"  written this run {wrote:,} · skipped (no liquid expiry) {empty:,}")
    conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
