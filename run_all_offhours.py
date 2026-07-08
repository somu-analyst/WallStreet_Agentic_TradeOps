import os
import sys
import subprocess
import threading
import time
from datetime import datetime, timedelta, date
from pathlib import Path
import pandas_market_calendars as mcal
import ctypes
from zoneinfo import ZoneInfo


# ================== PATHS / CONFIG ==================
BASE_DIR = r"C:\Users\srini\Options_chain_data\NYSE_DATA"
JOB1 = os.path.join(BASE_DIR, "NYSE_YFin.py")
JOB2 = os.path.join(BASE_DIR, "NYSE_Telegram.py")
# OpenBB parallel lane (runs alongside the Yahoo fetch; writes ONLY US_data_OpenBB.db).
# Non-fatal: BB failure never affects the Yahoo run or JOB2. Retire once DB_PATH flips to BB.
JOB_BB = os.path.join(BASE_DIR, "NYSE_OpenBB.py")
JOB_BB_DERIVE = os.path.join(BASE_DIR, "NYSE_OpenBB_derive.py")
STATE_DIR = BASE_DIR
STATE_FILE = os.path.join(STATE_DIR, "run_all_offhours_last_ok.txt")
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Run gate windows (NY time):
#   Pre-market  : midnight – PRE_MARKET_END  (targets previous trading day)
#   Post-close  : POST_CLOSE_START – midnight (targets today)
RUN_TZ = "America/New_York"
PRE_MARKET_END   = 9    # 00:00 – 08:59 NY → pull previous trading day EOD
POST_CLOSE_START = 17   # 17:00+  NY     → pull today's EOD


# Anti-sleep flags
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


# Globals
sleep_cookie = None
stop_sleep_thread = False
main_log = None  # Global for log_msg


def prevent_sleep():
    global sleep_cookie
    sleep_cookie = ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    )


def refresh_sleep():
    global stop_sleep_thread
    while not stop_sleep_thread:
        time.sleep(30)
        if sleep_cookie:
            ctypes.windll.kernel32.SetThreadExecutionState(sleep_cookie)


def allow_sleep():
    global stop_sleep_thread
    stop_sleep_thread = True
    if sleep_cookie:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)


NYSE = mcal.get_calendar("NYSE")


def log_msg(msg):
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)                        # Show in CMD
    if main_log:
        main_log.write(line + "\n")    # Write to log file
        main_log.flush()


# --- Trading‑hours helpers ---


def in_off_hours():
    """Return True if current time is considered 'off‑hours' for NYSE."""
    ny_tz = ZoneInfo("America/New_York")
    now = datetime.now(ny_tz)
    today = now.date()

    if not is_trading_day(today):
        return True  # Weekends/holidays are off‑hours

    # Normal NYSE hours: 9:30 AM – 4:00 PM ET
    start_time = datetime.combine(today, datetime.min.time(), tzinfo=ny_tz).replace(hour=9, minute=30)
    end_time   = datetime.combine(today, datetime.min.time(), tzinfo=ny_tz).replace(hour=16, minute=0)

    return now < start_time or now > end_time


def can_run_now_for_gate():
    """Return (ok, target_day, today_ny, now_ny, reason).

    Two allowed windows (NY time):
      Pre-market  00:00–PRE_MARKET_END   → target = previous trading day
      Post-close  POST_CLOSE_START–23:59 → target = today (must be trading day)
    """
    ny_tz = ZoneInfo(RUN_TZ)
    now_ny = datetime.now(ny_tz)
    today_ny = now_ny.date()
    hour = now_ny.hour

    # Pre-market window: midnight up to PRE_MARKET_END
    if hour < PRE_MARKET_END:
        prev = last_trading_day_before(today_ny)
        if prev is None:
            return False, today_ny, today_ny, now_ny, "No previous trading day found"
        return True, prev, today_ny, now_ny, f"Pre-market: targeting {prev}"

    # Post-close window: POST_CLOSE_START onwards, today must be a trading day
    if hour >= POST_CLOSE_START:
        if not is_trading_day(today_ny):
            return False, today_ny, today_ny, now_ny, "Today is not an NYSE trading day"
        return True, today_ny, today_ny, now_ny, "Post-close: targeting today"

    return False, today_ny, today_ny, now_ny, f"Market hours ({hour:02d}:xx NY) — not a run window"


def is_trading_day(day: date) -> bool:
    sch = NYSE.schedule(start_date=day, end_date=day)
    return not sch.empty


def last_trading_day_before(day: date):
    prev = day - timedelta(days=1)
    # Look back up to 10 days in case of holidays
    while prev > (day - timedelta(days=10)):
        if is_trading_day(prev):
            return prev
        prev -= timedelta(days=1)
    return None


def already_ran_for(day: date) -> bool:
    """Return True if we already ran for this trading day."""
    state = Path(STATE_FILE)
    if not state.exists():
        return False
    try:
        with state.open(encoding="utf-8") as f:
            content = f.read().strip()
            return content == day.strftime("%Y-%m-%d")
    except Exception:
        return False


def mark_success_for(day: date):
    """Mark that we successfully processed this trading day."""
    state = Path(STATE_FILE)
    try:
        state.parent.mkdir(parents=True, exist_ok=True)
        with state.open("w", encoding="utf-8") as f:
            f.write(day.strftime("%Y-%m-%d"))
    except Exception as e:
        log_msg(f"Error writing state: {e}")


# --- Job runner (with stdout echoed to CMD) ---


