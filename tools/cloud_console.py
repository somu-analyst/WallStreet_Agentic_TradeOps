# -*- coding: utf-8 -*-
"""Desktop launcher for the CLOUD bot -- the counterpart to the local desktop shortcut.

WHAT DOUBLE-CLICKING DOES
    Opens the cloud dashboard in its own window. That is the whole job. The Telegram bot is a
    systemd service that has been up for days and is meant to stay up, so there is nothing to
    launch about it -- an earlier version of this file started the services on every click,
    which on every normal day was a no-op wearing the costume of an action.

    What is left is the one thing that genuinely is not running yet when you click: a tunnel
    to the dashboard and a window pointed at it. Service state is still checked, but it is
    reported in a line, not acted on -- restarting is [1] on the board, a decision you make
    after reading something, not a thing that happens because you opened a window.

WHY THE DASHBOARD NEEDS A TOKEN IN THE URL
    The cloud dashboard binds 127.0.0.1 on the VM and gates on a token from dash_token.txt --
    it holds the position book and has no login of its own. Reaching it therefore takes two
    keys: the ssh key opens the tunnel, the token opens the page. The launcher reads the token
    off the VM over that same ssh and hands it to the browser. It is never printed.

WHY ONE SSH ROUND TRIP
    Every status check below is a separate command, but they are batched into a single ssh
    call. Six sequential connections to a VM across the internet is six handshakes and several
    seconds of blank screen; one is under a second, and the screen is the whole point.

WHY THE DESKTOP ICON IS SILENT
    The shortcut runs this with pythonw.exe, not python.exe -- no console attaches, so there
    is nothing to print to and no board to show. It logs in, opens the tunnel, opens the
    dashboard window, and the process exits. A launch failure with nothing to say it to still
    leaves a line in logs/cloud_launcher.log rather than failing invisibly.

    Run it from an actual terminal (python.exe) for the interactive board -- same script,
    different attachment, detected via the win32 console handle, not by guessing from stdio.

Usage:
    python tools/cloud_console.py            # LAUNCH: start if down, open dashboard, then board
    python tools/cloud_console.py --menu     # skip the launch, go straight to the board
    python tools/cloud_console.py --status   # print status once and exit, for scripting
    pythonw tools/cloud_console.py           # what the desktop icon runs: silent, dashboard only
"""
import os
import subprocess
import sys
import time
import webbrowser

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VM = os.environ.get("NYSE_VM", "ubuntu@150.136.41.250")
KEY = os.environ.get("NYSE_VM_KEY", r"C:\Users\srini\oci-nyse.key")
DB = "/home/ubuntu/US_data_OpenBB.db"
REPO = "/home/ubuntu/nyse"
SERVICES = ["nyse-bot", "nyse-dashboard"]
TUNNEL_PORT = int(os.environ.get("NYSE_TUNNEL_PORT", "8602"))

SSH = ["ssh", "-i", KEY, "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=20",
       "-o", "BatchMode=yes"]

# The whole board in one command. Marker lines keep the parse honest -- a missing section
# means that check failed, not that the value is empty.
PROBE = r"""
echo "@up $(uptime -p 2>/dev/null | sed 's/^up //')"
echo "@load $(cut -d' ' -f1-3 /proc/loadavg)"
echo "@disk $(df -h / | tail -1 | awk '{print $3" used / "$2" ("$5")"}')"
for s in nyse-bot nyse-dashboard; do
  echo "@svc $s $(systemctl is-active $s) $(systemctl show -p ActiveEnterTimestamp --value $s | cut -d' ' -f2-3)"
done
echo "@cap $(sqlite3 -readonly DBPATH 'SELECT MAX(trade_date) FROM options_openbb;' 2>/dev/null)"
echo "@caps $(sqlite3 -readonly DBPATH 'SELECT COUNT(DISTINCT ticker) FROM options_openbb WHERE trade_date=(SELECT MAX(trade_date) FROM options_openbb);' 2>/dev/null)"
echo "@git $(cd REPOPATH && git log --oneline -1 2>/dev/null)"
# Tracebacks are the health signal; a raw [ERROR] count is not. 250+ of those a day are
# yfinance saying "no earnings dates" for ETFs, which is true and expected -- counting them
# would put a permanent red number on the board that nobody can ever act on.
J="journalctl -u nyse-bot --since '24 hours ago' --no-pager"
echo "@err $(eval $J 2>/dev/null | grep -c 'Traceback (most recent call last)')"
echo "@errl $(eval $J 2>/dev/null | grep '\[ERROR\]' | grep -vc 'No earnings dates found')"
""".replace("DBPATH", DB).replace("REPOPATH", REPO)


