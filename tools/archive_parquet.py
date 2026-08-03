# -*- coding: utf-8 -*-
"""Parquet archival for the options tables (tracker ID 29).

The primary DB is ~2.9 GB and grows every capture day. Parquet stores the same rows far
denser and is still directly queryable, so cold history can live outside SQLite.

SAFETY: this script NEVER deletes anything. It exports, then re-reads what it wrote and
compares row count, column set and a per-column checksum against the source. Deletion is a
separate, explicit decision, and `--verify-only` exists to re-check an archive at any time.
A day is only ever reported as safe to prune once its readback has passed.

    python tools/archive_parquet.py --table options_openbb --before 2026-07-15
    python tools/archive_parquet.py --verify-only
"""
from __future__ import annotations

import argparse, hashlib, json, os, sqlite3, sys, time
import pandas as pd

DB = os.environ.get("NYSE_DB_PATH", r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
ARCHIVE = os.environ.get("NYSE_ARCHIVE_DIR",
                         r"C:\Users\srini\Options_chain_data\archive_parquet")
MANIFEST = os.path.join(ARCHIVE, "manifest.json")


def _fingerprint(df: pd.DataFrame) -> dict:
    """Order-independent content fingerprint: row count + per-column checksum.

    Parquet round-trips can reorder rows, so a naive frame equality check produces false
    alarms. Sorting each column independently compares CONTENT, which is what matters here.
    """
    out = {"rows": int(len(df)), "cols": sorted(map(str, df.columns))}
    h = {}
    for c in df.columns:
        s = df[c]
        try:
            v = pd.to_numeric(s, errors="raise").fillna(0).round(6).sort_values().to_numpy()
            h[str(c)] = hashlib.md5(v.tobytes()).hexdigest()[:16]
        except Exception:
            v = s.astype(str).fillna("").sort_values().str.cat(sep="\x1f")
            h[str(c)] = hashlib.md5(v.encode("utf-8", "replace")).hexdigest()[:16]
    out["col_hash"] = h
    return out


def _load_manifest() -> dict:
    if os.path.exists(MANIFEST):
        try:
            with open(MANIFEST, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_manifest(m: dict) -> None:
    os.makedirs(ARCHIVE, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, sort_keys=True)


def export_day(conn, table: str, day: str, man: dict, compression: str = "zstd") -> dict:
    src = pd.read_sql(f"SELECT * FROM {table} WHERE trade_date=?", conn, params=(day,))
    if src.empty:
        return {"day": day, "status": "EMPTY", "rows": 0}
    d = os.path.join(ARCHIVE, table)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{table}_{day}.parquet")
    t0 = time.time()
    try:
        src.to_parquet(path, compression=compression, index=False)
    except Exception as e:                       # zstd needs a recent pyarrow
        src.to_parquet(path, compression="snappy", index=False)
        compression = "snappy"

    # ---- readback verification: the whole point of this script ----
    back = pd.read_parquet(path)
    fs, fb = _fingerprint(src), _fingerprint(back)
    ok = (fs["rows"] == fb["rows"] and fs["cols"] == fb["cols"]
          and fs["col_hash"] == fb["col_hash"])
    bad = [c for c in fs["col_hash"] if fs["col_hash"].get(c) != fb["col_hash"].get(c)]
    rec = {"day": day, "table": table, "rows": fs["rows"],
           "db_bytes": int(src.memory_usage(deep=True).sum()),
           "parquet_bytes": os.path.getsize(path),
           "compression": compression, "seconds": round(time.time() - t0, 2),
           "verified": bool(ok), "mismatched_cols": bad,
           "status": "VERIFIED" if ok else "MISMATCH",
           "safe_to_prune": bool(ok), "path": path,
           "checked": time.strftime("%Y-%m-%d %H:%M:%S")}
    man.setdefault(table, {})[day] = rec
    return rec


def verify_only(man: dict) -> None:
    conn = sqlite3.connect(DB, timeout=30)
    print(f"{'table':16s} {'day':12s} {'rows':>8s} {'status':>10s}")
    for table, days in man.items():
        for day, rec in sorted(days.items()):
            if not os.path.exists(rec["path"]):
                print(f"{table:16s} {day:12s} {'-':>8s} {'FILE GONE':>10s}"); continue
            src = pd.read_sql(f"SELECT * FROM {table} WHERE trade_date=?", conn, params=(day,))
            back = pd.read_parquet(rec["path"])
            ok = _fingerprint(src) == _fingerprint(back) if len(src) else None
            st = "SOURCE GONE" if not len(src) else ("VERIFIED" if ok else "MISMATCH")
            print(f"{table:16s} {day:12s} {len(back):>8,d} {st:>10s}")
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="options_openbb")
    ap.add_argument("--before", help="archive trade_date < this ISO date")
    ap.add_argument("--limit", type=int, default=0, help="cap days processed (0 = all)")
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()

    man = _load_manifest()
    if a.verify_only:
        verify_only(man); return

    conn = sqlite3.connect(DB, timeout=30)
    q = f"SELECT DISTINCT trade_date FROM {a.table}"
    p = ()
    if a.before:
        q += " WHERE trade_date < ?"; p = (a.before,)
    days = [r[0] for r in conn.execute(q + " ORDER BY trade_date", p)]
    done = set(man.get(a.table, {}))
    days = [d for d in days if d not in done]
    if a.limit:
        days = days[:a.limit]
    if not days:
        print("nothing to archive (all matching days already in the manifest)"); conn.close(); return

    print(f"archiving {len(days)} day(s) of {a.table}  ->  {ARCHIVE}")
    print(f"  {'day':12s} {'rows':>9s} {'sqlite MB':>10s} {'parquet MB':>11s} {'ratio':>7s} {'status':>9s}")
    tot_s = tot_p = 0
    for d in days:
        r = export_day(conn, a.table, d, man)
        if r["status"] == "EMPTY":
            print(f"  {d:12s} {'0':>9s} {'':>10s} {'':>11s} {'':>7s} {'EMPTY':>9s}"); continue
        tot_s += r["db_bytes"]; tot_p += r["parquet_bytes"]
        print(f"  {d:12s} {r['rows']:>9,d} {r['db_bytes']/1e6:>10.1f} "
              f"{r['parquet_bytes']/1e6:>11.2f} {r['db_bytes']/max(r['parquet_bytes'],1):>6.1f}x "
              f"{r['status']:>9s}")
        _save_manifest(man)                      # checkpoint after every day
    conn.close()
    _save_manifest(man)
    if tot_p:
        print(f"\n  total: {tot_s/1e6:.1f} MB in memory -> {tot_p/1e6:.1f} MB parquet "
              f"({tot_s/tot_p:.1f}x denser)")
    v = sum(1 for t in man.values() for r in t.values() if r.get("verified"))
    n = sum(len(t) for t in man.values())
    print(f"  manifest: {v}/{n} archived days pass readback verification")
    print("  NOTHING WAS DELETED. Prune only days marked safe_to_prune, as a separate step.")


if __name__ == "__main__":
    sys.exit(main())
