# DECISIONS — backtest results & why we decided what we decided

> Permanent record (user ask 2026-07-17). Every backtest/validation gets an entry here:
> date, method, numbers, verdict, and the decision taken. Machine-readable copies live in
> the DB (`backtest_summary`, `signal_accuracy`); this file is the human "why".
> Rule for future work: no signal ships or dies without an entry here.

## 2026-07-14 — Black-Scholes next-day model ("Est Open" etc.)
- **Data**: 1.2M contract-days from our own capture, time-split (no lookahead).
- **Result**: "Est Open" (BS-predicted next-day option open) could **NOT beat naive**
  carry-forward of last price → prediction column is noise.
- **What DID validate**: scenario pricing "stock hits X → leg ≈ $Y" on liquid 22–45 DTE
  contracts: median error close 5.3% / high 3.6% / low 5.2%. Day Low–High band: 72% ≈ 1σ
  (well calibrated).
- **Decision**: kill/relabel Est Open; keep scenario outputs. Recipe locked: mid-quote IV
  anchor + liquidity gate (vol≥100, spread≤8%, grey-out others) + no GBM (overfit).
- Scripts: session scratchpad `bs_validate/bs_tune/bs_liquid.py`.

## 2026-07-14 — OpenBB vs Yahoo parity (cutover gate)
- 6/6 overlapping days PASS: OI corr 1.000/0.999, lastPrice 0.995–0.998; BB captured
  07-09 which Yahoo missed; 734 vs 88 tickers coverage.
- **Decision**: cut over PRIMARY DB to `US_data_OpenBB.db`; Yahoo = fallback-only
  (2026-07-16: fallback now gated on `bb_capture_ok`, not run daily).

## 2026-07-16 — Scanner direction backtests (t+5 signed fwd, ~7 mo history)
| Signal | N | Hit% | vs base | Avg fwd | Verdict |
|--------|-----|------|---------|---------|---------|
| revert (5d reversal z) | 362 | 54% | 49% | +2.69% | **VALIDATED** — the one real edge |
| uoa direction | 434 | 46% | 49% | −0.35% | **FAILED** — flow ≠ direction |
| building (OI-build dir) | 1108 | 47% | 49% | −1.47% | **FAILED/ANTI** — descriptive only |
- **Decision**: `/revert` tradeable; `/uoa` & `/building` kept as *context* commands, never
  directional advice. Persisted in `backtest_summary`. Fires were never persisted
  historically → signals were RECOMPUTED per historical day (honest, no survivorship).

## 2026-07-16 — Heat/fade intraday states (first read)
- N=6 HEAT / 5 FADE from only 2 days of minute bars — sample useless (FADE 1/5).
- **Decision**: NO verdict; rerun after ~2 weeks of bars accrue. Harness kept
  (`backtests_p2_p3.py` pattern).

## 2026-07-16 — Skew25 panel rank-IC (first read)
- 6 dates, mean daily rank-IC +2.2 (t=0.59) — statistical noise; sign currently OPPOSITE
  the downside hypothesis.
- **Decision**: NO verdict; rerun at 15–20 snapshot dates.

## Earlier (pre-dated this file, recorded from memory/LOG)
- **Market Radar put-flow**: predicts *size* of move, not direction → radar reframed as
  volatility/attention signal.
- **SPY PCR expiry spikes** (11+) are mechanical, not signal → excluded.
- **Mean-reversion composite** (`PCR_z×1.5 − Price_z − NetOI_z ≥ +3 → LONG`, 20d lookback)
  is the validated shape behind /revert.

## 2026-07-17 — Data-health watchdog (operational, not a backtest)
- 07-16 EOD: BB capture succeeded (734 tickers) but machine died mid-Yahoo-fetch under the
  OLD scheduler flow → derive never ran → bot showed stale 07-15 OI.
- **Decision**: (1) BB-primary flow (derive immediately after capture) already shipped
  07-16 removes the 4-hour exposure window; (2) new `data_health_alerts` table + twice-daily
  bot job + flashing dashboard banner + Telegram ack buttons nag until acknowledged;
  (3) logs auto-purge after 7 days (`cleanup_old_logs`).
