# -*- coding: utf-8 -*-
"""Fetch 13F holdings for every fund in the roster that has none (tracker ID 416).

WHY A TOOL AND NOT THE DASHBOARD FUNCTION. dashboard._edgar_build_history does this, but it
is Streamlit-coupled (caching, spinners) and importing dashboard.py to run a loader would boot
the whole app. This does the fetch and parse only; the roster is READ OUT of dashboard.py so
there is still exactly one list of CIKs and no second copy to drift.

SEC allows 10 requests/second and asks for a real User-Agent. 58 funds x ~8 filings is a few
hundred requests, so this is out-of-band work, not something to run inside a page load.
"""
import io, os, re, sys, json, time, sqlite3
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import telegram_bot_optimized as tb

UA = {"User-Agent": "NYSE_DATA research srinivas.analystsas@gmail.com"}
QUARTERS = int(os.environ.get("BF_QUARTERS", "8"))
DDL = ("CREATE TABLE IF NOT EXISTS edgar_13f (cik TEXT, fund TEXT, quarter TEXT, "
       "filing_date TEXT, cusip TEXT, issuer TEXT, shares REAL, value REAL, put_call TEXT)")


def roster(conn=None):
    """(fund, cik) pairs — the DB roster first, the code dict only as a fallback.

    investor_roster is maintained by tools/sync_13f_roster.py and can grow without a code
    edit, which is the point (ID 418). Filers marked `stale` are still fetched: a fund that
    stopped filing in 2024 still has real history worth searching, and skipping it would
    silently drop holdings we already know exist.
    """
    if conn is not None:
        try:
            rows = conn.execute(
                "SELECT fund, cik FROM investor_roster ORDER BY fund").fetchall()
            if rows:
                return [(r[0], r[1]) for r in rows]
        except Exception:
            pass
    src = io.open(os.path.join(ROOT, "dashboard.py"), encoding="utf-8").read()
    m = re.search(r"_EDGAR_FUNDS\s*=\s*\{(.*?)\n\s*\}", src, re.S)
    return [(n, c) for n, c in re.findall(r'"([^"]+)"\s*:\s*"(\d{10})"', m.group(1))] if m else []


def fetch(cik, fund, conn, have):
    d = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://data.sec.gov/submissions/CIK{cik}.json", headers=UA), timeout=30).read())
    rec = d.get("filings", {}).get("recent", {})
    rows = [(rec["accessionNumber"][i], rec["reportDate"][i], rec["filingDate"][i])
            for i, f in enumerate(rec.get("form", [])) if str(f).startswith("13F-HR")][:QUARTERS]
    stored = 0
    for acc, qtr, fdate in rows:
        if qtr in have:
            continue
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
        try:
            idx = json.loads(urllib.request.urlopen(urllib.request.Request(
                base + "/index.json", headers=UA), timeout=30).read())
        except Exception:
            continue
        names = [f["name"] for f in idx["directory"]["item"] if f["name"].endswith(".xml")]
        # The information table is the one with infoTable rows; its filename varies by filer
        # agent, so it is found by CONTENT rather than by guessing at the name.
        names.sort(key=lambda n: 0 if "infotable" in n.lower() else 1)
        for nm in names:
            try:
                x = urllib.request.urlopen(urllib.request.Request(
                    f"{base}/{nm}", headers=UA), timeout=30).read()
                root = ET.fromstring(x)
            except Exception:
                continue
            recs = []
            for it in root.iter():
                if not it.tag.endswith("infoTable"):
                    continue
                g = lambda t: next((e.text for e in it.iter() if e.tag.endswith(t)), None)
                try:
                    recs.append((cik, fund, qtr, fdate, g("cusip"), g("nameOfIssuer"),
                                 float(g("sshPrnamt") or 0), float(g("value") or 0),
                                 g("putCall") or ""))
                except Exception:
                    continue
            if recs:
                conn.execute("DELETE FROM edgar_13f WHERE cik=? AND quarter=?", (cik, qtr))
                conn.executemany("INSERT INTO edgar_13f VALUES (?,?,?,?,?,?,?,?,?)", recs)
                conn.commit()
                stored += len(recs)
                break
            time.sleep(0.12)
        time.sleep(0.12)
    return stored


def main():
    conn = tb.get_conn()
    conn.execute(DDL); conn.commit()
    done = {r[0] for r in conn.execute("SELECT DISTINCT cik FROM edgar_13f")}
    all_funds = roster(conn)
    todo = [(n, c) for n, c in all_funds if c not in done]
    print(f"roster {len(all_funds)} · already stored {len(done)} · to fetch {len(todo)}\n")
    ok = fail = 0
    for i, (fund, cik) in enumerate(todo, 1):
        have = {r[0] for r in conn.execute(
            "SELECT DISTINCT quarter FROM edgar_13f WHERE cik=?", (cik,))}
        try:
            n = fetch(cik, fund, conn, have)
            ok += 1 if n else 0
            print(f"  [{i:>2}/{len(todo)}] {fund[:38]:40} {n:>7,} holdings")
        except Exception as e:
            fail += 1
            print(f"  [{i:>2}/{len(todo)}] {fund[:38]:40} FAILED {type(e).__name__}")
        time.sleep(0.2)
    tot = conn.execute("SELECT COUNT(DISTINCT fund) FROM edgar_13f").fetchone()[0]
    print(f"\nfunds with data now: {tot} of {len(all_funds)}  (fetched {ok}, failed {fail})")
    conn.close()


if __name__ == "__main__":
    main()
