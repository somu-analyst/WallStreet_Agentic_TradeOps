# -*- coding: utf-8 -*-
"""13F holdings from SEC EDGAR — the shared lane for the bot and the dashboard (ID 331).

WHY THIS IS ITS OWN MODULE
    The fetch/parse/store logic used to live inside dashboard.py, which meant only a running
    Streamlit session could refresh it. "Track every quarter" needs a SCHEDULED job, and the
    bot cannot import a Streamlit script — so the lane moved here and both sides import it.
    One implementation, two callers, no duplication.

WHAT A 13F IS, AND IS NOT
    Filed 45 days after quarter end, so it is ALWAYS lagged — the August filing describes the
    June book. It covers US-listed LONG equity and options only: no shorts, no bonds, no cash,
    no foreign listings. A fund that looks "all-in on tech" may be hedged in instruments that
    never appear here. Treat it as a partial, delayed snapshot, and label it that way wherever
    it is shown.

    The quarter-over-quarter CHANGE is the signal, not the snapshot: what was bought, sold,
    added to or exited says far more than a list of positions.
"""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET

# SEC requires a descriptive UA with contact details; anonymous requests get 403.
# No Accept-Encoding: urllib does NOT decompress transparently, so advertising gzip means
# every response comes back as bytes that blow up on .decode() with a UnicodeDecodeError --
# which looks like a parsing bug and is really a transport one.
EDGAR_H = {"User-Agent": "srinivas.analystsas@gmail.com options-research",
           "Host": "www.sec.gov"}
_SUB_H = dict(EDGAR_H, Host="data.sec.gov")

DDL = ("CREATE TABLE IF NOT EXISTS edgar_13f (cik TEXT, fund TEXT, quarter TEXT, "
       "filing_date TEXT, cusip TEXT, issuer TEXT, shares REAL, value REAL, put_call TEXT, "
       "PRIMARY KEY (cik, quarter, cusip, put_call))")

# The investors tracked. CIK is the stable identifier -- fund names change, CIKs do not.
FUNDS = {
    "Berkshire Hathaway": "0001067983", "Vanguard Group": "0000102909",
    "BlackRock": "0001364742", "Citadel Advisors": "0001423053",
    "ARK Investment Management": "0001697748", "Soros Fund Management": "0001029160",
    "Bridgewater Associates": "0001350694", "Renaissance Technologies": "0001037389",
    "Pershing Square (Ackman)": "0001336528", "Scion (Burry)": "0001649339",
    "Third Point (Loeb)": "0001040273", "Tiger Global (Coleman)": "0001167483",
    "Greenlight (Einhorn)": "0001079114", "Baupost (Klarman)": "0001061768",
    "Duquesne (Druckenmiller)": "0001536411", "Appaloosa (Tepper)": "0001656456",
    "Gotham (Greenblatt)": "0001510387", "Icahn Enterprises": "0000921669",
}


def filings(cik, n=12):
    """The last n 13F-HR filings for a CIK, newest first."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    with urllib.request.urlopen(urllib.request.Request(url, headers=_SUB_H), timeout=25) as r:
        d = json.loads(r.read().decode())
    rec = d["filings"]["recent"]
    seen = {}
    for form, acc, fd, rd in zip(rec["form"], rec["accessionNumber"],
                                 rec["filingDate"], rec["reportDate"]):
        # Keep the FIRST filing seen per report date: amendments (13F-HR/A) come later and
        # a restated table should not silently replace the original unless asked for.
        if form == "13F-HR" and rd not in seen:
            seen[rd] = {"accession": acc, "filing_date": fd, "report_date": rd}
    return sorted(seen.values(), key=lambda x: x["report_date"], reverse=True)[:n]


def parse_infotable(cik, accession):
    """Every holding row in a filing's information table(s)."""
    ciki, acc = str(int(cik)), accession.replace("-", "")
    idx = f"https://www.sec.gov/Archives/edgar/data/{ciki}/{acc}/index.json"
    with urllib.request.urlopen(urllib.request.Request(idx, headers=EDGAR_H), timeout=25) as r:
        items = json.loads(r.read().decode())["directory"]["item"]
    xmls = [it["name"] for it in items if it["name"].lower().endswith(".xml")]
    cand = [n for n in xmls if n.lower() != "primary_doc.xml"]
    rows = []
    for nm in (cand or xmls):        # big filers SPLIT the table across several files
        try:
            url = f"https://www.sec.gov/Archives/edgar/data/{ciki}/{acc}/{nm}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=EDGAR_H),
                                        timeout=30) as r:
                root = ET.fromstring(r.read().decode(errors="ignore"))
            for el in root.iter():
                if el.tag.split("}")[-1] != "infoTable":
                    continue
                d = {}
                for ch in el.iter():
                    t = ch.tag.split("}")[-1]
                    if t in ("nameOfIssuer", "cusip", "value", "putCall", "sshPrnamt"):
                        d[t] = (ch.text or "").strip()
                if d.get("cusip"):
                    rows.append(d)
        except Exception:
            continue
    return rows


