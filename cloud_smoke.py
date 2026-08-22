# -*- coding: utf-8 -*-
"""Cloud-readiness smoke test — run BEFORE committing to any migration (ID 306/307).

WHAT THIS IS FOR
    Answers "can this system run somewhere that is not this laptop?" by exercising the exact
    configuration a cloud host would use, and reporting a per-gate verdict. Run it here
    first to prove the CODE is portable, then run the same file on the VM to prove the
    NETWORK is too. Same script, two environments, directly comparable output.

WHAT IT CANNOT TELL YOU FROM THIS MACHINE
    IP reputation. This box has a residential IP; a cloud host does not. Gate C (the option
    chain capture) is the one that decides the whole migration, and it can only be answered
    on the VM. That is stated in the output rather than glossed over.

Usage:
    python cloud_smoke.py              # full run
    python cloud_smoke.py --quick      # skip the slow chain capture
"""
import argparse
import os
import sqlite3
import sys
import time
import traceback

RESULTS = []


def gate(name, critical=True):
    """Decorator: run a check, capture PASS/FAIL/SKIP plus a one-line reason."""
    def deco(fn):
        def wrapped(*a, **kw):
            t0 = time.time()
            try:
                ok, detail = fn(*a, **kw)
                state = "PASS" if ok else ("FAIL" if critical else "WARN")
            except Exception as e:
                state, detail = ("FAIL" if critical else "WARN"), f"{type(e).__name__}: {e}"
                if os.environ.get("SMOKE_TRACE"):
                    traceback.print_exc()
            RESULTS.append((name, state, detail, time.time() - t0))
            print(f"  [{state:<4}] {name:<38} {detail[:88]}")
            return state == "PASS"
        return wrapped
    return deco


@gate("A. Portable secrets (KEYVAULT_PASSPHRASE)")
def gate_a():
    """The vault key is derived from user|hostname, so it will NOT decrypt on a new host
    unless KEYVAULT_PASSPHRASE is set. This proves the override path works."""
    import telegram_bot_optimized as B
    have = {k: bool(os.environ.get(k)) for k in
            ("ANTHROPIC_API_KEY", "FINNHUB_API_KEY", "GROQ_API_KEY")}
    live = [k for k, v in have.items() if v]
    if not live:
        return False, "vault decrypted no keys — set KEYVAULT_PASSPHRASE before migrating"
    override = "set" if os.environ.get("KEYVAULT_PASSPHRASE") else "NOT set (machine-bound)"
    return True, f"{len(live)} keys loaded ({', '.join(live)}) · passphrase {override}"


@gate("B. Price lane without yfinance (Finnhub)")
def gate_b():
    """The lane that replaces yfinance, which Yahoo blocks from datacenter IPs."""
    import NYSE_OpenBB as N
    sample = ["AAPL", "MSFT", "SPY", "NVDA", "TGT"]
    t0 = time.time()
    px = N._finnhub_eod(sample)
    if not px:
        return False, "no quotes — FINNHUB_API_KEY missing or rejected"
    dt = time.time() - t0
    rate = 730 * (dt / max(len(px), 1)) / 60
    return len(px) == len(sample), (
        f"{len(px)}/{len(sample)} quotes in {dt:.1f}s → ~{rate:.0f} min for 730 "
        f"(free cap 60/min ⇒ floor ~12 min)")


@gate("C. OPTION CHAIN capture  ← decides everything", critical=True)
def gate_c(limit=3):
    """THE deciding gate. Everything downstream is empty without options_openbb, and this is
    the lane most likely to be blocked from a datacenter range."""
    import NYSE_OpenBB as N
    from datetime import datetime
    # Test _fetch_chain_cdn: it is the path the capture actually falls back to (line 528),
    # takes (ticker, trade_dt) with no obb client, and hits CBOE's public CDN directly with a
    # browser-impersonated fingerprint. That CDN request is precisely what a datacenter IP
    # would get blocked on, so it is the right thing to probe.
    #
    # An earlier version of this gate called fetch_chain_openbb(ticker, dt) -- that function
    # takes FOUR args (obb, ticker, provider, trade_dt), so every call threw and the gate
    # reported 0/3 on a machine where the capture demonstrably works. A false FAIL on the
    # deciding gate is worse than no gate at all, hence the note.
    got, rows, tried = 0, 0, ["SPY", "AAPL", "MSFT"][:limit]
    err = ""
    for tk in tried:
        try:
            df = N._fetch_chain_cdn(tk, datetime.now())
            if df is not None and len(df):
                got += 1
                rows += len(df)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:50]
    where = ("THIS IS A DATACENTER IP — result is authoritative" if _is_cloud()
             else "residential IP — NOT proof for a datacenter")
    detail = f"{got}/{len(tried)} chains, {rows:,} rows · {where}"
    if not got and err:
        detail += f" · last error {err}"
    return got > 0, detail


