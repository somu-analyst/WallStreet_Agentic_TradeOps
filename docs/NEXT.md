# NEXT — switch-over note (2026-07-15, late)
1. User: restart bot + Streamlit; add real positions: GOOG 100sh @180 entry 2025-06-24
   (Type=STOCK) + GOOGL put-spread legs so /tax sees the Pub 550 reset (LT = 2027-07-26).
2. Intraday lane is SELF-STARTING: the bot auto-spawns NYSE_intraday.py during market hours
   (heartbeat-supervised, log: logs/intraday_lane.log). Nothing to launch — just restart the
   bot once. /live and /heat + 🔥/🌀 state-change pushes then work all session.
3. Next build: NSE India lane (endpoints verified in PLAN §2) — the last big queued item.
   Smaller: bot stock-position display.
4. Everything committed; only run_bot.bat untracked (user's launcher).