def run_job_headless(path):
    job_dir = os.path.dirname(path)
    job_name = os.path.splitext(os.path.basename(path))[0]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    log_file = os.path.join(LOG_DIR, f"{job_name}_{ts}.log")

    log_msg(f"Starting {job_name} -> {log_file}")

    with open(log_file, "a", encoding="utf-8") as log:
        log.write("=" * 80 + "\n")
        log.write(f"[{datetime.now().isoformat()}] Started: {path}\n\n")

        proc = subprocess.Popen(
            [sys.executable, "-u", path],
            cwd=job_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        for line in proc.stdout:
            line = line.rstrip()                 # Strip trailing newline
            print(line)                          # Show in CMD
            log.write(line + "\n")               # Write to log file
            log.flush()

        proc.wait()
        log.write(f"\n[{datetime.now().isoformat()}] Ended rc={proc.returncode}\n")
        log.write("=" * 80 + "\n")

    log_msg(f"{job_name} finished rc={proc.returncode}")
    return proc.returncode


def launch_job_background(path):
    """Start a job detached (own log file, no CMD echo) and return its Popen handle.
    Used for the OpenBB parallel lane so it overlaps the long Yahoo fetch."""
    job_name = os.path.splitext(os.path.basename(path))[0]
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    log_file = os.path.join(LOG_DIR, f"{job_name}_{ts}.log")
    log_msg(f"Launching {job_name} in background -> {log_file}")
    lf = open(log_file, "a", encoding="utf-8")
    lf.write("=" * 80 + f"\n[{datetime.now().isoformat()}] Started (bg): {path}\n\n")
    proc = subprocess.Popen(
        [sys.executable, "-u", path], cwd=os.path.dirname(path),
        stdout=lf, stderr=subprocess.STDOUT, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc, lf


def run_openbb_parallel_lane(bb_proc, bb_log):
    """After the Yahoo fetch, wait for the background OpenBB capture, then derive the same-schema
    tables into US_data_OpenBB.db. Fully non-fatal — logs and swallows any failure."""
    try:
        if bb_proc is not None:
            log_msg("Waiting for OpenBB capture to finish...")
            bb_rc = bb_proc.wait()
            try:
                bb_log.close()
            except Exception:
                pass
            log_msg(f"OpenBB capture finished rc={bb_rc}")
        log_msg("Running OpenBB derive (options_daily/options_change)...")
        rc = run_job_headless(JOB_BB_DERIVE)   # reuse the streaming runner (no --stock: options only)
        log_msg(f"OpenBB derive finished rc={rc}")
    except Exception as e:
        log_msg(f"OpenBB parallel lane error (non-fatal): {e}")


# --- Main scheduler ---


if __name__ == "__main__":
    DRY_RUN = "--dry-run" in sys.argv

    start_time = datetime.now()
    ts = start_time.strftime("%Y%m%d_%H%M")
    main_log_path = os.path.join(LOG_DIR, f"scheduler_{ts}.log")

    main_log = open(main_log_path, "a", encoding="utf-8")
    success = False
    exit_code = 1

    try:
        prevent_sleep()
        sleep_thread = threading.Thread(target=refresh_sleep, daemon=True)
        sleep_thread.start()

        log_msg("=== SCHEDULER STARTED ===")
        if DRY_RUN:
            log_msg("*** DRY-RUN MODE — jobs will NOT be launched ***")
        allowed, target_day, today_ny, now_ny, reason = can_run_now_for_gate()
        log_msg(f"NY now: {now_ny.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if not allowed:
            log_msg(f"Skipping run: {reason}")
            success = True
            exit_code = 0
            sys.exit(exit_code)

        log_msg(f"Gate passed ({reason}), Target: {target_day}")

        # 3. Skip if already ran for this day
        if already_ran_for(target_day):
            log_msg(f"Already ran for {target_day}. Exiting.")
            success = True
            exit_code = 0
            sys.exit(exit_code)

        log_msg(f"Running for target: {target_day}")

        # 4. Run the two jobs (output visible in CMD and in log files)
        if DRY_RUN:
            log_msg(f"[DRY-RUN] Would launch (parallel): {JOB_BB}")
            log_msg(f"[DRY-RUN] Would run: {JOB1}")
            log_msg(f"[DRY-RUN] Would run: {JOB_BB_DERIVE} (after BB capture)")
            log_msg(f"[DRY-RUN] Would run: {JOB2}")
            log_msg("[DRY-RUN] State file would be written — skipping.")
            success = True
            exit_code = 0
        else:
            # Kick off the OpenBB capture in parallel with the long Yahoo fetch (non-fatal).
            bb_proc = bb_log = None
            try:
                bb_proc, bb_log = launch_job_background(JOB_BB)
            except Exception as e:
                log_msg(f"Could not launch OpenBB capture (non-fatal): {e}")

            rc1 = run_job_headless(JOB1)

            # BB capture should be done by now (Yahoo fetch is the long pole); derive its tables.
            run_openbb_parallel_lane(bb_proc, bb_log)

            rc2 = run_job_headless(JOB2)

            success = (rc1 == 0 and rc2 == 0)
            if success:
                mark_success_for(target_day)
                log_msg("ALL JOBS SUCCESS!")
                exit_code = 0
            else:
                log_msg(f"FAILURE: rc1={rc1}, rc2={rc2}")
                exit_code = 1

        elapsed = (datetime.now() - start_time).total_seconds()
        log_msg(f"Total runtime: {elapsed:.1f}s")
        log_msg("=== SCHEDULER ENDED ===")

    finally:
        allow_sleep()
        if main_log:
            main_log.close()

    sys.exit(exit_code)