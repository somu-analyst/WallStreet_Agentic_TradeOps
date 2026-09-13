# -*- coding: utf-8 -*-
"""Find the CURRENT 13F-HR filer for a set of names (tracker ID 381).

Searches EDGAR company search restricted to form 13F-HR, then checks each candidate's
newest 13F-HR date. A name match alone is what produced the stale rows in the first place,
so nothing here is accepted on the name: the date is the test.
"""
import io, re, sys, json, time, datetime, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
UA = {"User-Agent": "NYSE_DATA research srinivas.analystsas@gmail.com"}
TODAY = datetime.date.today()

QUERIES = ["BlackRock", "Greenlight Capital", "Omega Advisors", "Invesco",
           "Markel", "JANA Partners", "Icahn"]


def candidates(q):
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
           + urllib.parse.quote(q) + "&type=13F-HR&dateb=&owner=include&count=40&output=atom")
    xml = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8", "ignore")
    # The Atom company list nests <cik> and <conformed-name> inside <company-info>; the
    # <title> attribute comes back as a literal "ARRAY(0x...)" perl artefact, so the name
    # must be read from conformed-name and never from the title.
    out = []
    for m in re.finditer(r"<company-info.*?</company-info>", xml, re.S):
        e = m.group(0)
        cik = re.search(r"<cik>(\d+)</cik>", e)
        nm = re.search(r"<conformed-name>(.*?)</conformed-name>", e, re.S)
        if cik:
            out.append((cik.group(1).zfill(10),
                        re.sub(r"\s+", " ", nm.group(1)).strip() if nm else "?"))
    if not out:
        c = re.search(r"CIK=(\d{10})", xml)
        if c:
            out.append((c.group(1).zfill(10), "?"))
    return out[:14]


def newest_13f(cik):
    d = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"https://data.sec.gov/submissions/CIK{cik}.json", headers=UA), timeout=25).read())
    rec = d.get("filings", {}).get("recent", {})
    forms, dates = rec.get("form", []), rec.get("filingDate", [])
    f13 = [dates[i] for i in range(len(forms)) if str(forms[i]).startswith("13F-HR")]
    return (d.get("name"), max(f13) if f13 else None, len(f13))


for q in QUERIES:
    print("=" * 74)
    print(f"QUERY: {q}")
    try:
        cands = candidates(q)
    except Exception as e:
        print(f"  search failed: {type(e).__name__}: {e}"); continue
    rows = []
    for cik, title in cands:
        try:
            name, newest, n = newest_13f(cik)
            if newest:
                age = (TODAY - datetime.date.fromisoformat(newest)).days
                rows.append((age, cik, name, newest, n))
        except Exception:
            pass
        time.sleep(0.25)
    for age, cik, name, newest, n in sorted(rows)[:5]:
        flag = "  <-- CURRENT" if age <= 400 else ""
        print(f"  {cik}  {str(name)[:44]:46} last 13F-HR {newest} ({age}d, {n} filings){flag}")
    if not rows:
        print("  no 13F-HR filer found")
    time.sleep(0.4)