def build_history(conn, cik, fund, n=12, force=False, pace=0.2):
    """Fetch, parse and store up to n quarters for one fund. Returns quarters newly stored."""
    conn.execute(DDL)
    conn.commit()
    have = set() if force else {x[0] for x in conn.execute(
        "SELECT DISTINCT quarter FROM edgar_13f WHERE cik=?", (str(cik),))}
    added = 0
    for f in filings(cik, n):
        q = f["report_date"]
        if q in have:
            continue
        rows = parse_infotable(cik, f["accession"])
        time.sleep(pace)                       # SEC asks for <10 req/s; this stays far under
        # SEC switched the value column from THOUSANDS to dollars for filings from 2023.
        # Getting this wrong makes older quarters look 1000x too small and silently ruins
        # any position-size comparison across the switch.
        mult = 1 if f["filing_date"] >= "2023-01-01" else 1000
        recs = []
        for d in rows:
            try:
                val = float(d.get("value") or 0) * mult
            except (TypeError, ValueError):
                val = 0.0
            try:
                sh = float(d.get("sshPrnamt") or 0)
            except (TypeError, ValueError):
                sh = 0.0
            recs.append((str(cik), fund, q, f["filing_date"], d.get("cusip", ""),
                         d.get("nameOfIssuer", ""), sh, val, d.get("putCall", "") or ""))
        if recs:
            conn.execute("DELETE FROM edgar_13f WHERE cik=? AND quarter=?", (str(cik), q))
            conn.executemany("INSERT OR REPLACE INTO edgar_13f VALUES (?,?,?,?,?,?,?,?,?)", recs)
            conn.commit()
            added += 1
    return added


def refresh_all(conn, n=12, only=None, log=None):
    """Bring every tracked fund up to date. Returns {fund: quarters_added}."""
    out = {}
    for fund, cik in (only or FUNDS).items():
        try:
            out[fund] = build_history(conn, cik, fund, n=n)
        except Exception as e:
            out[fund] = f"ERR {type(e).__name__}"
            if log:
                log.debug("13F refresh failed for %s: %s", fund, e)
    return out


def changes(conn, fund, quarter=None):
    """What the fund DID between the two most recent quarters it has.

    Returns (quarter, prev_quarter, rows) where each row is one position with its action:
    NEW, EXIT, ADD, TRIM or HOLD. This is the part a snapshot cannot show.
    """
    qs = [r[0] for r in conn.execute(
        "SELECT DISTINCT quarter FROM edgar_13f WHERE fund=? ORDER BY quarter DESC", (fund,))]
    if len(qs) < 2:
        return (qs[0] if qs else None), None, []
    q = quarter or qs[0]
    prev = next((x for x in qs if x < q), None)
    if not prev:
        return q, None, []

    def snap(qq):
        return {r[0]: {"issuer": r[1], "shares": r[2] or 0.0, "value": r[3] or 0.0}
                for r in conn.execute(
                    "SELECT cusip, issuer, SUM(shares), SUM(value) FROM edgar_13f "
                    "WHERE fund=? AND quarter=? AND COALESCE(put_call,'')='' GROUP BY cusip",
                    (fund, qq))}

    now, was = snap(q), snap(prev)
    rows = []
    for cusip in set(now) | set(was):
        a, b = now.get(cusip), was.get(cusip)
        if a and not b:
            act, chg = "NEW", None
        elif b and not a:
            act, chg = "EXIT", -100.0
        else:
            chg = ((a["shares"] / b["shares"] - 1) * 100) if b["shares"] else None
            # A 2% wobble is share-count noise or a split artefact, not a decision.
            act = "HOLD" if chg is None or abs(chg) < 2 else ("ADD" if chg > 0 else "TRIM")
        src = a or b
        rows.append({"cusip": cusip, "issuer": src["issuer"], "action": act,
                     "shares": (a or {}).get("shares", 0.0),
                     "value": (a or {}).get("value", 0.0),
                     "prev_value": (b or {}).get("value", 0.0), "shares_chg_pct": chg})
    rows.sort(key=lambda r: -(r["value"] or r["prev_value"]))
    return q, prev, rows
