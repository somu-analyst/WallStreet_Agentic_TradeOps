# NEXT — switch-over note (2026-07-18, early AM)

1. **Committed 3622277**: scheduler = OpenBB `--full` one-shot + catch-up gate (runs for the
   missed day whenever the laptop opens: pre-market window targets last trading day; state-file
   dedup). NYSE_Telegram retired from scheduler. 07-17 recovered end-to-end (734 tickers,
   derive+stock+skew all landed; audit flips VALIDATED on next /data or dashboard refresh).
2. **New**: `/data` (alias `/status`) on-demand data audit · dashboard header live-audit
   (30s cache) · Telegram "/" menu pushed (55 cmds) · `restart_bot.bat` (kill bot+dash, relaunch).
3. **Format QA DONE**: 37 commands rendered via fake-Telegram harness vs live DB; 5 violations
   found+fixed (opex dates, uoa 99+ cap, gex stray ZWJ, macro AV table, hiprob header). Harness
   pattern: session scratchpad `render_harness*.py` (FakeUpdate/FakeContext, 240s timeouts).
4. **USER action pending**: run `restart_bot.bat` (bot still on pre-fix code for /data, ticker-tap
   grids, opex/uoa/gex/macro/hiprob) · BotFather `/setinline` · weekly offsite parquet copy.
5. **Claude next tasks (in order)**: BB capture resumability (halt/shutdown mid-fetch → resume
   from per-chunk checkpoint instead of refetching 734 tickers) · /live /heat format QA at next
   market open · /ratings broker-name abbreviations (optional cosmetic).
6. **Queue (user-gated, PLAN.md)**: Portfolio track MCP+RAG+Docker/k8s (#31 — job-hunt showcase,
   biggest item) · NSE India lane · BS next-day model parts → dashboard · heat/fade + skew25
   backtest reruns (~2wk data gates) · Mini App phase 2 (parked).
7. Positions/tax live in DB (`trades`, `app_settings`) — NEXT.md no longer mirrors them.
