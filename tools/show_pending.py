# -*- coding: utf-8 -*-
"""Print the tracker queue straight from the sheet. The sheet is the source of truth --
never retype a status summary from memory (CLAUDE.md rule, 2026-08-03).

WHY THIS IS BUCKETED (2026-08-19, ID 268)
    It used to print everything that was not DONE as "OPEN", which on 2026-08-19 read
    "OPEN ITEMS: 18" when only five were work and thirteen were ANSWERED questions. That
    makes the list useless as a queue in exactly the situation it exists for: deciding what
    to do next. A question that has been answered is not pending work; it is history that
    happens not to be marked DONE.

    Three buckets now:
      ACTIONABLE  OPEN / IN PROGRESS / QUEUED      -> work you can pick up right now
      WAITING     NEEDS INFO / BLOCKED / DEFERRED  -> real, but not on us
      RESOLVED    ANSWERED / SUPERSEDED            -> collapsed to a count; --all to list

Usage:  python tools/show_pending.py [--all]
"""
import os
import sys

import openpyxl

XL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "docs", "IDEA_TRACKER.xlsx")

CLOSED = {"DONE", "REJECTED", "WITHDRAWN", "CLOSED"}
WAITING = {"NEEDS INFO", "BLOCKED", "DEFERRED", "ON HOLD"}
RESOLVED = {"ANSWERED", "SUPERSEDED"}
PRI = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _bucket(status):
    s = str(status or "").upper().strip()
    if s in CLOSED:
        return None
    if s in WAITING:
        return "WAITING"
    if s in RESOLVED:
        return "RESOLVED"
    return "ACTIONABLE"


def main(show_all=False, sheet="Ideas & Questions"):
    ws = openpyxl.load_workbook(XL)[sheet]
    rows = list(ws.values)[1:]
    buckets = {"ACTIONABLE": [], "WAITING": [], "RESOLVED": []}
    for r in rows:
        b = _bucket(r[6])
        if b:
            buckets[b].append(r)
    for v in buckets.values():
        v.sort(key=lambda r: (PRI.get(str(r[10]), 9), str(r[6])))

    def _dump(title, items, note=""):
        print(f"\n{title}: {len(items)}{note}")
        if not items:
            return
        print("-" * 96)
        for r in items:
            print(f"{str(r[0]):>5} {str(r[10]):<4} {str(r[6]):<12} {str(r[4])[:60]}")

    n_act = len(buckets["ACTIONABLE"])
    print(f"TRACKER: {len(rows)} rows · {n_act} actionable · "
          f"{len(buckets['WAITING'])} waiting · {len(buckets['RESOLVED'])} answered")
    _dump("ACTIONABLE NOW", buckets["ACTIONABLE"])
    _dump("WAITING (not on us)", buckets["WAITING"])
    if show_all:
        _dump("ANSWERED / SUPERSEDED", buckets["RESOLVED"])
    else:
        print(f"\nANSWERED / SUPERSEDED: {len(buckets['RESOLVED'])}  (--all to list)")
    if not n_act:
        print("\nNothing actionable. Do not invent work -- check WAITING above for what "
              "needs a decision from the user.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # --cloud reads the Oracle/hosting queue, which is a SEPARATE sheet on purpose (user
    # 2026-08-27): cloud items were diluting the main queue and their IDs are their own series.
    main("--all" in sys.argv,
         "Cloud Migration" if "--cloud" in sys.argv else "Ideas & Questions")
