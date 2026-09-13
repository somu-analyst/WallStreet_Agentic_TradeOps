# -*- coding: utf-8 -*-
"""Fetch the newest cloud database snapshot to this laptop, and verify it arrived intact.

WHY THIS IS THE BACKUP THAT COUNTS
    The VM already writes a verified daily snapshot to ~/backups. That protects against a
    corrupted database, a bad migration, or a mistaken DELETE -- but it lives on the SAME DISK,
    in the SAME tenancy. It does not survive the instance being reclaimed for idleness, and it
    does not survive the account going away, which is a documented if uncommon event.

    Nine months of option-chain history cannot be re-bought at any price: CBOE serves current
    delayed quotes only, and there is no historical chain API. So the archive has to leave
    Oracle entirely. That is this script, and it is the only copy that is independent of them.

WHY IT VERIFIES RATHER THAN TRUSTS
    scp cannot resume. A transfer interrupted at 95% leaves a file that looks plausible, opens
    as gzip, and is short. The VM writes a .sha256 beside each snapshot; this compares against
    it and refuses to keep a mismatch. An unverified backup is a hopeful file.

Usage:
    python tools/pull_cloud_backup.py
    python tools/pull_cloud_backup.py --keep 6
    python tools/pull_cloud_backup.py --list          # what is on the VM, fetch nothing
"""
import hashlib
import os
import subprocess
import sys

VM = os.environ.get("NYSE_VM", "ubuntu@150.136.41.250")
KEY = os.environ.get("NYSE_VM_KEY", r"C:\Users\srini\oci-nyse.key")
REMOTE_DIR = "~/backups"
LOCAL_DIR = os.environ.get("NYSE_BACKUP_DIR", r"C:\Users\srini\Options_chain_data\cloud_backups")
SSH = ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=20"]


def _remote(cmd):
    r = subprocess.run(SSH + [VM, cmd], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"ssh failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()


def main():
    keep = int(sys.argv[sys.argv.index("--keep") + 1]) if "--keep" in sys.argv else 4

    listing = _remote(f"ls -1t {REMOTE_DIR}/db_*.db.gz 2>/dev/null | head -10")
    if not listing:
        print("no snapshots on the VM -- has cloud-backup.timer run yet?")
        return 1
    remote_files = listing.splitlines()
    if "--list" in sys.argv:
        print(_remote(f"ls -lh {REMOTE_DIR}/"))
        return 0

    newest = remote_files[0]
    name = os.path.basename(newest)
    want = _remote(f"cat {newest}.sha256 2>/dev/null").split()[0] if _remote(
        f"test -f {newest}.sha256 && echo y || echo n") == "y" else None

    os.makedirs(LOCAL_DIR, exist_ok=True)
    dest = os.path.join(LOCAL_DIR, name)
    if os.path.exists(dest) and want and _sha256(dest) == want:
        print(f"already held and verified: {name}")
    else:
        size = _remote(f"stat -c %s {newest}")
        print(f"fetching {name} ({int(size)/1e6:,.0f} MB) ...")
        r = subprocess.run(["scp", "-i", KEY, "-o", "StrictHostKeyChecking=no",
                            f"{VM}:{newest}", dest])
        if r.returncode != 0:
            print("FATAL: scp failed"); return 1
        if want:
            got = _sha256(dest)
            if got != want:
                # Delete it. A short or corrupt archive that sits in the backup folder is worse
                # than no archive, because it will be trusted on the day it is needed.
                os.remove(dest)
                print(f"FATAL: checksum mismatch -- deleted.\n  want {want}\n  got  {got}")
                return 1
            print(f"verified sha256 {got[:16]}")
        else:
            print("WARNING: no .sha256 on the VM, cannot verify this one")

    local = sorted((f for f in os.listdir(LOCAL_DIR) if f.startswith("db_") and f.endswith(".gz")),
                   reverse=True)
    for old in local[keep:]:
        os.remove(os.path.join(LOCAL_DIR, old))
        print(f"pruned {old}")

    total = sum(os.path.getsize(os.path.join(LOCAL_DIR, f)) for f in os.listdir(LOCAL_DIR))
    print(f"\n{len(local[:keep])} local copies in {LOCAL_DIR} · {total/1e9:.2f} GB")
    print("this is the ONLY copy independent of Oracle")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