@gate("D. Database read/write")
def gate_d():
    db = os.environ.get("NYSE_DB_PATH",
                        r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
    if not os.path.exists(db):
        return False, f"DB not found at {db}"
    size = os.path.getsize(db) / 1e9
    c = sqlite3.connect(db, timeout=30)
    try:
        n = c.execute("SELECT COUNT(*) FROM options_openbb").fetchone()[0]
        d = c.execute("SELECT MAX(trade_date) FROM options_openbb").fetchone()[0]
        c.execute("CREATE TABLE IF NOT EXISTS _smoke (t TEXT)")
        c.execute("INSERT INTO _smoke VALUES (?)", (str(time.time()),))
        c.execute("DROP TABLE _smoke")
        c.commit()
    finally:
        c.close()
    return True, f"{size:.2f} GB · {n:,} chain rows · latest {d} · writable"


@gate("E. Bot imports headless (no display)")
def gate_e():
    import telegram_bot_optimized as B
    missing = [f for f in ("_signal_writeup", "_fmt_paper_us", "position_monitor")
               if not hasattr(B, f)]
    return not missing, ("imports clean, engine reachable" if not missing
                         else f"missing {missing}")


@gate("F. Dashboard module parses")
def gate_f():
    import py_compile
    py_compile.compile("dashboard.py", doraise=True)
    return True, "dashboard.py compiles (Streamlit serves it as a script)"


@gate("G. Free-tier resource fit", critical=False)
def gate_g():
    db = os.environ.get("NYSE_DB_PATH",
                        r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
    size = os.path.getsize(db) / 1e9 if os.path.exists(db) else 0
    try:
        import resource                                   # POSIX only
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    except Exception:
        rss = 0
    years = (200 - size) / 2.5 if size else 0
    return True, (f"{size:.2f}/200 GB used (~{years:.0f} yrs at +2.5 GB/yr)"
                  + (f" · peak RSS {rss:.2f} GB / 12 GB" if rss else ""))


def _is_cloud():
    """Rough: are we on a cloud VM rather than the laptop?"""
    if os.name == "nt":
        return False
    for p in ("/sys/class/dmi/id/sys_vendor", "/sys/class/dmi/id/product_name"):
        try:
            v = open(p).read().lower()
            if any(k in v for k in ("oracle", "amazon", "google", "microsoft", "kvm", "qemu")):
                return True
        except Exception:
            pass
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the slow chain capture")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("=" * 96)
    print(f"CLOUD SMOKE TEST · host={'CLOUD VM' if _is_cloud() else 'local laptop'} "
          f"· python={sys.version.split()[0]} · platform={sys.platform}")
    print("=" * 96)
    gate_a(); gate_b()
    if a.quick:
        RESULTS.append(("C. OPTION CHAIN capture", "SKIP", "--quick", 0.0))
        print("  [SKIP] C. OPTION CHAIN capture               --quick")
    else:
        gate_c()
    gate_d(); gate_e(); gate_f(); gate_g()

    print("-" * 96)
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    warns = [r for r in RESULTS if r[1] == "WARN"]
    print(f"{len(RESULTS)} gates · {len(RESULTS)-len(fails)-len(warns)} pass · "
          f"{len(warns)} warn · {len(fails)} FAIL · {sum(r[3] for r in RESULTS):.1f}s")
    if fails:
        print("\nBLOCKING:")
        for n, _s, d, _t in fails:
            print(f"   {n}: {d}")
    if not _is_cloud():
        print("\nNOTE: run this same file ON THE VM before trusting the result. This host has a")
        print("      residential IP, so gate C cannot tell you whether a DATACENTER IP is")
        print("      blocked -- and that is the one thing that decides the migration.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
