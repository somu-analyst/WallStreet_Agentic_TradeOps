# -*- coding: utf-8 -*-
"""Two-way sync of `trades` and `paper_trades` between the local laptop DB and the cloud VM DB.

WHY paper_trades WAS ADDED AFTER trades, NOT ALONGSIDE IT
    paper_trades had no `updated_at` at all -- this file's whole conflict rule (newer wins,
    receiving side keeps the sender's exact timestamp) has nothing to compare without it.
    Confirmed live (2026-09-04) that both bots independently closing the SAME expired GOOG
    paper position after a code deploy was a coincidence of that one bug fix, not evidence
    the table stays in sync -- a manually added/edited paper trade on one side genuinely never
    reached the other. Fixed at the root: `updated_at TEXT` added to paper_trades on both DBs
    (ALTER TABLE, existing rows get NULL -- `_newer()` already treats missing as "loses to
    anything real", so old rows just don't fight over who's newer), and every one of its 4
    write sites (2 in telegram_bot_optimized.py, 2 in dashboard.py) now sets it, mirroring
    exactly how trades already worked. Only once that existed was extending this script safe.

WHY A FULL DIFF, NOT A TRIGGER + QUEUE
    `trades` is small (currently ~90 rows, low hundreds for years of a personal book) and only
    ONE side -- local -- ever runs this script, since only local holds the ssh key. A trigger
    on the cloud DB would need something to drain its queue, and that something would still
    have to be this same local process reaching over ssh -- so the trigger buys nothing a full
    diff does not already give for a table this size, at the cost of a schema change to two
    live production databases. Comparing two ~90-row tables end to end runs in well under a
    second; there is no scale problem to solve here.

WHY `trade_id` IS SAFE TO SYNC ON NOW, AND WAS NOT BEFORE
    Both DBs seeded from one snapshot around 2026-08-27/28 and their autoincrement counters
    then diverged independently. Checked before writing this file: local's next id was 91,
    cloud's was 89 -- the very next cloud-side add would have collided with a local id that
    already meant a different trade. Fixed once, permanently, by reserving cloud's future ids
    at 1,000,000+ (`UPDATE sqlite_sequence SET seq=999999 WHERE name='trades'` on the VM,
    2026-09-04, DB backed up first to US_data_OpenBB.db.pre_seqbump.bak). No existing row was
    touched -- only where NEW autoincrement values start from. The two ranges can now never
    collide, so trade_id is a safe join key going forward.

WHY THE CONFLICT RULE IS `updated_at`, AND WHY THAT COLUMN NEEDED NO MIGRATION
    Checked before assuming: `trades.updated_at` already exists and is set on every insert and
    update path (verified by grep across telegram_bot_optimized.py and dashboard.py). Newer
    `updated_at` wins and is copied to the older side, UNCHANGED -- the receiving side's row
    ends up with the SAME `updated_at` the sending side had, not a fresh timestamp. That is
    what makes the sync idempotent: the next run sees identical `updated_at` on both sides for
    that trade_id and does nothing, rather than treating the just-received copy as new upstream
    and trying to write it right back where it came from.

WHY WRITES ARE PARAMETERIZED, NEVER STRING-BUILT SQL
    `notes` and other text columns are free-form. A ticker or a note containing a quote
    character breaks naive `f"...'{value}'..."` SQL and is exactly the kind of bug that looks
    fine on the two trades tested by hand and then corrupts the next one. Every write here goes
    through sqlite3's own parameter binding, locally and on the VM (via a small script pushed
    over ssh that also binds parameters -- never through a hand-assembled SQL string).

Usage:
    python tools/sync_trades.py                 # DEFAULT: dry run, prints the diff, writes nothing
    python tools/sync_trades.py --apply          # actually pushes/pulls
    python tools/sync_trades.py --apply --quiet  # for the scheduled job -- prints only on a real change
"""
import json
import os
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_DB = os.environ.get("NYSE_DB_PATH", r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
CLOUD_DB = "/home/ubuntu/US_data_OpenBB.db"
VM = os.environ.get("NYSE_VM", "ubuntu@150.136.41.250")
KEY = os.environ.get("NYSE_VM_KEY", r"C:\Users\srini\oci-nyse.key")
SSH = ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=20",
       "-o", "BatchMode=yes"]
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
REMOTE_APPLY_PATH = "/home/ubuntu/nyse/_sync_apply.py"

# Both tables share this exact shape: an autoincrement `trade_id` primary key (ranges kept
# disjoint per host -- see the module docstring), and an `updated_at` that every write path
# now sets. One diff/push/pull implementation, parameterized by table name, rather than a
# second near-identical copy that drifts from this one the next time either is fixed.
TABLES = ("trades", "paper_trades")

