# Telegram and dashboard parity

Standing rule from the user (2026-10-05): "whatever we do, we need both Telegram and dashboard,
include in md file."

## The rule

Every feature, report, table, alert, or number that the user can see goes to BOTH surfaces:

- **Telegram:** the bot (`telegram_bot_optimized.py`), as a command or a scheduled push.
- **Dashboard:** the Streamlit app (`dashboard.py`), as a page section or a table.

Ship neither half alone. If one surface is not yet built, say so in the tracker row and in the
reply, and add the missing half as its own tracked item.

## Same numbers on both

- Both surfaces read the same engine function or the same table. Never re-derive a number
  differently on one surface (CLAUDE.md: never copy engine logic into a second place).
- Settled and realized figures must match exactly. Verify by comparing the two outputs for the
  same data before calling a feature done.
- The dashboard imports the bot at runtime, so shared constants (for example
  `BRIDGE_CAPITAL`) are read from the bot and not typed again.

## Verification

- Telegram: render the function to a UTF-8 file and read it (the Windows console cannot print
  emoji).
- Dashboard: a live headless-browser DOM check with Playwright. `py_compile` and `curl` do not
  count (CLAUDE.md hard rule).

## Closing a change (standing process, user 2026-10-07)

Every change follows this order, every time:

1. **Build it in both surfaces.** Telegram and dashboard, per the table below — never ship
   one half.
2. **Verify both.** Telegram: render to a UTF-8 file and read it. Dashboard: a live
   headless-browser DOM check (CLAUDE.md hard rule) — `py_compile`/`curl` do not count.
3. **Commit and push**, to both `origin` and `backup` (git workflow memory) — right after
   each change, not batched up and pushed later.
4. **Cloud deploy happens automatically.** A git post-commit hook on `main`
   (`.git/hooks/post-commit`, installed 2026-09-04) runs `tools/deploy_cloud.py` in the
   background on every push: compiles, mirrors to the cloud repo, pushes it, pulls on the
   VM, restarts `nyse-bot` + `nyse-dashboard`. Confirmed working 2026-10-07 — three commits
   that day each auto-deployed and restarted cloud services within ~60-80s, verified
   against the VM directly (commit hash and `systemctl is-active` both matched).
   **Check `logs/auto_deploy.log` to confirm a deploy actually happened — don't assume.**
   No manual `deploy_cloud.py` run is needed unless that log shows a failure.

## Where features are listed

Add every new feature to this file's table so the two surfaces can be checked against each
other.

| Feature | Telegram | Dashboard |
|---|---|---|
| Recommendation track record (realized by strategy, bridge view) | `/recperf` | 🎯 High-Prob Options, Recommendation Tracker section |
| Dealer positioning (CFTC) | `/dealer` | 📡 Macro/Event Hub |
| Company money flow (Sankey) | `/sankey TICKER` | 💧 Money Flow (Sankey) |
| Positions and P&L | `/positions`, position monitor push | 💼 Portfolio & Suggestions |
| Gamma exposure walls | `/gex` | 📐 GEX Command |
| Paper trading | paper book commands | 📝 Paper Trading |
| Watchlist | `/watchlist` | 👀 Watchlist |

Keep this table current. Anything that exists on only one surface is listed with "not yet".
