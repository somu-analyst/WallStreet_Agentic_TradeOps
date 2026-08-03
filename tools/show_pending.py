# -*- coding: utf-8 -*-
"""Print open tracker items straight from the sheet. The sheet is the source of truth --
never retype a status summary from memory (CLAUDE.md rule, 2026-08-03)."""
import openpyxl, sys, os
XL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "docs", "IDEA_TRACKER.xlsx")
ws = openpyxl.load_workbook(XL)["Ideas & Questions"]
rows = list(ws.values)
CLOSED = {"DONE", "REJECTED", "WITHDRAWN", "CLOSED"}
op = [r for r in rows[1:] if str(r[6]).upper() not in CLOSED]
order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
op.sort(key=lambda r: (order.get(str(r[10]), 9), str(r[6])))
print(f"OPEN ITEMS: {len(op)} of {len(rows)-1} tracked\n")
print(f"{'ID':>5} {'Pri':<4} {'Status':<12} Item")
print("-" * 96)
for r in op:
    print(f"{str(r[0]):>5} {str(r[10]):<4} {str(r[6]):<12} {str(r[4])[:62]}")
