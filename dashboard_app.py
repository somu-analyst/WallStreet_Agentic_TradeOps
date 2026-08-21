# -*- coding: utf-8 -*-
"""Launch the dashboard as a desktop app window — no Chrome required (ID 280).

WHY THIS EXISTS
    `webbrowser.open()` hands the URL to whatever the default browser is, as an ordinary
    tab. It has no concept of an installed PWA, which is why the installed Streamlit app
    never opened (ID 277). This launcher instead opens a dedicated, chrome-less window.

THE LADDER, best first. Every rung except the first needs NOTHING installed:
    1. pywebview  - a real native window using the WebView2 runtime that already ships with
                    Windows. No browser UI at all, own taskbar entry. Needs `pip install
                    pywebview` (small, pure-Python wrapper over the OS webview).
    2. Edge       - `msedge.exe --app=URL`. Edge is part of Windows, so this is the
                    zero-install option and looks identical to a PWA window.
    3. Chrome     - same flag, if Edge is somehow missing but Chrome is present.
    4. default browser - last resort, an ordinary tab.

It also starts the Streamlit server first when it is not already up, because opening a
window at a dead port just shows a connection error. That is the piece people miss: the
server and the window are two separate things.

Usage:
    python dashboard_app.py            # start server if needed, open the app window
    python dashboard_app.py --no-serve # window only, assume the server is already running
"""
import os
import socket
import subprocess
import sys
import time

PORT = 8502
URL = f"http://localhost:{PORT}"
ROOT = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(ROOT, "dashboard.py")


def _port_open(port=PORT, host="127.0.0.1", timeout=0.6):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def ensure_server(wait=60):
    """Start Streamlit headless if the port is dead. Returns True once it answers."""
    if _port_open():
        print(f"[app] server already up on {PORT}")
        return True
    if not os.path.exists(DASHBOARD):
        print(f"[app] cannot find {DASHBOARD}")
        return False
    print("[app] starting Streamlit…")
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", DASHBOARD,
         "--server.port", str(PORT), "--server.address", "0.0.0.0",
         "--server.headless", "true", "--browser.gatherUsageStats", "false"],
        cwd=ROOT,
        creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                       | getattr(subprocess, "DETACHED_PROCESS", 0)),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    for _ in range(wait * 2):
        if _port_open():
            print(f"[app] server ready on {PORT}")
            return True
        time.sleep(0.5)
    print("[app] server did not come up in time")
    return False


def _find(*candidates):
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def open_window():
    """Open the app window via the best rung available."""
    # 1. Native window
    try:
        import webview                       # noqa: F401  (optional dependency)
        print("[app] opening native window (pywebview)")
        webview.create_window("WallStreet TradeOps", URL,
                              width=1600, height=1000, resizable=True)
        webview.start()
        return True
    except ImportError:
        pass
    except Exception as e:
        print(f"[app] pywebview failed ({e}), falling back")

    # 1b. The INSTALLED PWA shortcut, if the user installed it. This is what carries OUR
    # icon: a plain `--app=URL` window keeps the browser's own icon, because Chrome only
    # adopts the site icon for an installed app (which is why the taskbar showed Chrome).
    # Launching the .lnk uses the real app id and therefore the real logo.
    appdata = os.environ.get("APPDATA", "")
    for name in ("RUDRARJUN Analytics.lnk", "WallStreet_Agentic_TradeOps.lnk"):
        lnk = os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                           "Programs", "Chrome Apps", name)
        if os.path.exists(lnk):
            print(f"[app] opening installed app: {name}")
            os.startfile(lnk)
            return True

    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    lad = os.environ.get("LOCALAPPDATA", "")
    # 2. Edge — part of Windows, so this needs nothing installed.
    edge = _find(os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
                 os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"))
    # 3. Chrome
    chrome = _find(os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
                   os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
                   os.path.join(lad, "Google", "Chrome", "Application", "chrome.exe"))
    for exe, name in ((edge, "Edge"), (chrome, "Chrome")):
        if exe:
            print(f"[app] opening {name} app window")
            subprocess.Popen([exe, f"--app={URL}",
                              f"--window-size=1600,1000"],
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return True
    # 4. Whatever the OS has
    import webbrowser
    print("[app] falling back to the default browser (ordinary tab)")
    return webbrowser.open(URL, new=2)


def ensure_bot():
    """Start the Telegram bot if it is not already polling (ID 283).

    One icon should start everything, rather than the user remembering which of several .bat
    files to click. The bot opens its own dashboard on startup, so this is the single entry
    point that `run_bot.bat` was.
    """
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "
             "'telegram_bot_optimized' } | Measure-Object).Count"],
            capture_output=True, text=True, timeout=30)
        if (out.stdout or "").strip().startswith("0"):
            print("[app] starting the Telegram bot…")
            subprocess.Popen([sys.executable, "telegram_bot_optimized.py"], cwd=ROOT,
                             creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                            | getattr(subprocess, "DETACHED_PROCESS", 0)),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL)
        else:
            print("[app] bot already running")
    except Exception as e:
        print(f"[app] could not check/start the bot: {e}")


if __name__ == "__main__":
    if "--with-bot" in sys.argv:
        ensure_bot()
    if "--no-serve" not in sys.argv:
        if not ensure_server():
            sys.exit(1)
    open_window()
