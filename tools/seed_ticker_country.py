# -*- coding: utf-8 -*-
"""Resolve the country of every symbol in the book and cache it in `ticker_country`.

WHY THIS IS A TOOL AND NOT PART OF RENDERING: yfinance `.info` costs 1-2s per symbol. Doing
it inside /positions would blow Telegram's timeout on first render. So `_ticker_flag()` stays
purely offline (suffix -> curated map -> this cache -> default US) and this script fills the
cache out of band. Run it after adding foreign names; it only queries symbols that the static
maps cannot already resolve, so a repeat run is nearly free.

    python tools/seed_ticker_country.py            # resolve unknowns
    python tools/seed_ticker_country.py --show     # print the whole book with its flags
    python tools/seed_ticker_country.py TSM MELI   # force-resolve specific symbols
"""
import sys

sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA")
sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA\_lib")
import telegram_bot_optimized as tb

A = lambda x: str(x).encode("ascii", "replace").decode()
SHOW = "--show" in sys.argv
FORCE = [a.upper() for a in sys.argv[1:] if not a.startswith("-")]


def book_symbols(conn):
    """Every symbol the user actually holds or watches — the only ones worth resolving."""
    out = []
    for q in ("SELECT DISTINCT ticker FROM trades WHERE status='OPEN'",
              "SELECT DISTINCT ticker FROM paper_trades WHERE status='OPEN'",
              "SELECT DISTINCT ticker FROM watchlist WHERE status='ACTIVE'"):
        try:
            out += [str(r[0]).upper() for r in conn.execute(q) if r[0]]
        except Exception:
            pass                      # table may not exist yet — not an error
    return sorted(set(out))


conn = tb.get_conn()
tb._flag_setup(conn)
syms = FORCE or book_symbols(conn)
print(f"{len(syms)} symbols in the book")

if SHOW:
    for s in syms:
        print(f"  {A(tb._ticker_flag(s, conn))}  {s}")
    conn.close()
    sys.exit(0)

# A symbol is "unknown" when the offline lanes fall through to the 🇺🇸 default AND it has no
# cache row — a real US name and an unresolved one look identical from the outside, so the
# cache row is what tells them apart on the next run.
cached = {str(r[0]).upper() for r in conn.execute("SELECT ticker FROM ticker_country")}
todo = [s for s in syms if s not in cached and "." not in s
        and s not in (tb._FLAG_STATIC or {}) and tb._ticker_flag(s, conn) == "🇺🇸"]
if FORCE:
    todo = FORCE
print(f"{len(todo)} need a network lookup: {A(todo)}")

import datetime as _dt

wrote = 0
for s in todo:
    country, flag = None, None
    try:
        country = (tb._yf_ticker(s).info or {}).get("country")
    except Exception as e:
        print(f"  {s}: lookup failed ({type(e).__name__})")
    if country:
        flag = tb._COUNTRY_NAME_FLAG.get(country)
        if not flag:
            print(f"  {s}: country '{A(country)}' has no flag in _COUNTRY_NAME_FLAG - add it")
    # Cache the miss as US too: without a row we would re-query this symbol forever.
    conn.execute("INSERT OR REPLACE INTO ticker_country VALUES (?,?,?,?)",
                 (s, flag or "\U0001F1FA\U0001F1F8", country or "United States",
                  _dt.date.today().isoformat()))
    wrote += 1
    print(f"  {s:<8} {A(country) or '(no data -> US)':<20} {A(flag or 'US')}")
conn.commit()

tb._FLAG_DB = None                    # drop the process cache so the next read sees the writes
print(f"\nwrote {wrote} rows. Book now reads:")
for s in syms:
    print(f"  {A(tb._ticker_flag(s, conn))}  {s}")
conn.close()
