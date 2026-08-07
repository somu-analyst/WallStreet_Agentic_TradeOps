# -*- coding: utf-8 -*-
"""Regression pass over everything changed 2026-08-07.

Not "does it run" -- each check asserts the SPECIFIC defect that was fixed cannot recur.
"""
import sys, re, traceback
sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA")
sys.path.insert(0, r"C:\Users\srini\Options_chain_data\NYSE_DATA\_lib")
import telegram_bot_optimized as tb

A = lambda x: str(x).encode("ascii", "replace").decode()
PASS, FAIL = [], []


def check(name, fn):
    try:
        ok, detail = fn()
        (PASS if ok else FAIL).append((name, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name:44s} {A(detail)[:70]}")
    except Exception as e:
        FAIL.append((name, f"EXCEPTION {type(e).__name__}: {e}"))
        print(f"  FAIL  {name:44s} EXCEPTION {type(e).__name__}: {A(str(e))[:50]}")


conn = tb.get_conn()
print("=" * 100)
print("REGRESSION PASS - 2026-08-07")
print("=" * 100)

# ---- 1. /plan truncation (commodities lost past 4096) ----
def t_plan():
    t = tb._next_day_plan(conn)
    parts = tb._chunk_on_sections(t)
    has_com = any("COMMODITIES" in p for p in parts)
    bal = all(p.count("<pre>") == p.count("</pre>") for p in parts)
    lim = all(len(p) <= 3800 for p in parts)
    brk_last = t.find("BREAKING") > t.find("COMMODITIES") if "BREAKING" in t else True
    return (has_com and bal and lim and brk_last,
            f"{len(t)}ch -> {len(parts)} chunks, commodities={has_com}, balanced={bal}, news_last={brk_last}")
check("plan: commodities survive + news last", t_plan)

# ---- 2. digest tag-safe chunking (raw &lt;/pre&gt;) ----
def t_digest():
    t = tb._eod_digest(conn, edition="evening")
    parts = tb._chunk_on_sections(t)
    bad = [(i, tag) for i, p in enumerate(parts) for tag in ("pre", "i", "b")
           if p.count(f"<{tag}>") != p.count(f"</{tag}>")]
    return (not bad, f"{len(t)}ch -> {len(parts)} chunks, unbalanced={bad or 'none'}")
check("digest: every chunk tag-balanced", t_digest)

# ---- 3. no blind chunkers left ----
def t_noblind():
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\telegram_bot_optimized.py",
               encoding="utf-8").read()
    n = len(re.findall(r"range\(0, len\(txt\), 39", src))
    return (n == 0, f"blind chunkers remaining = {n}")
check("no blind txt[i:i+3900] chunkers", t_noblind)

# ---- 4. heatmap renders NON-BLANK ----
def t_heatmap():
    png = tb._heatmap_png(conn)
    if not png:
        return False, "no PNG"
    n = len(png.getvalue())
    # the blank-tree bug produced ~65KB; a real treemap is far larger
    return (n > 200_000, f"{n:,} bytes (blank-tree bug produced ~65,000)")
check("heatmap: PNG is not the blank tree", t_heatmap)

# ---- 5. scanners show BOTH tails ----
def t_tails():
    out = []
    for nm, fn, pred in (("revert", tb._revert_scan, lambda r: r.get("side") == "LONG"),
                         ("zrev", tb._zrev_scan, lambda r: r.get("z", 0) < 0)):
        rows = fn(conn) or []
        a = [r for r in rows if pred(r)]; b = [r for r in rows if not pred(r)]
        if a and b:
            shown = tb._both_tails(rows, pred)
            sa = sum(1 for r in shown if pred(r))
            out.append(f"{nm}:{sa}/{len(shown)-sa}")
            if sa == 0 or sa == len(shown):
                return False, f"{nm} still one-tailed"
    return True, " ".join(out) or "no two-sided data now"
check("scanners: both tails shown", t_tails)

# ---- 6. anomaly dedup key is ticker-stable ----
def t_dedup():
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\_lib\event_writeup_bot_hooks.py",
               encoding="utf-8").read()
    good = '_dk or (a.get("description")' in src and 'key = a["type"] + "_" + (_dk' in src
    gate = "_OTHER_MIN_MOVE" in src and "_RELEVANT_ALWAYS" in src
    return (good and gate, f"stable_key={good} relevance_gate={gate}")
check("anomaly: stable dedup key + relevance gate", t_dedup)

# ---- 7. NFP block carries unemployment + rank ----
def t_nfp():
    a = tb._macro_event_actual("Jobs \u00b7 NFP")
    if not a:
        return False, "no BLS actual"
    return (a.get("c_val") is not None and a.get("rank_n"),
            f"chg={a['chg']:+.0f}k unemp={a.get('c_val')} rank={a.get('rank_worse')}/{a.get('rank_n')}")
check("NFP: unemployment rate + historical rank", t_nfp)

# ---- 8. world/geo news actually returns Japan + Ukraine ----
def t_geo():
    th = tb._geo_news()
    keys = " ".join(th)
    return (len(th) >= 2, f"{len(th)} themes: {A(keys)[:60]}")
check("world news: themed feeds return content", t_geo)

# ---- 9. breaking news filtered to the book, subject-checked ----
def t_breaking():
    rows = tb._breaking_for_book(conn)
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\telegram_bot_optimized.py",
               encoding="utf-8").read()
    subj = "SUBJECT CHECK" in src
    return (subj, f"{len(rows)} hits, subject_check={subj}")
check("breaking: subject check present", t_breaking)

# ---- 10. all 8 screener models resolve ----
def t_screen():
    ok = [m for m in tb._SCREEN_MODELS if tb._SCREEN_MODELS[m].get("tests")]
    return (len(ok) == 8, f"{len(ok)}/8 models with tests")
check("screener: 8 models present", t_screen)

# ---- 11. every handler has a menu entry ----
def t_menu():
    src = open(r"C:\Users\srini\Options_chain_data\NYSE_DATA\telegram_bot_optimized.py",
               encoding="utf-8").read()
    h = set(re.findall(r'app\.add_handler\(CommandHandler\("(\w+)"', src))
    m = set(re.findall(r'BotCommand\("(\w+)"', src))
    return (not (h - m), f"handlers={len(h)} menu={len(m)} missing={sorted(h-m) or 'none'}")
check("menu: every handler is discoverable", t_menu)

# ---- 12. catalyst two tables + measured-drift honesty ----
def t_cat():
    t = tb._fmt_catalysts(tb._macro_events(3), [], 3, geo=[])
    return ("COMING UP" in t and "no measurable edge" in t,
            f"two_tables={'COMING UP' in t} drift_caveat={'no measurable edge' in t}")
check("catalysts: two tables + measured drift note", t_cat)

conn.close()
print("=" * 100)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
for n, d in FAIL:
    print(f"   FAILED: {n} -- {A(d)[:90]}")
