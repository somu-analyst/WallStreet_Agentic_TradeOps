# -*- coding: utf-8 -*-
"""Resolve investor NAMES to verified 13F filer CIKs (tracker ID 417).

Names are cheap to collect and worthless on their own. The Gates row in this roster pointed at
a real EDGAR entity with exactly the right name whose last 13F-HR was two years old, and the
2026-07-24 audit that checked names had passed it. So nothing here is accepted on a name: each
candidate is looked up, its newest 13F-HR date read, and only a filer that is CURRENT is
proposed.

Prints a ready-to-paste dict line per resolved name, and says plainly which names could not be
resolved rather than guessing at them.
"""
import io, os, re, sys, json, time, datetime, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
UA = {"User-Agent": "NYSE_DATA research srinivas.analystsas@gmail.com"}
TODAY = datetime.date.today()
FRESH_DAYS = 400        # one missed quarter is tolerable; a year of silence is not

# "display name" -> search term actually used against EDGAR company search. The firm is a far
# better search key than the person: EDGAR indexes the FILER, and "Mohnish Pabrai" is not an
# entity while "Pabrai Investments" is.
TARGETS = [
    ("Atlantic Investment (Roepers)", "Atlantic Investment Management"),
    ("Oakmark (Nygren)", "Harris Associates"),
    ("Oakcliff (Lawrence)", "Oakcliff Capital"),
    ("TCI Fund (Hohn)", "TCI Fund Management"),
    ("Semper Augustus (Bloomstran)", "Semper Augustus"),
    ("CAS Investment (Sosin)", "CAS Investment Partners"),
    ("Matrix Asset (Katz)", "Matrix Asset Advisors"),
    ("Wedgewood (Rolfe)", "Wedgewood Partners"),
    ("ShawSpring (Hong)", "ShawSpring Partners"),
    ("H&H International (Duan)", "H&H International Investment"),
    ("Chou Associates", "Chou America"),
    ("Giverny Capital (Rochon)", "Giverny Capital"),
    ("Engaged Capital (Welling)", "Engaged Capital"),
    ("Conifer (Alexander)", "Conifer Management"),
    ("Aquamarine (Spier)", "Aquamarine Capital"),
    ("Sound Shore (Burn)", "Sound Shore Management"),
    ("Durable Capital (Ellenbogen)", "Durable Capital Partners"),
    ("Egerton Capital (Armitage)", "Egerton Capital"),
    ("Greenlea Lane (Tarasoff)", "Greenlea Lane Capital"),
    ("Lindsell Train", "Lindsell Train"),
    ("Pabrai Investments", "Pabrai Investments"),
    ("Muhlenkamp", "Muhlenkamp"),
    ("Punch Card (Lou)", "Punch Card Management"),
    ("Dorsey Asset (Pat Dorsey)", "Dorsey Asset Management"),
    ("Fairfax Financial (Watsa)", "Fairfax Financial Holdings"),
    ("Ruane Cunniff", "Ruane Cunniff"),
    ("Patient Capital (McLemore)", "Patient Capital Management"),
    ("Check Capital", "Check Capital Management"),
    ("Makaira (Bancroft)", "Makaira Partners"),
    ("Triple Frond Partners", "Triple Frond"),
    ("Vulcan Value Partners", "Vulcan Value Partners"),
    ("Cantillon (Von Mueffling)", "Cantillon Capital"),
    ("Causeway (Ketterer)", "Causeway Capital"),
    ("Akre Capital", "Akre Capital Management"),
    ("Brave Warrior (Greenberg)", "Brave Warrior"),
    ("AKO Capital", "AKO Capital"),
    ("Altarock Partners", "Altarock Partners"),
    ("Century Management (Van Den Berg)", "Century Management"),
    ("Miller Value (Bill Miller)", "Miller Value Partners"),
    ("Davis Advisors", "Davis Selected Advisers"),
    ("Kahn Brothers", "Kahn Brothers"),
    ("Tweedy Browne", "Tweedy Browne"),
    ("Polen Capital", "Polen Capital Management"),
    ("Valley Forge Capital", "Valley Forge Capital"),
    ("ValueAct Capital", "ValueAct"),
    ("Weitz Investment", "Weitz Investment Management"),
    ("Greenhaven Associates", "Greenhaven Associates"),
    ("Hillman Capital", "Hillman Capital"),
    ("Jensen Investment", "Jensen Investment Management"),
    ("Mairs & Power", "Mairs & Power"),
    ("Torray", "Torray"),
    ("Gardner Russo (Thomas Russo)", "Gardner Russo"),
]


def candidates(q):
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
           + urllib.parse.quote(q) + "&type=13F-HR&dateb=&owner=include&count=40&output=atom")
    xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")
    out = []
    for m in re.finditer(r"<company-info.*?</company-info>", xml, re.S):
        e = m.group(0)
        c = re.search(r"<cik>(\d+)</cik>", e)
        n = re.search(r"<conformed-name>(.*?)</conformed-name>", e, re.S)
        if c:
            out.append((c.group(1).zfill(10), (n.group(1).strip() if n else "?")))
    if not out:
        c = re.search(r"CIK=(\d{10})", xml)
        if c:
            out.append((c.group(1), "?"))
    return out[:10]


def newest_13f(cik):
    d = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://data.sec.gov/submissions/CIK{cik}.json", headers=UA), timeout=25).read())
    rec = d.get("filings", {}).get("recent", {})
    forms, dates = rec.get("form", []), rec.get("filingDate", [])
    f13 = [dates[i] for i in range(len(forms)) if str(forms[i]).startswith("13F-HR")]
    return d.get("name"), (max(f13) if f13 else None), len(f13)


def main():
    found, missed = [], []
    for label, query in TARGETS:
        best = None
        try:
            for cik, _t in candidates(query):
                try:
                    name, newest, n = newest_13f(cik)
                except Exception:
                    continue
                if not newest:
                    continue
                age = (TODAY - datetime.date.fromisoformat(newest)).days
                if age <= FRESH_DAYS and (best is None or age < best[0]):
                    best = (age, cik, name, newest, n)
                time.sleep(0.2)
        except Exception as e:
            print(f"  {label:36} search failed: {type(e).__name__}")
            missed.append(label); continue
        if best:
            age, cik, name, newest, n = best
            print(f'  "{label}": "{cik}",   # {str(name)[:38]} · {newest} · {n} filings')
            found.append((label, cik))
        else:
            print(f"  {label:36} NO CURRENT 13F FILER FOUND")
            missed.append(label)
        time.sleep(0.3)
    print(f"\nresolved {len(found)} · unresolved {len(missed)}")
    if missed:
        print("unresolved (left out rather than guessed): " + ", ".join(missed))


if __name__ == "__main__":
    main()