# ssh.exe is a console app. Under pythonw (no console attached to THIS process at all --
# what the desktop shortcut runs), Windows does not just skip giving it one: CreateProcess
# auto-allocates a FRESH console for every single child console app that doesn't ask
# otherwise, and it flashes on screen for however long that child runs. Every ssh() call and
# the tunnel below is exactly that kind of child, so without this flag each one pops its own
# window -- several per launch, each closing the instant its own command finishes, which
# reads as "cmd windows keep opening" (user 2026-09-04) rather than one persistent console.
# Under a real terminal (python.exe, console already exists) this flag changes nothing
# observable, so it is applied unconditionally rather than only in the quiet path.
_NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def ssh(cmd, timeout=90):
    """Run one command on the VM. Returns (ok, text) -- never raises, because a dead network
    is a normal state for this screen to show, not a crash."""
    try:
        r = subprocess.run(SSH + [VM, cmd], capture_output=True, text=True, timeout=timeout,
                           **_NO_WINDOW)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except Exception as e:  # ssh missing, key unreadable
        return False, str(e)


def probe():
    ok, out = ssh(PROBE, timeout=60)
    d = {"svc": {}}
    if not ok:
        d["error"] = out.strip().splitlines()[-1] if out.strip() else "unreachable"
        return d
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("@"):
            continue
        tag, _, rest = line[1:].partition(" ")
        if tag == "svc":
            parts = rest.split(None, 2)
            if parts:
                d["svc"][parts[0]] = (parts[1] if len(parts) > 1 else "?",
                                      parts[2] if len(parts) > 2 else "")
        else:
            d[tag] = rest.strip()
    return d


def board(clear=True):
    """clear=False draws the board in place, without wiping the screen. That is what the
    launcher wants: the launch log above (what started, whether the tunnel came up, whether
    the token was readable) is the context for the numbers below, and clearing to show them
    would throw away the only record of how the run went."""
    if clear:
        os.system("cls" if os.name == "nt" else "clear")
    print("=" * 64)
    print(" NYSE CLOUD BOT".ljust(46) + VM.split("@")[-1])
    print("=" * 64)
    t0 = time.time()
    # Only draw the transient "checking" line on a real console -- \r means nothing to a pipe
    # and would leave the word wedged into the first status row of captured output.
    tty = sys.stdout.isatty()
    if tty:
        print(" checking...", end="", flush=True)
    d = probe()
    if tty:
        print("\r" + " " * 20 + "\r", end="")
    if d.get("error"):
        print(" STATUS   UNREACHABLE".ljust(64))
        print(f"          {d['error'][:56]}")
        print("\n          The VM may be stopped, or the key/host may have moved.")
        print(f"          key : {KEY}")
        print("=" * 64)
        return d

    for s in SERVICES:
        state, since = d["svc"].get(s, ("?", ""))
        mark = "OK  " if state == "active" else "DOWN"
        print(f" {mark} {s:<16} {state:<10} since {since[:16]}")
    print("-" * 64)
    print(f" host     up {d.get('up', '?')}   load {d.get('load', '?')}")
    print(f" disk     {d.get('disk', '?')}")
    cap, caps = d.get("cap", "?"), d.get("caps", "?")
    print(f" capture  {cap}   {caps} tickers")
    print(f" code     {d.get('git', '?')[:52]}")
    print(f" log      {d.get('err', '?')} traceback(s), {d.get('errl', '?')} error line(s) in 24h")
    print("=" * 64)
    print(f" [1] restart services   [2] bot log     [3] capture log")
    print(f" [4] open dashboard     [5] deploy      [r] refresh   [q] quit")
    print("=" * 64)
    print(f" (checked in {time.time()-t0:.1f}s)")
    return d


def restart():
    print("\n checking for a running capture first...")
    ok, out = ssh("ps -ef | grep -c '[c]loud_capture'", timeout=45)
    if ok and out.strip().split() and out.strip().split()[0] not in ("0", ""):
        print(" CAPTURE IS RUNNING -- not restarting. It holds the single-instance lock and")
        print(" a restart mid-derive can leave a partial day. Try again when it finishes.")
        return
    print(" restarting nyse-bot + nyse-dashboard (about 20s)...")
    ok, out = ssh("sudo systemctl restart nyse-bot nyse-dashboard && sleep 20 && "
                  "for s in nyse-bot nyse-dashboard; do printf '%s=%s ' $s "
                  "$(systemctl is-active $s); done; echo", timeout=180)
    print(" " + " ".join(out.split())[:200])
    if not ok or "=failed" in out or "=inactive" in out:
        print(" A SERVICE DID NOT COME BACK -- read the bot log ([2]).")


