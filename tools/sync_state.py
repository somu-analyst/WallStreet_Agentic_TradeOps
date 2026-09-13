# -*- coding: utf-8 -*-
"""Push the BOOK from this laptop to the cloud VM, and nothing else.

WHY THIS IS NOT A FILE COPY
    Both machines write to the same database, but to different parts of it. The laptop owns the
    user-entered state -- trades, watchlist, paper trades, settings. The VM owns the captured
    market data, and by now holds capture dates the laptop has never seen. Copying the whole
    file in either direction destroys one side's work:

        laptop -> VM   loses the VM's newer captures
        VM -> laptop   loses trades entered here since the last copy

    So this moves ONLY the tables the laptop is authoritative for, and leaves options_openbb,
    options_change, stock_daily, skew_snapshot and gex_history untouched.

WHY IT BACKS UP FIRST
    It replaces the VM's copy of each table wholesale, because a row-level merge cannot tell a
    deliberate deletion from a row that has not arrived yet. Wholesale replacement is only safe
    if the previous state is recoverable, so the VM's version is saved to a timestamped table
    before anything is written.

Usage:
    python tools/sync_state.py --dry-run     # compare both sides, change nothing
    python tools/sync_state.py               # push laptop -> VM
"""
import os
import sqlite3
import subprocess
import sys
import time

SRC = os.environ.get("NYSE_DB_PATH", r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
VM = os.environ.get("NYSE_VM", "ubuntu@150.136.41.250")
KEY = os.environ.get("NYSE_VM_KEY", r"C:\Users\srini\oci-nyse.key")
REMOTE_DB = "/home/ubuntu/US_data_OpenBB.db"
SSH = ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=25"]

# The laptop is authoritative for these. Everything else on the VM is left alone.
TABLES = ["trades", "watchlist", "paper_trades", "bookmarks", "event_journal", "app_settings"]


def sh(cmd, timeout=300):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def remote(sql):
    return sh(SSH + [VM, f'sqlite3 {REMOTE_DB} "{sql}"'])[1].strip()


def main():
    dry = "--dry-run" in sys.argv
    stamp = time.strftime("%Y%m%d_%H%M")

    print("comparing both sides")
    src = sqlite3.connect(SRC)
    diffs = []
    for t in TABLES:
        try:
            n_local = src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            print(f"  {t:<16} absent locally -- skipping"); continue
        n_vm = remote(f"SELECT COUNT(*) FROM {t};") or "?"
        mark = "" if str(n_local) == str(n_vm) else "  <-- differs"
        print(f"  {t:<16} laptop {n_local:>5}   vm {n_vm:>5}{mark}")
        diffs.append(t)

    # The book is the reason this exists, so report it specifically rather than by row count:
    # equal counts hid a real difference once (4 GOOGL positions closed here, open there).
    lo = src.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]
    vo = remote("SELECT COUNT(*) FROM trades WHERE status='OPEN';")
    print(f"\n  open positions   laptop {lo:>5}   vm {vo:>5}")
    if dry:
        print("\ndry run -- nothing written")
        return 0

    print(f"\nextracting {len(diffs)} table(s)")
    tmp = os.path.join(os.path.dirname(SRC), f"_state_{stamp}.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    out = sqlite3.connect(tmp)
    for t in diffs:
        ddl = src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                          (t,)).fetchone()[0]
        out.execute(ddl)
        rows = src.execute(f"SELECT * FROM {t}").fetchall()
        if rows:
            ph = ",".join("?" * len(rows[0]))
            out.executemany(f"INSERT INTO {t} VALUES ({ph})", rows)
    out.commit(); out.close(); src.close()
    print(f"  {os.path.getsize(tmp)/1024:.0f} KB")

    print("uploading")
    rc, o = sh(["scp", "-i", KEY, "-o", "StrictHostKeyChecking=no", tmp,
                f"{VM}:/tmp/state.db"])
    if rc != 0:
        print(f"  scp FAILED\n{o[:200]}"); return 1

    # Back up, then replace, inside ONE transaction so a failure leaves the VM untouched.
    print("applying on the VM (previous state saved first)")
    stmts = ["ATTACH '/tmp/state.db' AS s;", "BEGIN;"]
    for t in diffs:
        stmts.append(f"CREATE TABLE IF NOT EXISTS _bak_{t}_{stamp} AS SELECT * FROM {t};")
        stmts.append(f"DELETE FROM {t};")
        stmts.append(f"INSERT INTO {t} SELECT * FROM s.{t};")
    stmts += ["COMMIT;", "DETACH s;"]
    rc, o = sh(SSH + [VM, f'sqlite3 {REMOTE_DB} "{" ".join(stmts)}"'], timeout=300)
    if rc != 0 or "Error" in o:
        print(f"  FAILED -- the VM is unchanged\n{o[:400]}"); return 1

    print("\nverifying")
    ok = True
    for t in diffs:
        n_vm = remote(f"SELECT COUNT(*) FROM {t};")
        print(f"  {t:<16} vm now {n_vm}")
    vo2 = remote("SELECT COUNT(*) FROM trades WHERE status='OPEN';")
    print(f"  open positions   vm now {vo2}   (laptop {lo})")
    if str(vo2) != str(lo):
        print("  MISMATCH -- investigate before trusting this"); ok = False

    sh(SSH + [VM, "rm -f /tmp/state.db"])
    os.remove(tmp)
    print(f"\n{'done' if ok else 'done WITH A MISMATCH'} · rollback tables on the VM: "
          f"_bak_<table>_{stamp}")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
