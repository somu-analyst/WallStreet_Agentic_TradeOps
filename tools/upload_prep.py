# -*- coding: utf-8 -*-
"""Prepare the primary DB for upload to the cloud host: snapshot, compress, hash.

WHY A SCRIPT AND NOT THREE ONE-LINERS
    The equivalent `python -c` commands need nested single and double quotes (SQLite string
    literals inside a Python string inside a PowerShell argument). PowerShell 5.1 mangles the
    escaping and the command dies with an unterminated-string error before it touches the
    database. A file has no quoting problem at all.

What it does, in order:
  1. VACUUM INTO a snapshot -- consistent even if something is mid-write, and compacts.
  2. gzip it. SQLite compresses ~3-4x, which is the difference between an upload measured in
     hours and one measured in tens of minutes.
  3. SHA-256 the compressed file, so the far end can prove it arrived whole. scp cannot
     resume, so a corrupt 1.4 GB transfer that nobody checks is a very expensive silent bug.

Usage:
    python tools/upload_prep.py
    python tools/upload_prep.py --keep-plain     # don't delete the uncompressed snapshot
"""
import gzip
import hashlib
import os
import shutil
import sqlite3
import sys
import time

SRC = os.environ.get("NYSE_DB_PATH") or r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db"
SNAP = r"C:\Users\srini\db_full.db"
GZ = SNAP + ".gz"
VM = "ubuntu@150.136.41.250"
KEY = r"C:\Users\srini\oci-nyse.key"


def _mb(p):
    return os.path.getsize(p) / 1e6


def main():
    keep = "--keep-plain" in sys.argv
    if not os.path.exists(SRC):
        print(f"FATAL: source not found: {SRC}")
        return 1
    for p in (SNAP, GZ):
        if os.path.exists(p):
            print(f"FATAL: {p} already exists -- delete it first")
            return 1

    free = shutil.disk_usage(os.path.dirname(SNAP)).free / 1e9
    need = _mb(SRC) / 1000 * 1.4          # snapshot + gz, with headroom
    print(f"source {_mb(SRC):,.0f} MB · free disk {free:.1f} GB · needs ~{need:.1f} GB")
    if free < need:
        print("FATAL: not enough free disk for snapshot + archive")
        return 1

    t0 = time.time()
    print("\n[1/3] snapshot (VACUUM INTO)...")
    con = sqlite3.connect(SRC)
    con.execute("VACUUM INTO ?", (SNAP.replace("\\", "/"),))
    con.close()
    print(f"      {_mb(SNAP):,.0f} MB · {time.time()-t0:.0f}s")

    t1 = time.time()
    print("\n[2/3] compress...")
    with open(SNAP, "rb") as f, gzip.open(GZ, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g, 1024 * 1024)
    print(f"      {_mb(GZ):,.0f} MB ({100*_mb(GZ)/_mb(SNAP):.0f}% of snapshot) · {time.time()-t1:.0f}s")

    t2 = time.time()
    print("\n[3/3] sha256...")
    h = hashlib.sha256()
    with open(GZ, "rb") as f:
        for blk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blk)
    digest = h.hexdigest()
    print(f"      {digest} · {time.time()-t2:.0f}s")

    if not keep:
        os.remove(SNAP)
        print(f"\nremoved uncompressed snapshot (--keep-plain to retain)")

    print(f"\ntotal {time.time()-t0:.0f}s\n" + "=" * 78)
    print("UPLOAD:")
    print(f"  scp -i {KEY} {GZ} {VM}:~/")
    print("\nTHEN ON THE VM -- the hash must match exactly:")
    print(f"  sha256sum ~/db_full.db.gz")
    print(f"  # expect: {digest}")
    print("  gunzip -c ~/db_full.db.gz > ~/US_data_OpenBB.db && rm ~/db_full.db.gz")
    print("  sqlite3 ~/US_data_OpenBB.db \"PRAGMA integrity_check;\"")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
