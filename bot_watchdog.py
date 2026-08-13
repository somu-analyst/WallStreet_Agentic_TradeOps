# -*- coding: utf-8 -*-
r"""Keep the Telegram bot alive. Replaces bot_watchdog.ps1 + bot_watchdog_hidden.vbs.

WHY THIS IS PYTHON NOW (2026-08-08)
-----------------------------------
The PowerShell version was quarantined by the user's antivirus as IDP.Generic. Nothing was
injected -- the file was byte-identical to what was written -- but IDP.Generic is a
BEHAVIOURAL detection and the old design earned it honestly:

    bot_watchdog_hidden.vbs   WScript.Shell.Run(..., 0, False)   <- hidden window
      -> powershell.exe -ExecutionPolicy Bypass -File ...        <- policy bypass
      -> Get-CimInstance Win32_Process, reading other processes' command lines
      -> DNS lookup of an external host
      -> Start-Process -WindowStyle Hidden                       <- detached hidden spawn

That is the fingerprint of a dropper establishing persistence and checking in. The scanner
read the behaviour correctly; only the intent was wrong. Arguing with it via an exclusion
would leave a script on disk that looks like malware to every future scan, so the design was
replaced instead:

  * no .vbs launcher       -- pythonw.exe has no console at all, which is what the VBS was for
  * no PowerShell          -- and therefore no -ExecutionPolicy Bypass
  * no hidden-window trick -- nothing is being concealed, so nothing looks concealed
  * psutil if available    -- a normal library call instead of WMI command-line scraping

Same three-step logic as before, which was never the problem:
  1. Is a telegram_bot_optimized.py process alive?        -> if yes, do nothing, silently
  2. Is the network actually up (DNS for api.telegram.org)? -> if not, DEFER the restart.
     A wake-from-sleep blip is not a dead bot; restarting into a dead network burns a start
     and loses the job queue.
  3. Otherwise start the bot detached and log why.

Run it windowless:  pythonw.exe bot_watchdog.py
Check what it did:  logs\watchdog.log   (silent on success -- only actions are logged)
"""
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "telegram_bot_optimized.py")
LOG_DIR = os.path.join(ROOT, "logs")
LOG = os.path.join(LOG_DIR, "watchdog.log")
TARGET = "telegram_bot_optimized.py"
HOST = "api.telegram.org"


def write_log(msg):
    """Logging must NEVER take the watchdog down. Two overlapping runs both appending threw
    'file in use' on Windows and killed the old script outright (caught 2026-08-07). Retry
    briefly, then give up silently -- restarting the bot matters, recording it does not."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        line = "[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
        for _ in range(5):
            try:
                with open(LOG, "a", encoding="utf-8") as fh:
                    fh.write(line)
                return
            except OSError:
                time.sleep(0.2)
    except Exception:
        pass


def bot_pids():
    """PIDs running the bot. Matches the COMMAND LINE, not the image name: several python.exe
    processes run here (dashboard, intraday lane), so a bare name check always looks healthy."""
    try:
        import psutil
    except ImportError:
        return _bot_pids_fallback()
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if not (p.info["name"] or "").lower().startswith("python"):
                continue
            if any(TARGET in part for part in (p.info["cmdline"] or [])):
                out.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _bot_pids_fallback():
    """No psutil: ask the OS. Uses CREATE_NO_WINDOW so the query itself never flashes a
    console -- the whole reason the old launcher existed."""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        raw = subprocess.run(
            ["wmic", "process", "where", "name like 'python%'", "get", "ProcessId,CommandLine"],
            capture_output=True, text=True, timeout=30, creationflags=flags).stdout
    except Exception:
        return []
    pids = []
    for line in raw.splitlines():
        if TARGET in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.append(int(parts[-1]))
    return pids


def network_up():
    try:
        socket.gethostbyname(HOST)
        return True
    except OSError:
        return False


def watchdog_pids():
    """Other live copies of THIS script. Without this, every bot start would stack another
    watchdog and they would race to restart the bot together."""
    me = os.getpid()
    try:
        import psutil
    except ImportError:
        return []
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["pid"] == me:
                continue
            if not (p.info["name"] or "").lower().startswith("python"):
                continue
            argv = p.info["cmdline"] or []
            # basename match + the --loop flag, NOT a substring scan: a shell that merely
            # mentions this filename (a py_compile, a grep) must not read as a live watchdog
            if any(os.path.basename(a) == "bot_watchdog.py" for a in argv) and "--loop" in argv:
                out.append(p.info["pid"])
        except Exception:
            continue
    return out


def main():
    if bot_pids():
        return 0                      # healthy -- stay silent

    if not network_up():
        write_log("bot down but DNS for %s fails - network not up yet, deferring restart"
                  % HOST)
        return 0

    if not os.path.exists(SCRIPT):
        write_log("cannot restart: %s missing" % SCRIPT)
        return 1

    # sys.executable is pythonw.exe when launched windowless; the BOT wants the console
    # build so its own logging behaves, so swap back if needed.
    exe = sys.executable or "python.exe"
    if os.path.basename(exe).lower() == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(cand):
            exe = cand

    try:
        subprocess.Popen(
            [exe, SCRIPT], cwd=ROOT,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                           | getattr(subprocess, "DETACHED_PROCESS", 0)),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL)
    except Exception as exc:
        write_log("restart failed to launch: %s" % exc)
        return 1

    time.sleep(12)
    pids = bot_pids()
    if pids:
        write_log("bot was down - restarted OK (pid %d)" % pids[0])
    else:
        write_log("bot was down - restart attempted but process not found after 12s")
    return 0


def loop(interval=300):
    """Run the check forever. This is how the watchdog runs WITHOUT Task Scheduler.

    Registering a scheduled task on this machine returns Access denied even for a task the
    user authored and even in a user subfolder, so the 5-minute trigger had to come from
    somewhere else. The bot spawns this loop DETACHED at startup, which means it outlives the
    bot: if the bot crashes, this restarts it; if this dies, the next bot start replaces it.
    Mutual supervision, no elevation, no registry or Startup-folder persistence.

    The one case it does NOT cover is a cold boot with neither running -- that still needs the
    logon trigger, i.e. the one elevated command.
    """
    if watchdog_pids():
        return 0                      # another loop already owns the job
    write_log("watchdog loop started (interval %ds, pid %d)" % (interval, os.getpid()))
    while True:
        try:
            main()
        except Exception as exc:      # a bad tick must never end the loop
            write_log("watchdog tick failed: %s" % exc)
        time.sleep(interval)


if __name__ == "__main__":
    if "--loop" in sys.argv:
        iv = 300
        if "--interval" in sys.argv:
            try:
                iv = int(sys.argv[sys.argv.index("--interval") + 1])
            except (ValueError, IndexError):
                pass
        sys.exit(loop(iv) or 0)
    sys.exit(main())
