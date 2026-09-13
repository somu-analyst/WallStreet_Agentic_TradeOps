# -*- coding: utf-8 -*-
"""Build a small, fully-functional slice of the primary DB for first upload to the cloud host.

WHY A SLICE (cloud tracker, 2026-08-27)
    The full store is 5.03 GB and hours of home-broadband upload. Measured, 94.8% of its rows
    are the three option-chain tables:

        options_daily   8,268,860   34.3%
        options_change  7,717,386   32.0%
        options_openbb  6,858,341   28.5%
        all 36 others   ~1,250,000   5.2%

    The live system does not need chain HISTORY. GEX, walls, OI intent, the scanners and the
    dashboard all read the most recent date; only backtests reach back. But it very much does
    need the small tables in FULL -- signal_accuracy is the hit-rate evidence, stock_history is
    multi-year OHLCV behind momentum and RS, and trades is the book (and the tax clock).

    So: every table complete, except the three chain tables which are cut to --days. That is a
    few hundred MB instead of 5 GB, and nothing in the bot is crippled by it. The chain history
    can be topped up later without redoing any of this.

Usage:
    python tools/make_cloud_db.py                    # last 10 days of chains
    python tools/make_cloud_db.py --days 3
    python tools/make_cloud_db.py --out C:/path/slice.db
"""
import os
import sqlite3
import sys
import time

SRC = os.environ.get("NYSE_DB_PATH") or r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db"
OUT = r"C:\Users\srini\db_cloud_slice.db"
BIG = ("options_daily", "options_change", "options_openbb")


def _date_col(cur, table):
    """The chain tables disagree on the name: options_openbb has trade_date, options_change has
    trade_date_now. Detect rather than assume -- guessing wrong silently copies the whole table."""
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{table}")')]
    for c in ("trade_date_now", "trade_date", "date"):
        if c in cols:
            return c
    return None


def main():
    days = 10
    out = OUT
    argv = sys.argv[1:]
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if os.path.exists(out):
        print(f"FATAL: {out} already exists -- delete it or pass --out elsewhere")
        return 1

    t0 = time.time()
    src = sqlite3.connect(SRC)
    src.row_factory = None
    cur = src.cursor()
    dst = sqlite3.connect(out)
    dst.execute("PRAGMA journal_mode=OFF")
    dst.execute("PRAGMA synchronous=OFF")

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    schema = {r[0]: r[1] for r in cur.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")}

    print(f"source {SRC}\n  ->   {out}\n{len(tables)} tables · chains cut to last {days} days\n")
    total = 0
    for t in tables:
        dst.execute(schema[t])
        ncols = len(list(cur.execute(f'PRAGMA table_info("{t}")')))
        where = ""
        if t in BIG:
            if days <= 0:
                # --days 0 = schema only for the chain tables. Note this must be explicit:
                # falling through to a LIMIT 0 date lookup returns no cut-off, which would
                # leave `where` empty and copy the whole 8M-row table -- the opposite of asked.
                where = " WHERE 1=0"
            else:
                dc = _date_col(cur, t)
                if dc:
                    cut = [r[0] for r in cur.execute(
                        f'SELECT DISTINCT "{dc}" FROM "{t}" ORDER BY "{dc}" DESC LIMIT {days}')]
                    if cut:
                        where = f' WHERE "{dc}" >= \'{cut[-1]}\''
        rows = cur.execute(f'SELECT * FROM "{t}"{where}')
        ph = ",".join("?" * ncols)
        n = 0
        while True:
            chunk = rows.fetchmany(20000)
            if not chunk:
                break
            dst.executemany(f'INSERT INTO "{t}" VALUES ({ph})', chunk)
            n += len(chunk)
        dst.commit()
        total += n
        flag = f"  (last {days} days)" if where else ""
        print(f"  {t:<26}{n:>12,}{flag}")

    # Indexes last: building them after the inserts is markedly faster than maintaining them
    # during, and the copy is write-once.
    print("\nindexes...")
    for name, sql in cur.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"):
        try:
            dst.execute(sql)
        except Exception as e:
            print(f"  skip {name}: {e}")
    dst.commit()
    dst.close()
    src.close()

    mb = os.path.getsize(out) / 1e6
    full = os.path.getsize(SRC) / 1e6
    print(f"\n{total:,} rows · {mb:.0f} MB  ({100*mb/full:.1f}% of the {full/1000:.2f} GB source) "
          f"· {time.time()-t0:.0f}s")
    print(f"\nnext:  scp -i C:\\Users\\srini\\oci-nyse.key {out} "
          f"ubuntu@150.136.41.250:~/US_data_OpenBB.db")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
