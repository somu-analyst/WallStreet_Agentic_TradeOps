# -*- coding: utf-8 -*-
"""Export ONLY pre-approved, publishable data into a small separate database (ID 356).

WHY THIS EXISTS
    Row 356 originally tried a different approach: pick which existing dashboard PAGES are
    "safe" for a future public instance, by reading their name and description. That was
    verified wrong at the code level (2026-09-12) - 4 of 5 candidate "safe" pages turned out
    to have live vendor-data calls buried inside them (a gamma-wall scan against
    options_change, yfinance income-statement figures, historical price lookups). Auditing
    every function transitively forever is not a real safety strategy; one missed call is a
    real leak.

    This script is the replacement design: ONE reviewable choke point. It runs on a schedule,
    reads specific pre-approved tables, and writes ONLY the shape decided here into a small
    separate database. Whatever public app eventually reads this database can never leak more
    than what this file explicitly puts in it - the export step, not the display step, is
    where "is this safe to show a stranger" gets decided.

WHAT'S IN, AND WHY EACH ONE IS SAFE
    1. 13F institutional holdings (edgar_13f) - a REQUIRED PUBLIC SEC DISCLOSURE. Every fund
       above $100M AUM must file this quarterly; it is not vendor-licensed data at all, the
       same category as the SEC-filed Sankey segment splits. Exported as-is.
    2. Signal accuracy, AGGREGATED only (by model_name + signal, never per-ticker-per-date).
       The raw signal_accuracy table has a row per (ticker, date, model) with the model's
       actual call and the market's actual return - exporting that granularly would reveal
       day-by-day trading calls on specific names, which is a different and much larger
       disclosure than "here is how rigorously this system validates itself." The aggregate
       (hit-rate and edge per model, N observations) is the genuinely public-worthy part: it
       demonstrates the walk-forward validation discipline (docs/architecture, bot-conventions
       "never tune a parameter on the data you then judge it on") without exposing what the
       system said about any specific name on any specific day.

WHAT'S DELIBERATELY NOT IN
    Anything touching options_change / options_daily / options_openbb / stock_daily /
    stock_history directly (CBOE/Finnhub/Yahoo licensed, personal-use only - the finding that
    started row 356), anything from a live dashboard page render, and any raw per-observation
    signal_accuracy row.

Usage:
    python tools/export_public_data.py              # writes public_export.db next to the DB
    python tools/export_public_data.py --dry-run     # show row counts, write nothing
"""
import argparse
import os
import sqlite3
import sys

SRC_DB = os.environ.get("NYSE_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "US_data_OpenBB.db")
DST_DB = os.path.join(os.path.dirname(os.path.abspath(SRC_DB)), "public_export.db")


def export_13f(src, dst, quarters_back=8):
    """Public SEC 13F disclosures, most recent N quarters only (keeps the export small and
    current; older quarters are of diminishing public interest and cost nothing to drop)."""
    quarters = [r[0] for r in src.execute(
        "SELECT DISTINCT quarter FROM edgar_13f ORDER BY quarter DESC LIMIT ?",
        (quarters_back,))]
    if not quarters:
        return 0
    placeholders = ",".join("?" * len(quarters))
    rows = src.execute(
        f"SELECT fund, quarter, filing_date, cusip, issuer, shares, value, put_call "
        f"FROM edgar_13f WHERE quarter IN ({placeholders})", quarters).fetchall()
    dst.execute("""CREATE TABLE IF NOT EXISTS public_13f (
        fund TEXT, quarter TEXT, filing_date TEXT, cusip TEXT, issuer TEXT,
        shares REAL, value REAL, put_call TEXT)""")
    dst.execute("DELETE FROM public_13f")
    dst.executemany(
        "INSERT INTO public_13f VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def export_signal_accuracy_aggregate(src, dst):
    """Per-model, per-signal AGGREGATE only. Never per-ticker, never per-date - see the
    module docstring for why that line is drawn there.

    `correct` is NOT a plain 0/1 flag - it carries three values (0, 1, -1) where -1 is an
    unresolved/pending observation (verified live 2026-09-14: 7,399 of 37,236 rows, ~20%%).
    AVG(correct) over all three silently treats "not graded yet" as "very wrong", which
    understated every hit rate by a wide margin before this filter was added - e.g.
    scn_building/BULL read 23.0%% including pending rows vs its real, resolved-only rate.
    N is counted the same way, over resolved rows only, so it matches what hit_rate_pct
    was actually computed from."""
    rows = src.execute("""
        SELECT model_name, signal, COUNT(*) AS n,
               ROUND(AVG(correct) * 100, 1) AS hit_rate_pct,
               ROUND(AVG(actual_ret) * 100, 3) AS avg_ret_pct,
               MIN(trade_date) AS first_date, MAX(trade_date) AS last_date
        FROM signal_accuracy
        WHERE correct IN (0, 1)
        GROUP BY model_name, signal
        HAVING n >= 10
        ORDER BY model_name, signal
    """).fetchall()
    dst.execute("""CREATE TABLE IF NOT EXISTS public_signal_accuracy (
        model_name TEXT, signal TEXT, n INTEGER, hit_rate_pct REAL,
        avg_ret_pct REAL, first_date TEXT, last_date TEXT)""")
    dst.execute("DELETE FROM public_signal_accuracy")
    dst.executemany(
        "INSERT INTO public_signal_accuracy VALUES (?,?,?,?,?,?,?)", rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = sqlite3.connect(SRC_DB)
    src.row_factory = None

    if args.dry_run:
        n13f = src.execute("SELECT COUNT(DISTINCT quarter) FROM edgar_13f "
                            "WHERE quarter IN (SELECT DISTINCT quarter FROM edgar_13f "
                            "ORDER BY quarter DESC LIMIT 8)").fetchone()[0]
        nsig = src.execute("SELECT COUNT(*) FROM (SELECT model_name, signal FROM "
                            "signal_accuracy WHERE correct IN (0, 1) GROUP BY "
                            "model_name, signal HAVING COUNT(*) >= 10)").fetchone()[0]
        print(f"[dry-run] would export {n13f} quarters of 13F data, "
              f"{nsig} model/signal aggregate rows. Nothing written.")
        src.close()
        return

    dst = sqlite3.connect(DST_DB)
    n1 = export_13f(src, dst)
    n2 = export_signal_accuracy_aggregate(src, dst)
    dst.commit()
    dst.close()
    src.close()
    print(f"Exported {n1} 13F rows, {n2} signal-accuracy aggregate rows -> {DST_DB}")


if __name__ == "__main__":
    main()