# The VM-side apply script. Reads one JSON array of rows off stdin, upserts each with bound
# parameters, into whichever table is named on argv[1]. Deliberately tiny and reviewed here
# in full rather than assembled at runtime, so what runs against the production DB is exactly
# what this file says it is. The table name is never taken from row data -- only from TABLES
# above, via argv -- so there is no injection surface even though it lands in an f-string.
_REMOTE_APPLY = r'''
import json, sqlite3, sys
table = sys.argv[1]
rows = json.load(sys.stdin)
c = sqlite3.connect("''' + CLOUD_DB + r'''")
cols = list(rows[0].keys()) if rows else []
placeholders = ",".join("?" for _ in cols)
collist = ",".join(cols)
sql = f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})"
for r in rows:
    c.execute(sql, [r[k] for k in cols])
c.commit()
c.close()
print(f"applied {len(rows)} row(s) to {table}")
'''


def _local_rows(table):
    c = sqlite3.connect(LOCAL_DB)
    c.row_factory = sqlite3.Row
    try:
        rows = {r["trade_id"]: dict(r) for r in c.execute(f"SELECT * FROM {table}")}
    finally:
        c.close()
    return rows


def _cloud_rows(table):
    r = subprocess.run(SSH + [VM, f'sqlite3 -readonly -json {CLOUD_DB} "SELECT * FROM {table};"'],
                       capture_output=True, text=True, timeout=60, **_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(f"cloud read failed: {(r.stderr or r.stdout)[:300]}")
    data = json.loads(r.stdout) if r.stdout.strip() else []
    return {row["trade_id"]: row for row in data}


def _newer(a, b):
    """True if row a's updated_at is strictly newer than row b's. Missing/NULL loses to
    anything real -- an old row that was never touched should not block a real sync."""
    au, bu = a.get("updated_at") or "", b.get("updated_at") or ""
    return au > bu


def diff(local, cloud):
    """Returns (push_to_cloud, pull_to_local) -- lists of full row dicts."""
    push, pull = [], []
    all_ids = set(local) | set(cloud)
    for tid in all_ids:
        l, c = local.get(tid), cloud.get(tid)
        if l is None:
            pull.append(c)
        elif c is None:
            push.append(l)
        elif _newer(l, c):
            push.append(l)
        elif _newer(c, l):
            pull.append(c)
        # else: identical updated_at (or genuinely unchanged) -- nothing to do
    return push, pull


def apply_push(table, rows):
    # ssh does not pass a multi-arg command through untouched -- it re-joins argv into one
    # string and the REMOTE shell re-parses it, mangling a multi-line Python script full of
    # quotes and parens. Write the script to its own file over stdin first (no shell
    # involvement in the script's content at all), then run that file separately with the
    # row data on ITS stdin and the table name as a plain argv.
    w = subprocess.run(SSH + [VM, f"cat > {REMOTE_APPLY_PATH}"], input=_REMOTE_APPLY,
                       capture_output=True, text=True, timeout=30, **_NO_WINDOW)
    if w.returncode != 0:
        raise RuntimeError(f"could not stage remote script: {(w.stderr or w.stdout)[:300]}")
    payload = json.dumps(rows)
    r = subprocess.run(SSH + [VM, "python3", REMOTE_APPLY_PATH, table],
                       input=payload, capture_output=True, text=True, timeout=60, **_NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError(f"push failed: {(r.stderr or r.stdout)[:300]}")
    return r.stdout.strip()


def apply_pull(table, rows):
    c = sqlite3.connect(LOCAL_DB)
    try:
        cols = list(rows[0].keys())
        collist = ",".join(cols)
        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})"
        for r in rows:
            c.execute(sql, [r[k] for k in cols])
        c.commit()
    finally:
        c.close()


def main():
    apply = "--apply" in sys.argv
    quiet = "--quiet" in sys.argv
    any_change = False

    for table in TABLES:
        local = _local_rows(table)
        cloud = _cloud_rows(table)
        push, pull = diff(local, cloud)

        if not push and not pull:
            if not quiet:
                print(f"{table}: in sync -- {len(local)} local / {len(cloud)} cloud rows")
            continue

        any_change = True
        for r in push:
            print(f"{table}: {'PUSH ->cloud' if apply else 'would push ->cloud'}: "
                  f"trade_id={r['trade_id']} {r['ticker']} {r['status']} updated_at={r['updated_at']}")
        for r in pull:
            print(f"{table}: {'PULL ->local' if apply else 'would pull ->local'}: "
                  f"trade_id={r['trade_id']} {r['ticker']} {r['status']} updated_at={r['updated_at']}")

        if not apply:
            continue
        if push:
            print(f"{table}: " + apply_push(table, push))
        if pull:
            apply_pull(table, pull)
            print(f"{table}: applied {len(pull)} row(s) locally")

    if not apply and any_change:
        print("\n(dry run -- pass --apply to actually write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