def log(unit_cmd, title):
    print(f"\n---- {title} ----")
    ok, out = ssh(unit_cmd, timeout=90)
    tail = out.strip().splitlines()
    print("\n".join(tail[-60:]) if tail else " (empty)")


def dash_token():
    """Read the dashboard token off the VM. Fetched on its own rather than in the status probe
    so the secret never sits in the dict the board prints from -- there is no code path that
    can put it on screen by accident. Returns "" if it cannot be read, which is worth showing
    as a specific failure: the tunnel will work and the page will still refuse you."""
    ok, out = ssh(f"cat {REPO}/dash_token.txt 2>/dev/null; echo ---; "
                  f"cat {REPO}/dash_owner.txt 2>/dev/null", timeout=45)
    if not ok:
        return "", ""
    part = (out or "").split("---")
    acc = part[0].strip().splitlines()
    own = part[1].strip().splitlines() if len(part) > 1 else []
    return (acc[0].strip() if acc else ""), (own[0].strip() if own else "")


def tunnel():
    """Two keys open this page. The ssh key opens the tunnel -- the dashboard binds 127.0.0.1
    on the VM on purpose, since exposing 8502 to the internet would publish the position book.
    The token from dash_token.txt then opens the page itself. Having only the first gets you
    'Access token required', which looks like a broken tunnel and is not one."""
    import socket
    s = socket.socket()
    s.settimeout(0.4)
    live = s.connect_ex(("127.0.0.1", TUNNEL_PORT)) == 0
    s.close()
    if not live:
        print(f"\n opening ssh tunnel {TUNNEL_PORT} -> VM 8502 ...")
        cmd = SSH + ["-N", "-L", f"{TUNNEL_PORT}:127.0.0.1:8502", VM]
        # Surviving the launcher process exiting needs no visible console at all -- a Windows
        # child does not die with its parent by default. The earlier CREATE_NEW_CONSOLE was
        # solving a problem that did not exist, at the cost of a permanent black window.
        subprocess.Popen(cmd, **_NO_WINDOW)
        time.sleep(3)
    else:
        print(f" tunnel already up on {TUNNEL_PORT}")
    base = f"http://127.0.0.1:{TUNNEL_PORT}"
    tok, owner = dash_token()
    url = base
    shown = base
    if tok:
        url += f"/?token={tok}"
        shown += "/?token=<dash_token.txt>"
        if owner:  # unlocks the book without typing a password
            url += f"&owner={owner}"
            shown += "&owner=<dash_owner.txt>"
    _open_window(url)
    print(f" opening {shown}")
    if not tok:
        print(" COULD NOT READ dash_token.txt -- the page will say 'Access token required'.")
        print(f" Get the token from the bot's /terminal, or: ssh ... cat {REPO}/dash_token.txt")
    elif not owner:
        print(" No dash_owner.txt on the VM -- the book pages will still ask for a password.")
    print(" (tunnel runs hidden in the background; closes when you sign out or reboot)")


# Chromium's app mode, in preference order. --app= gives a window with no tab strip, no
# omnibox and its own taskbar entry, which is the difference between "a dashboard" and "a
# tab I lose behind twenty others".
_BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


# A profile of its own, not the browser's daily-driver one. Reusing the default profile
# meant this window inherited whatever that profile had already accumulated for
# 127.0.0.1:8602 -- Chrome remembers page zoom PER ORIGIN forever, so one stray Ctrl+scroll,
# ever, on that exact origin (during testing, or a trackpad slip) would silently reapply on
# every future open. A dedicated profile has no such history and never can.
_PROFILE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                            "NYSE_CloudDashboard", "ChromeProfile")



