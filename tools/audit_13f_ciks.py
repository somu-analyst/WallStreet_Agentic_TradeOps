# -*- coding: utf-8 -*-
"""Flag 13F CIKs in the dashboard roster that have stopped filing (tracker ID 381).

The Gates row was a real EDGAR entity with the right-looking name, so it passed the
2026-07-24 name audit -- but it was a SECONDARY filer whose last 13F-HR was two years old,
so the row sat frozen while looking healthy. Name checks cannot catch that; only the
filing DATE can. This reads the roster out of dashboard.py and reports, per fund, how many
13F-HR filings exist and how recent the newest one is.
"""
import io, os, re, sys, json, time, datetime, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "NYSE_DATA research srinivas.analystsas@gmail.com"}

src = io.open(os.path.join(ROOT, "dashboard.py"), encoding="utf-8").read()
block = re.search(r"_EDGAR_FUNDS\s*=\s*\{(.*?)\n\s*\}", src, re.S)
pairs = re.findall(r'"([^"]+)"\s*:\s*"(\d{10})"', block.group(1)) if block else []
print(f"roster entries: {len(pairs)}\n")

today = datetime.date.today()
stale, dead, ok = [], [], 0
for name, cik in pairs:
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"https://data.sec.gov/submissions/CIK{cik}.json", headers=UA), timeout=25).read())
        rec = d.get("filings", {}).get("recent", {})
        forms, dates = rec.get("form", []), rec.get("filingDate", [])
        f13 = [dates[i] for i in range(len(forms)) if str(forms[i]).startswith("13F-HR")]
        if not f13:
            dead.append((name, cik, d.get("name"), "no 13F-HR on record"))
            continue
        newest = max(f13)
        age = (today - datetime.date.fromisoformat(newest)).days
        if age > 400:
            stale.append((name, cik, d.get("name"), f"{newest} ({age}d old, {len(f13)} filings)"))
        else:
            ok += 1
    except Exception as e:
        dead.append((name, cik, "?", f"{type(e).__name__}: {e}"))
    time.sleep(0.25)

print(f"CURRENT (filed within ~13 months): {ok}")
for label, rows in (("STALE - last filing over 400 days ago", stale),
                    ("NO 13F-HR / ERROR", dead)):
    print(f"\n{label}: {len(rows)}")
    for name, cik, conformed, note in rows:
        print(f"  {name:34} {cik}  [{str(conformed)[:30]}]  {note}")
