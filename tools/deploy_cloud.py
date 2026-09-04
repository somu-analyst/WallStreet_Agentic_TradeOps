# -*- coding: utf-8 -*-
"""One command: canonical repo -> cloud repo -> VM -> restarted services.

WHY PUSH AND NOT POLL
    A timer on the VM pulling every few minutes would work, but you would never know whether a
    given change had landed without going to look. This runs to completion and tells you, so a
    failed deploy is visible at the moment you caused it rather than discovered later from
    behaviour that does not match the code you are reading.

WHAT IT REFUSES TO DO
    It will not deploy code that does not compile. `py_compile` is a weak check -- it proves
    syntax, not correctness -- but it is the difference between "this might be broken" and
    "this definitely cannot start", and the VM restarting into a file that cannot import means
    a bot that is down until someone notices.

    It will not restart services while a capture is running. Restarting the bot mid-capture is
    survivable, but the capture holds the single-instance lock and a restart during the derive
    step can leave a partial day -- which the audit then flags and someone has to investigate.

    It will not restart anything if nothing changed. A no-op deploy should cost nothing and
    should not interrupt a conversation with the bot.

Usage:
    python tools/deploy_cloud.py                 # sync, push, pull, restart if changed
    python tools/deploy_cloud.py --dry-run       # show what would move, touch nothing
    python tools/deploy_cloud.py --no-restart    # deploy the files, leave services alone
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLOUD = os.path.join(os.path.dirname(HERE), "NYSE_Cloud")
VM = os.environ.get("NYSE_VM", "ubuntu@150.136.41.250")
KEY = os.environ.get("NYSE_VM_KEY", r"C:\Users\srini\oci-nyse.key")
SSH = ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=25"]
CHECK = ["telegram_bot_optimized.py", "dashboard.py", "NYSE_OpenBB.py", "run_all_offhours.py"]


def sh(cmd, cwd=None, timeout=300):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main():
    dry = "--dry-run" in sys.argv
    no_restart = "--no-restart" in sys.argv
    t0 = time.time()

    # 1. Compile gate. Cheap, and the one failure that guarantees a dead service.
    print("[1/5] compile check")
    import py_compile
    for f in CHECK:
        p = os.path.join(HERE, f)
        if not os.path.exists(p):
            continue
        try:
            py_compile.compile(p, doraise=True)
        except py_compile.PyCompileError as e:
            print(f"      FAILED {f}\n{str(e)[:400]}")
            print("      nothing deployed")
            return 1
    print(f"      {len(CHECK)} files ok")

    # 2. Mirror.
    print("[2/5] mirror to the cloud tree")
    rc, out = sh([sys.executable, os.path.join(HERE, "tools", "sync_cloud.py")]
                 + (["--dry-run"] if dry else []), cwd=HERE)
    changed = [l.strip() for l in out.splitlines()
               if l.strip().startswith(("write ", "copy ", "build ", "remove "))]
    print(f"      {len(changed)} file(s) changed" + (f": {', '.join(changed[:4])}" if changed else ""))
    if dry:
        print("      dry run -- stopping here")
        return 0
    if not changed:
        print("      nothing to deploy")
        return 0

    # 3. Commit and push the mirror.
    print("[3/5] push the cloud repo")
    sh(["git", "add", "-A"], cwd=CLOUD)
    msg = "deploy: " + ", ".join(c.split()[-1] for c in changed[:3])
    if len(changed) > 3:
        msg += f" (+{len(changed)-3})"
    rc, out = sh(["git", "-c", "user.name=somu-analyst",
                  "-c", "user.email=srinivas.analystsas@gmail.com",
                  "commit", "-q", "-m", msg], cwd=CLOUD)
    rc, out = sh(["git", "push", "-q", "origin", "main"], cwd=CLOUD, timeout=300)
    if rc != 0:
        print(f"      push FAILED\n{out[:300]}")
        return 1
    print(f"      pushed: {msg}")

    # 4. Pull on the VM.
    print("[4/5] pull on the VM")
    rc, out = sh(SSH + [VM, "cd /home/ubuntu/nyse && git pull -q 2>&1 | tail -2 && "
                            "git log --oneline -1"], timeout=300)
    if rc != 0:
        print(f"      pull FAILED\n{out[:300]}")
        return 1
    print(f"      {out.strip().splitlines()[-1] if out.strip() else 'ok'}")

    # 5. Restart, but only when it is safe and useful.
    if no_restart:
        print("[5/5] restart skipped (--no-restart)")
        return 0
    print("[5/5] restart services")
    rc, out = sh(SSH + [VM, "ps -ef | grep -c '[c]loud_capture'"], timeout=60)
    if out.strip().split()[0] not in ("0", ""):
        print("      CAPTURE IS RUNNING -- not restarting. Re-run when it finishes,")
        print("      or: ssh ... 'sudo systemctl restart nyse-bot nyse-dashboard'")
        return 0
    rc, out = sh(SSH + [VM,
                        "sudo systemctl restart nyse-bot nyse-dashboard && sleep 20 && "
                        "for s in nyse-bot nyse-dashboard; do printf '%s=%s ' $s "
                        "$(systemctl is-active $s); done; echo; "
                        "ps -ef | grep -c '[c]loud_bot'"], timeout=180)
    print("      " + " ".join(out.split()))
    if "=failed" in out or "inactive" in out:
        print("      A SERVICE DID NOT COME BACK -- check journalctl -u nyse-bot -n 30")
        return 1

    # A fresh dashboard process pays a real, one-time cost on its FIRST session -- compiling
    # this file's bytecode, deriving the vault key, building the liquid-universe scan
    # (measured: several seconds, py-spy'd and confirmed real work -- cloud tracker row 43/48).
    # Before this, that cost landed on whoever happened to open the dashboard first after a
    # restart. It CANNOT be paid with a bare HTTP hit: Streamlit serves its static shell over
    # plain HTTP instantly, and only runs the actual Python script after the browser's JS opens
    # a websocket and asks for a rerun (checked -- a curl here returned in 16ms, far too fast
    # to be real; it primed nothing). A real client is required, so this drives one headlessly:
    # open the same tunnel a person would, load the page, let Playwright's own load-detection
    # wait for the script to actually finish, then throw the session away. Best-effort --
    # missing Playwright or a slow warm-up should never fail a deploy.
    print("[warm-up] priming the dashboard process", end=" ", flush=True)
    try:
        sys.path.insert(0, os.path.join(HERE, "tools"))
        import cloud_console as _cc
        tok, owner = _cc.dash_token()
        tun = subprocess.Popen(_cc.SSH + ["-N", "-L", f"{_cc.TUNNEL_PORT}:127.0.0.1:8502", VM],
                               **_cc._NO_WINDOW)
        try:
            from playwright.sync_api import sync_playwright
            time.sleep(3)
            wurl = f"http://127.0.0.1:{_cc.TUNNEL_PORT}/" + (f"?token={tok}&owner={owner}" if tok else "")
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_page()
                pg.goto(wurl, wait_until="load", timeout=45000)
                pg.wait_for_selector("section[data-testid='stSidebar']", timeout=45000)
                b.close()
            print("ok")
        finally:
            tun.terminate()
    except Exception as e:
        print(f"skipped ({str(e)[:80]})")

    print(f"\ndone in {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