def _open_window(url):
    """Open the dashboard as its own window, not a tab. Falls back to the default browser if
    no chromium is found -- a tab you can see beats a window you cannot open.

    NO --window-size. The local launcher (telegram_bot_optimized.py open_dashboard_on_startup)
    never passes one either -- it lets Chrome's own per-profile window memory take over after
    the first open, which is exactly why the local window has settled in nice and large over
    time. A calculated --window-size does the opposite of that: it wins over whatever the user
    just resized the window to, EVERY launch, forever -- so even a manual maximize gets undone
    the next time the icon is clicked. That fight, not a font or a zoom level, is what read as
    "cloud is zoomed" (confirmed: identical computed font-size and devicePixelRatio on both
    pages at a matched viewport -- the only variable left was real window size). --start-
    maximized replaces it: gives a fresh profile a full-size window on its very first launch
    (nothing to remember yet), then gets out of the way -- Chrome remembers from there, same
    as local."""
    for exe in _BROWSERS:
        if os.path.exists(exe):
            try:
                os.makedirs(_PROFILE_DIR, exist_ok=True)
                subprocess.Popen([exe, f"--app={url}", "--start-maximized",
                                  f"--user-data-dir={_PROFILE_DIR}",
                                  "--no-first-run", "--no-default-browser-check"])
                return True
            except Exception:
                break
    webbrowser.open(url)
    return False


def launch():
    """What the desktop icon runs. Log in, make sure the bot is up, put the dashboard on
    screen. Returns False only when the VM itself could not be reached -- everything else is
    reported and carried on from, because a dashboard you can read is useful even on a day
    when one service is refusing to start."""
    print("=" * 64)
    print(" NYSE CLOUD BOT -- starting".ljust(46) + VM.split("@")[-1])
    print("=" * 64)

    print(" [1/2] connecting ...", end=" ", flush=True)
    ok, out = ssh("for s in " + " ".join(SERVICES) +
                  "; do printf '%s=%s ' $s $(systemctl is-active $s); done; echo", timeout=60)
    if not ok:
        print("FAILED")
        line = out.strip().splitlines()[-1] if out.strip() else "unreachable"
        print(f"\n  {line[:60]}")
        print("\n  The VM did not answer. It may be stopped in the Oracle console, or the")
        print("  key/address may have moved.")
        print(f"  key  {KEY}")
        print(f"  host {VM}")
        return False
    state = dict(p.split("=", 1) for p in out.split() if "=" in p)
    down = [s for s in SERVICES if state.get(s) != "active"]
    print("ok" + ("" if not down else f"  ({', '.join(down)} DOWN -- [1] restarts)"))

    print(" [2/2] dashboard")
    tunnel()
    print()  # the board's own rule follows immediately; two in a row reads as a glitch
    return True


def deploy():
    print("\n running tools/deploy_cloud.py ...\n")
    subprocess.run([sys.executable, os.path.join(HERE, "tools", "deploy_cloud.py")], cwd=HERE)


def _has_console():
    """Is there an actual console attached to read our stdout? True for a terminal running
    python.exe; False for pythonw.exe (the desktop shortcut) and for GetConsoleWindow itself
    failing. isatty() alone is not the right test here -- pythonw's stdout is a real,
    non-None stream (redirected to nul), so it still answers isatty() calls; only the win32
    console handle tells us whether anything is actually visible."""
    if os.name != "nt":
        return bool(sys.stdin) and sys.stdin.isatty()
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.GetConsoleWindow())
    except Exception:
        return True  # can't tell -- behave like a normal terminal run


def _quiet_fail(reason):
    """No console to report to. Leave a trail instead of failing invisibly -- the desktop
    icon otherwise just does nothing and there is no way to tell why."""
    try:
        d = os.path.join(HERE, "logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "cloud_launcher.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {reason}\n")
    except Exception:
        pass


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--status" in sys.argv:
        board()
        return 0

    quiet = not _has_console()   # the desktop shortcut: just open the dashboard, nothing else
    inline = False
    if "--menu" not in sys.argv:
        ok = launch()
        if quiet:
            if not ok:
                _quiet_fail("launch failed -- VM unreachable (see board/--status for detail)")
            return 0 if ok else 1
        if not ok:
            # Unreachable VM: hold the window open so the reason is readable. Dropping
            # straight to the board would just redraw the same failure.
            try:
                input("\n press Enter to close ")
            except (EOFError, KeyboardInterrupt):
                pass
            return 1
        inline = True  # first board draws under the launch log, not over it
    while True:
        board(clear=not inline)
        inline = False
        try:
            c = input("\n > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 0
        if c in ("q", "quit", "exit"):
            return 0
        if c == "1":
            restart()
        elif c == "2":
            log("journalctl -u nyse-bot -n 60 --no-pager", "nyse-bot (last 60)")
        elif c == "3":
            log("tail -n 40 /home/ubuntu/capture.log", "capture.log (last 40)")
        elif c == "4":
            tunnel()
        elif c == "5":
            deploy()
        elif c == "r":
            continue
        else:
            continue
        input("\n press Enter to return to the board ")


if __name__ == "__main__":
    sys.exit(main())
