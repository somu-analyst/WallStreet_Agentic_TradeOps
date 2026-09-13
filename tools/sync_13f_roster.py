# -*- coding: utf-8 -*-
"""Keep the 13F investor roster in the DB, discovered and verified rather than typed (ID 418).

WHY THIS REPLACES A DICT IN dashboard.py. The roster was a literal in the page code, and
holdings only existed when someone ran a backfill by hand. That is exactly how 58 of 78 funds
sat empty and Peter Thiel was absent entirely while the page looked perfectly healthy. A list
that only changes when a human edits source is not a roster, it is a snapshot.

WHAT THIS DOES, and the order matters:
  1. SEED     the code dict is read as the starting set, so nothing is lost if discovery fails
  2. DISCOVER extra names resolved from EDGAR company search (tools/resolve_13f_names.py)
  3. VERIFY   every CIK is checked for its newest 13F-HR DATE -- never accepted on its name
  4. UPSERT   into investor_roster, marking anyone who has stopped filing as stale

VERIFICATION IS THE WHOLE POINT. The Gates entry in the original dict was a real EDGAR company
with precisely the right name whose last 13F was two years old, and a name audit had already
passed it. Only the date catches that, so the date is what is stored.

Re-runnable. Nothing is deleted: a filer that goes quiet is flagged `stale`, because a fund
winding down is information, not an error to erase.
"""
import io, os, re, sys, json, time, datetime, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import telegram_bot_optimized as tb

UA = {"User-Agent": "NYSE_DATA research srinivas.analystsas@gmail.com"}
TODAY = datetime.date.today()
FRESH_DAYS = 400
DDL = """CREATE TABLE IF NOT EXISTS investor_roster (
    cik         TEXT PRIMARY KEY,
    fund        TEXT NOT NULL,
    source      TEXT,
    last_13f    TEXT,
    filings_n   INTEGER,
    status      TEXT,
    checked_on  TEXT
)"""

# Names discovered from public superinvestor rosters. NAMES ONLY -- every CIK below was
# resolved and date-verified by tools/resolve_13f_names.py, not copied from anywhere.
DISCOVERED = {
    "Atlantic Investment (Roepers)": "0001063296", "Oakcliff (Lawrence)": "0001657335",
    "TCI Fund (Hohn)": "0001647251", "Semper Augustus (Bloomstran)": "0001115373",
    "CAS Investment (Sosin)": "0001697591", "Matrix Asset (Katz)": "0001016287",
    "Wedgewood (Rolfe)": "0000859804", "ShawSpring (Hong)": "0001766908",
    "H&H International (Duan)": "0001759760", "Giverny Capital (Rochon)": "0001641864",
    "Engaged Capital (Welling)": "0001559771", "Conifer (Alexander)": "0001773994",
    "Sound Shore (Burn)": "0000820124", "Durable Capital (Ellenbogen)": "0001798849",
    "Egerton Capital (Armitage)": "0001581811", "Greenlea Lane (Tarasoff)": "0001766504",
    "Lindsell Train": "0001484150", "Muhlenkamp": "0001133219",
    "Punch Card (Lou)": "0001631664", "Dorsey Asset (Pat Dorsey)": "0001671657",
    "Fairfax Financial (Watsa)": "0000915191", "Patient Capital (McLemore)": "0001854794",
    "Check Capital": "0001032814", "Makaira (Bancroft)": "0001540866",
    "Triple Frond Partners": "0001454502", "Vulcan Value Partners": "0001556785",
    "Cantillon (Von Mueffling)": "0001279936", "Causeway (Ketterer)": "0001165797",
    "Akre Capital": "0001112520", "Brave Warrior (Greenberg)": "0001553733",
    "AKO Capital": "0001376879", "Altarock Partners": "0001631014",
    "Miller Value (Bill Miller)": "0001135778", "Davis Advisors": "0001036325",
    "Kahn Brothers": "0001039565", "Tweedy Browne": "0000732905",
    "Polen Capital": "0001034524", "Valley Forge Capital": "0001697868",
    "ValueAct Capital": "0001418814", "Weitz Investment": "0000883965",
    "Greenhaven Associates": "0000846222", "Hillman Capital": "0001314620",
    "Jensen Investment": "0001106129", "Mairs & Power": "0001070134",
    "Torray": "0000098758", "Gardner Russo (Thomas Russo)": "0000860643",
}


def code_roster():
    """The dict still in dashboard.py — the seed, so discovery failing costs nothing."""
    src = io.open(os.path.join(ROOT, "dashboard.py"), encoding="utf-8").read()
    m = re.search(r"_EDGAR_FUNDS\s*=\s*\{(.*?)\n\s*\}", src, re.S)
    return dict((n, c) for n, c in re.findall(r'"([^"]+)"\s*:\s*"(\d{10})"', m.group(1))) if m else {}


def verify(cik):
    d = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://data.sec.gov/submissions/CIK{cik}.json", headers=UA), timeout=25).read())
    rec = d.get("filings", {}).get("recent", {})
    forms, dates = rec.get("form", []), rec.get("filingDate", [])
    f13 = [dates[i] for i in range(len(forms)) if str(forms[i]).startswith("13F-HR")]
    return (max(f13) if f13 else None), len(f13)


def main():
    conn = tb.get_conn()
    conn.execute(DDL); conn.commit()

    merged = {}
    for fund, cik in code_roster().items():
        merged[cik] = (fund, "code")
    added = 0
    for fund, cik in DISCOVERED.items():
        if cik not in merged:                 # dedupe by CIK, not by name
            merged[cik] = (fund, "discovered"); added += 1
    print(f"seed {len(code_roster())} · discovered new {added} · total {len(merged)}\n")

    fresh = stale = dead = 0
    for cik, (fund, source) in sorted(merged.items(), key=lambda kv: kv[1][0].lower()):
        try:
            newest, n = verify(cik)
        except Exception:
            newest, n = None, 0
        if not newest:
            status = "no-13f"; dead += 1
        else:
            age = (TODAY - datetime.date.fromisoformat(newest)).days
            status = "current" if age <= FRESH_DAYS else "stale"
            fresh += status == "current"; stale += status == "stale"
        conn.execute(
            "INSERT INTO investor_roster (cik, fund, source, last_13f, filings_n, status, "
            "checked_on) VALUES (?,?,?,?,?,?,?) ON CONFLICT(cik) DO UPDATE SET "
            "fund=excluded.fund, last_13f=excluded.last_13f, filings_n=excluded.filings_n, "
            "status=excluded.status, checked_on=excluded.checked_on",
            (cik, fund, source, newest, n, status, TODAY.isoformat()))
        time.sleep(0.15)
    conn.commit()
    print(f"current {fresh} · stale {stale} · no 13F on file {dead}")
    for r in conn.execute("SELECT fund, cik, last_13f, status FROM investor_roster "
                          "WHERE status != 'current' ORDER BY fund"):
        print(f"   {r[3]:8} {r[0][:38]:40} {r[1]}  last {r[2]}")
    conn.close()


if __name__ == "__main__":
    main()
