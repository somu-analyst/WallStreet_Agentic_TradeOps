# NEXT — switch-over note (2026-07-15, late)
1. User: restart bot + Streamlit; add real positions: GOOG 100sh @180 entry 2025-06-24
   (Type=STOCK) + GOOGL put-spread legs so /tax sees the Pub 550 reset (LT = 2027-07-26).
2. User: start the NEW intraday lane at the open — `python NYSE_intraday.py` (loops market
   hours, exits after close). Bot then answers /live and /heat and pushes 🔥/🌀 state changes.
3. Next build: NSE India lane (endpoints verified in PLAN §2) — the last big queued item.
   Smaller: launcher/scheduler for NYSE_intraday.py; bot stock-position display.
4. Everything committed; only run_bot.bat untracked (user's launcher).
