# -*- coding: utf-8 -*-
"""Deep-verify everything marked DONE. Does the feature ACTUALLY work, right now?

Written because ID 92 ("morning brief does not mention Japan") was marked DONE while the
brief the user actually receives still had no Japan in it — the fix had landed in a
different function with a similar name. A status column is a claim; this is the check.

Each probe calls the REAL function and asserts on its OUTPUT, not on whether it imports.
Anything that cannot be probed automatically is reported as MANUAL, never as PASS.
"""
import html as _h
import re
import sys
import traceback

sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA")
sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA\_lib")
sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA\tools")
import telegram_bot_optimized as tb

A = lambda x: str(x).encode("ascii", "replace").decode()
PASS, FAIL, MANUAL = [], [], []


def probe(rid, name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        FAIL.append((rid, name, f"EXCEPTION {type(e).__name__}: {e}"))
        print(f"  FAIL  {str(rid):>5} {name:<44} EXCEPTION {type(e).__name__}")
        traceback.print_exc(limit=1)
        return
    (PASS if ok else FAIL).append((rid, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {str(rid):>5} {name:<44} {A(detail)[:60]}")


def _tables_ok(txt, max_w=28):
    """ALIGNMENT is the correctness property: every line of a <pre> table must be the same
    display width, or the columns visibly stagger. Width vs the 28-cell mobile guideline is
    reported separately — several long-standing tables (/paper 61, positions 38) exceed it by
    design, so failing on it would flag pre-existing debt as a regression in this feature."""
    over = []
    for b in re.findall(r"<pre>(.*?)</pre>", txt or "", re.S):
        w = {tb._disp_w(_h.unescape(l)) for l in b.splitlines() if l.strip()}
        if len(w) != 1:
            return False, f"MISALIGNED, widths {w}"
        if max(w) > max_w:
            over.append(max(w))
    return True, (f"aligned (wide: {over} > {max_w})" if over else "aligned")


def _tags_ok(txt):
    for t in ("b", "i", "pre"):
        if (txt or "").count(f"<{t}>") != (txt or "").count(f"</{t}>"):
            return False, f"<{t}> unbalanced"
    return True, ""


conn = tb.get_conn()
print("=" * 104)
print("DEEP VERIFICATION OF 'DONE' ITEMS")
print("=" * 104)

# ---- 92: the one that was falsely DONE -------------------------------------------------
def t92():
    txt = tb._fmt_briefing(tb.morning_briefing(conn))
    need = ["japan", "nikkei", "overnight"]
    miss = [k for k in need if k not in txt.lower()]
    ok_t, w = _tables_ok(txt)
    ok_g, g = _tags_ok(txt)
    return (not miss and ok_t and ok_g,
            f"missing={miss or 'none'} {w} {g}".strip())
probe(92, "morning brief mentions Japan/overnight", t92)

# ---- 169 dealer ------------------------------------------------------------------------
def t169():
    d = tb._fmt_dealer()
    if not d:
        return False, "no output"
    ok_t, w = _tables_ok(d)
    return ("PERCENTILE" in d.upper() or "pctile" in d) and ok_t, w or "has pctile framing"
probe(169, "/dealer renders with percentile framing", t169)

# ---- 132 whatif ------------------------------------------------------------------------
def t132():
    rows, meta = tb._ep_scenario(conn, "GLD", 5.0)
    if not rows:
        return False, str(meta)
    d = {t: imp for t, _b, imp, _dl in rows}
    return abs(d["GLD"] - 5.0) < 0.15, f"view honoured GLD={d['GLD']:.2f}"
probe(132, "/whatif entropy pooling honours the view", t132)

# ---- 195 xirr --------------------------------------------------------------------------
def t195():
    from datetime import datetime as dt
    r = tb._xirr([(dt(2025, 1, 1), -100), (dt(2026, 1, 1), 110)])
    rows = tb._xirr_book(conn)
    short_ok = all(h["xirr"] is None for _s, h in rows if h["days"] < 30)
    return (abs(r - 0.10) < 0.005 and rows and short_ok,
            f"solver ok, {len(rows)} holdings, short-suppression={short_ok}")
probe(195, "/xirr math + short-holding suppression", t195)

# ---- 39 india --------------------------------------------------------------------------
def t39():
    c = tb._india_conn()
    n = c.execute("SELECT COUNT(*) FROM india_daily").fetchone()[0]
    avg = c.execute("SELECT AVG(deliv_pct) FROM india_daily").fetchone()[0]
    c.close()
    txt = tb._fmt_india()
    ok_t, w = _tables_ok(txt)
    return (n > 100 and 0 < avg < 100 and txt and ok_t,
            f"{n} rows, avg delivery {avg:.1f}%, own DB {w}")
probe(39, "/india own DB + real delivery %", t39)

# ---- 197 two-decimal cap ---------------------------------------------------------------
def t197():
    t = tb._pipe_table(("A", "B"), [("3.14159", "x"), ("2026-08-07", "y")])
    body = _h.unescape(t)
    return ("3.14" in body and "3.14159" not in body and "2026-08-07" in body,
            "rounds numbers, leaves dates")
probe(197, "2dp cap in _pipe_table", t197)

# ---- 194 UPPER() index fix -------------------------------------------------------------
def t194():
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\telegram_bot_optimized.py",
               encoding="utf-8").read()
    n = len(re.findall(r"UPPER\(ticker\)\s*=\s*\?", src))
    plan = conn.execute("EXPLAIN QUERY PLAN SELECT 1 FROM options_openbb WHERE ticker=? "
                        "AND trade_date=?", ("NVDA", "2026-08-07")).fetchone()[-1]
    return n == 0 and "SEARCH" in plan, f"{n} UPPER sites left, plan={plan[:38]}"
probe(194, "UPPER(ticker) removed, index used", t194)

# ---- 27 dropped columns ----------------------------------------------------------------
def t27():
    cols = [d[1] for d in conn.execute("PRAGMA table_info(options_daily)")]
    dead = [c for c in cols if re.match(r"^(money_|vol_rank_|chg_oi_)", c)]
    n = conn.execute("SELECT COUNT(*) FROM options_daily").fetchone()[0]
    live = [c for c in cols if c.endswith("_info")]
    # Row count GROWS every capture — pinning it to the exact count at drop time (5,953,485)
    # made this fail the first evening new data landed. What the drop had to preserve is that
    # nothing was lost, so the floor is the assertion.
    return (not dead and n >= 5953485 and len(live) == 8,
            f"{len(cols)} cols, {len(dead)} dead left, {len(live)} _info kept, {n:,} rows")
probe(27, "dead cols dropped, live _info kept", t27)

# ---- 190 why ---------------------------------------------------------------------------
def t190():
    p1, v1 = tb._narr_verdict(conn, "SPY", "up", 5)
    p2, v2 = tb._narr_verdict(conn, "SPY", "down", 5)
    return (not (v1 == "SUPPORTED" and v2 == "SUPPORTED"),
            f"opposite claims -> {v1}/{v2} (price decides)")
probe(190, "/why verdict is price-driven", t190)

# ---- 183 llm ---------------------------------------------------------------------------
def t183():
    st = tb._llm_status()
    conf = [n for n, _m, ok in st if ok]
    txt, who = tb._llm_chat("Reply with exactly: OK", max_tokens=10)
    return bool(txt), f"configured={conf} live={who}"
probe(183, "free-LLM lane answers live", t183)

# ---- 35.5 dispersion -------------------------------------------------------------------
def t355():
    n = conn.execute("SELECT COUNT(*) FROM dispersion_daily").fetchone()[0]
    return n >= 5, f"{n} sessions stored (needs history before it signals)"
probe(35.5, "dispersion accruing", t355)

# ---- 93 macro vintages -----------------------------------------------------------------
def t93():
    n = conn.execute("SELECT COUNT(*) FROM macro_vintages").fetchone()[0]
    return n > 0, f"{n} vintage rows"
probe(93, "macro vintages accruing", t93)

# ---- menu discoverability --------------------------------------------------------------
def tmenu():
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\telegram_bot_optimized.py",
               encoding="utf-8").read()
    h = set(re.findall(r'app\.add_handler\(CommandHandler\("(\w+)"', src))
    m = set(re.findall(r'BotCommand\("(\w+)"', src))
    return not (h - m), f"{len(h)} handlers, missing from menu: {sorted(h - m) or 'none'}"
probe("-", "every command discoverable", tmenu)


# ---- 200/201/202: flags, /positions, foreign tickers ------------------------------------
def t201():
    want = {"RELIANCE.NS": "IN", "7203.T": "JP", "BABA": "CN", "INFY": "IN", "TSM": "TW",
            "MELI": "AR", "INDA": "IN", "AAPL": "US", "SPY": "US", "MDT": "US"}
    cc = lambda f: "".join(chr(ord(c) - 0x1F1E6 + 65) for c in f if 0x1F1E6 <= ord(c) <= 0x1F1FF)
    bad = [t for t, e in want.items() if cc(tb._ticker_flag(t, conn)) != e]
    # a flag is ONE glyph: 2 cells, not 4 — this is what keeps headers aligned with rows
    w_ok = tb._disp_w("\U0001F1FA\U0001F1F8") == 2
    return not bad and w_ok, f"{len(want) - len(bad)}/{len(want)} correct, flag width 2={w_ok}"
probe(201, "country flag resolver + table width", t201)


def t201b():
    txt = tb._fmt_paper(conn) + tb._fmt_watchlist(conn)
    ok_t, w = _tables_ok(txt)
    n = len(re.findall(r"[\U0001F1E6-\U0001F1FF]{2}", txt))
    return n > 0 and ok_t, f"{n} flags rendered, tables aligned {w}"
probe(201, "flags reach /paper and /watchlist", t201b)


def t202():
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\telegram_bot_optimized.py",
               encoding="utf-8").read()
    reg = 'CommandHandler("positions"' in src and 'BotCommand("positions"' in src
    return reg and callable(getattr(tb, "positions_command", None)), f"registered={reg}"
probe(202, "/positions command exists", t202)


def t200():
    good = [["RELIANCE.NS", "stock", "10", "@1400"], ["7203.T", "stock", "5", "@2800"],
            ["POWERINDIA.NS", "stock", "2", "@36050"], ["BRK.B", "stock", "1", "@450"]]
    bad = [tb._parse_add_args(a)[1] for a in good]
    return not any(bad), f"{len(good)} foreign symbols parse; errors={[b for b in bad if b]}"
probe(200, "long/foreign tickers parse in /add", t200)


for rid, name in [(97, "sticky columns scroll right"), (102, "Exit Planner vertical space"),
                  (109, "pinned columns visual check")]:
    MANUAL.append((rid, name))
    print(f"  MANL  {rid:>5} {name:<44} needs your eyes (canvas-rendered)")

conn.close()
print("=" * 104)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} FAILED, {len(MANUAL)} manual")
for rid, n, d in FAIL:
    print(f"   FAILED {rid}: {n} -- {A(d)[:80]}")
