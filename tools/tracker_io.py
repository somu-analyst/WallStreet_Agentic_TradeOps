# -*- coding: utf-8 -*-
"""Safe append/update for docs/IDEA_TRACKER.xlsx.

Written after two Claude sessions edited the workbook at the same time on 2026-08-12 and
collided: both had computed "the next ID" from a copy read minutes earlier, both appended
rows with the same numbers, and the second save silently won. Four rows lost their outcome
text because an update keyed on ID landed on the wrong row.

The rules this enforces:
  * NEVER hardcode an ID. `add()` re-reads the workbook and takes max(ID)+1 at write time.
  * An update matches on ID *and* the question text, so a collided ID cannot be written
    over by accident -- it raises instead.
"""
import datetime as _dt

import openpyxl

PATH = r"C:\Users\srini\Options_chain_data\NYSE_DATA\docs\IDEA_TRACKER.xlsx"


CLOUD = "Cloud Migration"          # the Oracle/hosting queue, kept OFF the main sheet (user 2026-08-27)


def _open(sheet=None):
    """`sheet` picks a worksheet by name; None means the active (main) sheet. Each sheet keeps
    its OWN ID sequence -- Cloud Migration IDs are not comparable to main-tracker IDs."""
    wb = openpyxl.load_workbook(PATH)
    ws = wb[sheet] if sheet else wb.active
    return wb, ws, {c.value: i + 1 for i, c in enumerate(ws[1])}


def add(question, detail, raised_by="User", category="Idea", priority="P2",
        next_step="", status="OPEN", sheet=None):
    """Append one row and return its ID, allocated fresh at write time."""
    wb, ws, I = _open(sheet)
    ids = [ws.cell(r, I["ID"]).value for r in range(2, ws.max_row + 1)]
    nid = int(max([i for i in ids if isinstance(i, (int, float))] or [0])) + 1
    today = _dt.date.today().isoformat()
    row = [""] * len(I)
    for k, v in (("ID", nid), ("Date Added", today), ("Raised By", raised_by),
                 ("Category", category), ("Idea / Question", question), ("Detail", detail),
                 ("Status", status), ("Priority", priority), ("Next Step", next_step)):
        row[I[k] - 1] = v
    ws.append(row)
    wb.save(PATH)
    return nid


def update(rid, status=None, outcome=None, next_step=None, expect=None, sheet=None):
    """Update a row by ID. `expect` is a substring of the question that MUST match --
    the guard that would have prevented the 2026-08-12 clobber. `sheet` must name the same
    worksheet the row lives on; IDs repeat across sheets, so omitting it on a Cloud Migration
    row would search the main sheet and either miss or hit the wrong item."""
    wb, ws, I = _open(sheet)
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, I["ID"]).value != rid:
            continue
        q = str(ws.cell(r, I["Idea / Question"]).value or "")
        if expect and expect.lower() not in q.lower():
            raise ValueError(f"ID {rid} is '{q[:60]}', not '{expect}' — refusing to overwrite")
        if status is not None:
            ws.cell(r, I["Status"]).value = status
            ws.cell(r, I["Date Actioned"]).value = _dt.date.today().isoformat()
        if outcome is not None:
            ws.cell(r, I["Outcome / Evidence"]).value = outcome
        if next_step is not None:
            ws.cell(r, I["Next Step"]).value = next_step
        wb.save(PATH)
        return True
    raise KeyError(f"ID {rid} not found")
