[RESUME AFTER] 2026-09-03 22:00  (limit-guard: block at 134177971 tokens >= 80000000)
# NEXT — handoff

Updated 2026-09-04. Read `python tools/show_pending.py --cloud` before acting; this file is a
summary, the sheet is the source of truth.

## Resume here (2026-09-04 session)

Full detail in `docs/LOG.md` (top entry) and Cloud Migration tracker IDs 24–45. Short version:

- **Row 41 (live position sync) — SHIPPED, running unattended, verified live. Don't rebuild
  this.** Abandoned the Telegram-relay design from the prior handoff (blocked on a manual
  BotFather step) in favor of a full table diff — `trades` is only ~90 rows, cheap to compare
  whole, no schema change needed. `tools/sync_trades.py`: diff local vs cloud `trades` by
  `trade_id`, last-writer-wins on `updated_at` (already existed), parameterized writes only
  (never string-built SQL — `notes` is free text). **Found and fixed a real landmine first**:
  local/cloud `trade_id` autoincrement counters had diverged since the 08-27/28 seed split
  (local next=91, cloud next=89) — the next cloud-side add would have collided with an
  existing local trade. Reserved cloud ids at 1,000,000+ via `sqlite_sequence` (DB backed up
  first, zero existing rows touched). Applied the 2 backlogged TSLA trades — cloud row 34
  (empty book) closed as a result. Wired to Windows Scheduled Task `NYSE_TradeSync`
  (`pythonw tools/sync_trades.py --apply --quiet`, every 2 min) — independent of whether
  either bot process is open. Verified by making a real local change, letting the task fire
  itself (not invoking the script by hand), and confirming the matching timestamp landed on
  cloud via direct SQL. Cadence is 2 minutes, not instant — fine for a personal book; only
  revisit if the user asks for tighter.
- **Desktop launcher shipped, verified, and a real regression already fixed**: on the FIRST
  cut, `pythonw` (no console) meant every `ssh` call auto-got its OWN fresh console window
  from Windows (nothing to inherit) — the tunnel's Popen also explicitly asked for
  `CREATE_NEW_CONSOLE`, my own mistake. User reported "many cmds opening" (cloud row 44).
  Fixed: `creationflags=CREATE_NO_WINDOW` on every ssh subprocess call. Verified properly
  this time — not a process-list snapshot (which false-positived on THIS Claude Code
  session's own unrelated conhost/cmd noise) but a 100ms-resolution `IsWindowVisible` poll
  across the full 12s launch, against a pre-launch baseline. **0 visible windows.** Don't
  redo this fix; if it recurs, the bug is somewhere new.
- Book unlock, `time`-import crash, title/badge, Chrome-zoom isolation, and the
  `magicEnabled` perf fix are all shipped and deployed (cloud HEAD `c33d106`). Portfolio page
  is still the one outlier (~4.5s vs ~1.1s elsewhere) — traced to real one-time bot-engine
  import work (`_liquid_scan_universe`, `_keyvault_key`), not a bug; low priority, don't
  chase further without a specific reason.
- **Row 45 (next up): user also wants CODE changes (not just trade data)
  auto-reflected on both hosts** — "when i update one code that should be reflected in both".
  Distinct problem from row 41. `tools/deploy_cloud.py`/`sync_cloud.py` already do this, but
  only as a manual command someone has to remember to run — which is exactly how cloud row 31
  happened (VM sat 12 commits behind, unnoticed). Needs the user's call: auto-deploy on every
  git commit (safer — only deploys finished work) vs. on every save (risk: deploys mid-edit,
  breaks a live 24/7 bot) vs. keep it manual but add a drift check (VM HEAD vs local HEAD) to
  the desktop launcher's status board. Ask before building either way.
- Also open, smaller: cloud row 36 (bot sends empty chart PNGs, `BadRequest: File must be
  non-empty` from `signal_ticker_detail`), row 20 (idle-CPU research question, no action
  needed unless asked), row 3 (Oracle budget alarm `limit_use` is Custom not Monthly — the
  idle tripwire silently expires after one period, unrelated to anything above).

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

## In flight — actually, mostly done; check before resuming

`build_gex_history.py` is NOT currently running on the VM (checked 2026-09-04: `pgrep` found a
stale PID, but `ps` on that PID showed nothing — process is dead). `gex_history` already holds
**30,122 rows**, past the original ~29,300 estimate, so the bulk of the build completed in an
earlier pass. `~/gex_build.log` ends in `sqlite3.OperationalError: database is locked` — from a
LATER resume/rebuild attempt, likely colliding with this session's own sync writes
(`sync_trades.py`, the sqlite_sequence bump), not the original run failing. Before assuming
more work is needed: check `SELECT COUNT(DISTINCT trade_date) FROM gex_history` against
capture dates and only re-run for a genuine gap, not a full rebuild.

Purpose once confirmed complete: `gamma_wall_trades` is empty, so the gamma-wall and
zero-gamma claims have never been scored. Join to forward returns via `daily_ic` — and if a
"near the wall" threshold ever gets tuned, that must go through `walkforward.py`, not be fitted
on the judging data.

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
