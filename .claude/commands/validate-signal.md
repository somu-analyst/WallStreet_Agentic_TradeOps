---
description: Backtest a signal vs US_data.db history; report hit-rate vs baseline
argument-hint: [ticker] (default SPY)
allowed-tools: Bash(python -m core.validate*)
---
Backtest the mean-reversion signal using the parallel `core/` system (read-only, never the bot).

Ticker: use `$ARGUMENTS` if provided, otherwise `SPY`.

1. Run `cd archive && python -m core.validate --ticker <TICKER>` (the `core/` package lives under `archive/`).
2. Present the output as a compact table: ticker · days · fires · hit% · avg fwd · baseline · edge.
3. Flag low sample counts and do NOT overstate the edge — thin N means weak evidence.

For a cross-sectional, Alphalens-style view (rank IC + quantile forward-return spread over the
whole universe, not one ticker), use the bot's **`/ic`** command / `_ic_analyze(conn, factor)` in
`telegram_bot_optimized.py` (factors: reversal, momentum, lowvol). It reports mean IC, IC-IR,
t-stat, IC-hit%, N, and Q5−Q1 spread per horizon. |t|≥2 is the bar; ~6mo history = low power.
