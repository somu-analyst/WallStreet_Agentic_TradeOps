# NEXT — handoff

Updated 2026-08-29. Read `python tools/show_pending.py --cloud` before acting; this file is a
summary, the sheet is the source of truth.

## Where things stand

**The migration is done.** The system runs on Oracle Ampere A1 (`150.136.41.250`, us-ashburn-1,
2 OCPU / 12 GB Always Free) and the laptop is not involved. The proof is not a smoke test: the
scheduled lane captured **732 tickers for 2026-08-28 by itself**.

Running there: `nyse-bot` (@WallStreet_AI_Ops_bot, a SECOND bot — the laptop keeps
@Analyst_Somu_AI_bot), `nyse-dashboard`, `cloud-keepalive`, `cloud-eod.timer`,
`cloud-backup.timer`, `fail2ban`.

Two repos, deliberately independent: canonical `WallStreet_Agentic_TradeOps` (edit here) and
`Street_Cloud_AI_TradeOps` (private, deployment mirror, **never edit** — `tools/sync_cloud.py`
overwrites it and renames every module on the way).

## Blocked on the user — nothing else can start

1. **Name a broker.** The one open compliance breach: Cboe's Market Data Policies prohibit
   automated extraction of delayed quote data, which is exactly what the nightly 733-ticker
   capture does, and the OpenBB `cboe` provider reads the same endpoint. Broker APIs permit
   programmatic access for their own account holders, free. The chain endpoint must return
   **open interest** — many real-time APIs omit it, and without OI GEX, walls, max pain and
   `/building` all stop working. Validate the swap the way the Finnhub one was: capture a day
   both ways and diff (that measured 0.000% before switching the price lane).
2. Revoke Telegram bot **8018716820** — found in git history, never rotated.
3. GitHub Support ticket to `gc` the repo after the history rewrite.
4. Budget `limit_use` → Monthly with an email recipient; it currently stops watching after August.
5. Approve Tailscale `serve`, then close port 22.

## In flight

`python tools/build_gex_history.py` running on the VM under `nohup nice -n 19`, log at
`~/gex_build.log`. Builds `gex_history`, ~29,300 ticker-days, roughly 80 minutes, resumable.
Purpose: `gamma_wall_trades` is empty, so the gamma-wall and zero-gamma claims have never been
scored. Once built, join to forward returns via `daily_ic` — and if a "near the wall" threshold
ever gets tuned, that must go through `walkforward.py`, not be fitted on the judging data.

## Undecided

- **Position pushes**: currently a new Telegram message every 10 min (RTH) / 15 min (off-hours).
  Proposed: edit one message in place off-hours, send new during market hours. `position_alerts`
  stays as new messages regardless — threshold breaches must never be silently overwritten.
- **Pay As You Go**: would remove both the idle-reclamation grey area and the 3 GB keep-alive.
  Parked by the user.
- **Impersonated CDN fallback** (`_fetch_chain_cdn`): delete once chains come from a broker.

## Traps this session paid for

- **A Windows-only API kills a Linux job silently.** `subprocess.CREATE_NO_WINDOW` meant the
  nightly scheduler had NEVER run; `ctypes.windll` would have done the same. Both now `getattr`.
- **A missing optional dependency fails open.** No `psutil` → bot and watchdog each concluded the
  other was absent and spawned it: 15 processes, 6.45 GB in 40 seconds.
- **A missing extra silently disables everything.** `python-telegram-bot` without `[job-queue]`
  emits a WARNING and every scheduled job never runs.
- **httpx logs request URLs at INFO**, and a Telegram API URL contains the token.
- **`git rm` does not remove anything.** History was rewritten to purge a 14 MB DB, the tracker
  and five files with hardcoded tokens. Backup mirror: `C:\Users\srini\repo_backup_20260828.git`.
- **Three secrets reached the chat transcript** (SSH key, vault passphrase, dashboard tokens).
  All rotated. `/terminal` exists so tokens never need copying by hand.
