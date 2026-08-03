# RUNBOOK — run it, rebuild it, recover it

> Tracker ID 89. Two jobs: (1) run each surface on its own, (2) rebuild this system from
> nothing. The second half is also the disaster-recovery procedure — the only one there is.

---

## 1. Run each surface independently

They already are independent. The bot does **not** launch the dashboard at startup:
`ensure_streamlit_running()` is only called when you tap the terminal button, and it is a
no-op if the port is already up. (CLAUDE.md previously implied otherwise.)

```bash
# Telegram bot only            — token read from token.txt
python telegram_bot_optimized.py

# Streamlit only               — imports the bot as a LIBRARY, does not need the bot process
streamlit run dashboard.py --server.port 8502

# EOD pipeline only            — NY-gated; exits immediately if already run for the target day
python run_all_offhours.py

# Intraday lane only           — normally auto-spawned by the bot's supervisor
python NYSE_intraday.py
```

**Restarting the bot** (Windows, PowerShell) — it does not reload edited files, so every
code change needs this:

```powershell
$b = Get-CimInstance Win32_Process -Filter "Name='python3.13.exe'" |
     Where-Object { $_.CommandLine -like '*telegram_bot_optimized*' }
if ($b) { Stop-Process -Id $b.ProcessId -Force; Start-Sleep 4 }
Start-Process python -ArgumentList "telegram_bot_optimized.py" `
  -WorkingDirectory "C:\Users\srini\Options_chain_data\NYSE_DATA" -WindowStyle Hidden
```

Confirm it came up: `tail -5 telegram_bot.log` should end with `Bot is running!` and
`Registered N slash commands`.

Streamlit **does** hot-reload on file save. Only the bot needs a restart.

---

## 2. What is NOT in git — read before cloning

A fresh clone **will not run**. Everything expensive is deliberately gitignored:

| Needed | In git? | How to get it back |
|---|---|---|
| Code | ✅ | `git clone` |
| `token.txt` (bot token) | ❌ | BotFather → `/mybots` → API Token |
| `api_keys.enc` | ❌ | **Machine-bound — cannot be copied.** Recreate, see §3.4 |
| `US_data_OpenBB.db` (~2.9 GB) | ❌ | Google Drive backup |
| `openbb_chains/*.parquet` | ❌ | Google Drive backup |
| `US_intraday.db` | ❌ | Rebuilds itself from the intraday lane |
| `logs/` | ❌ | Regenerates |

`api_keys.enc` is encrypted **and bound to the machine that wrote it**. Copying it to
another PC gives you a file that will not decrypt. This is by design.

---

## 3. Bootstrap on a new machine

### 3.1 Code
```bash
git clone https://github.com/somu-analyst/WallStreet_Agentic_TradeOps.git
cd WallStreet_Agentic_TradeOps
```

### 3.2 Python
Python **3.13** (3.12+ required — the code uses `datetime.now(timezone.utc)` idioms and
`zoneinfo`).
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install -r requirements_openbb.txt      # only for the OpenBB capture lane
```

### 3.3 Restore the data
```
G:\My Drive\NYSE_backup\US_data_OpenBB.db   ->  C:\Users\srini\Options_chain_data\
G:\My Drive\NYSE_backup\openbb_chains\      ->  C:\Users\srini\Options_chain_data\openbb_chains\
```
Verify before trusting it:
```bash
python -c "import sqlite3;c=sqlite3.connect(r'C:\Users\srini\Options_chain_data\US_data_OpenBB.db');print(c.execute('SELECT COUNT(*),MAX(trade_date) FROM options_openbb').fetchone())"
```

If the DB is gone but the parquets survived, the chains can be reloaded from them — that
is the whole reason they exist. `stock_history` re-downloads free from Yahoo; **option
bid/ask and open interest cannot be re-obtained at any price**, which is why those files
are the irreplaceable part.

### 3.4 Secrets
```
token.txt          one line: the BotFather token
api_keys.env       NAME=value per line (ANTHROPIC_API_KEY, FINNHUB_API_KEY,
                   ALPHAVANTAGE_KEY, optionally FRED_API_KEY)
```
On first run `_load_api_keys()` merges `api_keys.env`, re-encrypts to `api_keys.enc`, and
**deletes the plaintext**. `api_keys.env` being absent afterwards is normal, not a fault.

### 3.5 Scheduled tasks (Windows Task Scheduler)
| Task | Schedule | Does |
|---|---|---|
| EOD pipeline | hourly, NY-gated | `run_all_offhours.py` — exits if already run |
| `NYSE_OffsiteBackup` | Sun 12:00, catch-up | `backup_offsite.bat` → Google Drive |
| `ClaudeResume` | ad-hoc | `resume_after_limit.ps1` |

### 3.6 First run
```bash
python telegram_bot_optimized.py         # expect: Bot is running! / Registered N commands
streamlit run dashboard.py --server.port 8502
```

---

## 4. Health checks

```bash
python tools/show_pending.py             # open work, read from the tracker
```
In Telegram: `/data` (VALIDATED / PARTIAL / FAILED for the last capture) and `/status`.

Capture forensics live in the **data** folder, not the repo:
```
C:\Users\srini\Options_chain_data\openbb_fetch_YYYYMMDD.log
```
The scheduler log (`NYSE_DATA\logs\scheduler_*.log`) only records whether a job *launched*.
`openbb_fetch_*.log` records what it actually did.

---

## 5. Backups

`backup_offsite.bat` robocopies to `G:\My Drive\NYSE_backup` weekly:
- `openbb_chains\*.parquet` — the irreplaceable option chains
- `US_data_OpenBB.db` — newer-only

Verified 2026-08-03: 21 parquets + the 3.0 GB DB present on the drive.

**The known weakness:** both copies live on the same machine until Drive syncs, and only
one non-local copy exists. A second offsite target would be the next improvement.

---

## 6. Gotchas that will bite

- **Console output must be ASCII.** Windows cp1252 crashes on `✔ σ – ≈`. Use
  `.encode("ascii","replace")` in any script that prints model output.
- **The bot does not reload edited files.** Restart it (§1).
- **Streamlit renders tables to a canvas.** Column headers are NOT in `document.body`
  innerText — read `[role=columnheader]` instead. A check that greps body text will
  produce false "column missing" results.
- **`_hiprob_scan_asof` measures DTE from its as-of date on purpose.** It replays history;
  do not "fix" it to use today like the live paths.
- **LIVE and BACKFILL recommendations must never be pooled** — that would report hindsight
  as performance.
- **yfinance option chains can be a full session stale**, with `bid=ask=0` on nearly every
  contract well after the open. Prefer `options_openbb` marks and show quote age.
