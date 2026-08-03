# -*- coding: utf-8 -*-
"""Walk-forward validation harness (tracker ID 8).

Backtests here have been ad-hoc: a signal is scored once over all available history, and
any parameter that got tuned was tuned on the same data it was then judged on. That is
in-sample fitting, and it is the second way this project has manufactured edge (the first
was the pooled rank-IC t-stat, banned 2026-07-31 -- see .claude/rules/bot-conventions.md).

This module is the standard. Anything that CHOOSES a parameter must go through
`walk_forward`; anything that merely scores a fixed signal can use `daily_ic` directly.

The convention
--------------
* EXPANDING window. Fold k trains on everything up to date d_k and tests on (d_k, d_k+h].
  Never trains on anything after its test window -- no lookahead, ever.
* The parameter is refit INSIDE each fold, on train only. Reporting a single parameter
  chosen over all history and then "walking it forward" is still in-sample.
* Test-fold ICs are de-overlapped by the forward horizon before any t-test, because
  fwd-h returns sampled daily share h-1 days with their neighbour.
* Judgement is on the pooled TEST folds only. Train scores are printed for comparison --
  a large train/test gap IS the overfitting signal and is worth seeing.

Usage
-----
    from walkforward import walk_forward, daily_ic, sanity_gate

    def fit(train_px):            # -> any parameter object, chosen on TRAIN only
        ...
    def signal(px, param):        # -> DataFrame (dates x tickers) aligned to px
        ...
    print(walk_forward(px, fit, signal, horizon=5))

Run directly for a self-test on the real DB:  python tools/walkforward.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------- core measurement
def daily_ic(sig: pd.DataFrame, fwd: pd.DataFrame, step: int, min_names: int = 15):
    """One cross-sectional IC per date, de-overlapped by `step`, then a t-test.

    Returns dict(ic, t, p, n) or None when there are too few independent dates. NEVER
    pool (ticker, date) pairs into one correlation -- that is the banned method.
    """
    ics = []
    for d in sig.index[::step]:
        if d not in fwd.index:
            continue
        a, f = sig.loc[d], fwd.loc[d]
        m = a.notna() & f.notna()
        if m.sum() < min_names:
            continue
        ic, _ = stats.spearmanr(a[m], f[m])
        if ic == ic:
            ics.append(ic)
    if len(ics) < 4:
        return None
    a = np.array(ics)
    t = stats.ttest_1samp(a, 0)
    return {"ic": float(a.mean()), "t": float(t.statistic), "p": float(t.pvalue), "n": len(a)}


def fwd_returns(px: pd.DataFrame, horizon: int, excess_vs: str | None = None):
    """Forward simple returns; optionally excess vs a benchmark column already in `px`."""
    f = px.shift(-horizon) / px - 1
    if excess_vs and excess_vs in px.columns:
        b = px[excess_vs]
        f = f.sub(b.shift(-horizon) / b - 1, axis=0)
    return f


# ---------------------------------------------------------------- walk-forward driver
def walk_forward(px: pd.DataFrame, fit, signal, horizon: int = 5, n_folds: int = 5,
                 min_train: int = 252, excess_vs: str | None = None, verbose: bool = True):
    """Expanding-window walk-forward. `fit(train_px) -> param`; `signal(px, param) -> frame`.

    Returns dict with per-fold rows and the pooled TEST verdict. Judge on `test`.
    """
    px = px.sort_index()
    n = len(px)
    if n < min_train + n_folds * horizon * 4:
        raise ValueError(f"not enough history: {n} rows for {n_folds} folds")

    # fold boundaries carved out of the post-min_train span
    edges = np.linspace(min_train, n - horizon, n_folds + 1).astype(int)
    rows, test_ics, train_ics = [], [], []

    for k in range(n_folds):
        tr_end, te_end = edges[k], edges[k + 1]
        if te_end - tr_end < horizon * 4:
            continue
        train_px = px.iloc[:tr_end]
        param = fit(train_px)                       # <-- fit sees TRAIN ONLY

        sig_all = signal(px, param)
        fwd_all = fwd_returns(px, horizon, excess_vs)

        # train window must stop `horizon` short, or its last labels peek into test
        tr = daily_ic(sig_all.iloc[:max(tr_end - horizon, 0)],
                      fwd_all.iloc[:max(tr_end - horizon, 0)], step=horizon)
        te = daily_ic(sig_all.iloc[tr_end:te_end], fwd_all.iloc[tr_end:te_end], step=horizon)
        if te is None:
            continue
        rows.append({"fold": k + 1,
                     "train_to": str(px.index[tr_end - 1])[:10],
                     "test_to": str(px.index[te_end - 1])[:10],
                     "param": param if np.isscalar(param) else "obj",
                     "train_ic": None if tr is None else round(tr["ic"], 4),
                     "test_ic": round(te["ic"], 4), "test_t": round(te["t"], 2),
                     "test_n": te["n"]})
        test_ics.append(te["ic"])
        if tr is not None:
            train_ics.append(tr["ic"])

    if not rows:
        return {"folds": [], "test": None, "verdict": "NOT TESTABLE - no usable folds"}

    a = np.array(test_ics)
    tt = stats.ttest_1samp(a, 0) if len(a) >= 3 else None
    out = {
        "folds": rows,
        "test": {"mean_ic": float(a.mean()), "n_folds": len(a),
                 "t": None if tt is None else float(tt.statistic),
                 "p": None if tt is None else float(tt.pvalue)},
        "train_mean_ic": float(np.mean(train_ics)) if train_ics else None,
    }
    gap = (out["train_mean_ic"] - a.mean()) if train_ics else None
    out["train_test_gap"] = None if gap is None else float(gap)
    p = out["test"]["p"]
    out["verdict"] = ("NOT TESTABLE" if p is None else
                      ("SURVIVES walk-forward" if p < 0.05 else "does NOT survive"))
    if verbose:
        print(pd.DataFrame(rows).to_string(index=False))
        print(f"\n  pooled TEST : mean IC {a.mean():+.4f} over {len(a)} folds"
              + ("" if tt is None else f"  t={tt.statistic:+.2f}  p={tt.pvalue:.3f}"))
        if gap is not None:
            print(f"  train mean IC {out['train_mean_ic']:+.4f}  ->  train-test gap {gap:+.4f}"
                  "   (a large positive gap IS overfitting)")
        print(f"  VERDICT: {out['verdict']}")
    return out


# ---------------------------------------------------------------- mandatory sanity gate
def sanity_gate(px: pd.DataFrame, horizon: int = 5, n: int = 200, seed: int = 0,
                excess_vs: str | None = None):
    """Push random signals through `daily_ic`. >~5% passing means the HARNESS is broken.

    Required before trusting any new harness (bot-conventions.md). Measured 2026-08-02 on
    this DB: 3.0% of 300 random signals passed -- correct.
    """
    rng = np.random.default_rng(seed)
    fwd = fwd_returns(px, horizon, excess_vs)
    hits = tot = 0
    for _ in range(n):
        r = pd.DataFrame(rng.standard_normal(px.shape), index=px.index,
                         columns=px.columns).rolling(int(rng.integers(3, 40))).mean()
        d = daily_ic(r, fwd, step=horizon)
        if d:
            tot += 1; hits += d["p"] < 0.05
    rate = hits / max(tot, 1)
    return {"pass_rate": rate, "n": tot,
            "ok": rate <= 0.10,
            "note": "expect ~0.05; >0.10 means the harness manufactures significance"}


# ---------------------------------------------------------------- self-test
if __name__ == "__main__":
    import sqlite3, sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import telegram_bot_optimized as bot

    conn = bot.get_conn()
    tks = [r[0] for r in conn.execute(
        "SELECT ticker FROM stock_history GROUP BY ticker HAVING COUNT(*)>=1200 "
        "ORDER BY COUNT(*) DESC LIMIT 120").fetchall()]
    px = bot._history_matrix(tks, years=6, conn=conn)
    conn.close()
    px = px.tail(1400)
    px = px.dropna(axis=1, thresh=int(len(px) * 0.95)).ffill().bfill()
    print(f"self-test panel: {px.shape[1]} tickers x {len(px)} days\n")

    g = sanity_gate(px, horizon=5, n=120)
    print(f"SANITY GATE: {g['pass_rate']*100:.1f}% of {g['n']} random signals passed "
          f"(expect ~5%)  -> {'OK' if g['ok'] else 'HARNESS BROKEN'}\n")

    # Example: momentum lookback CHOSEN on train only. This is exactly the kind of
    # parameter that used to be picked over all history and then reported as validated.
    def fit(train_px):
        best, best_ic = 21, -9.9
        f = fwd_returns(train_px, 5)
        for lb in (10, 21, 42, 63, 126):
            s = train_px / train_px.shift(lb) - 1
            d = daily_ic(s, f, step=5)
            if d and d["ic"] > best_ic:
                best, best_ic = lb, d["ic"]
        return best

    print("WALK-FORWARD: cross-sectional momentum, lookback refit on each train fold")
    walk_forward(px, fit, lambda p, lb: p / p.shift(lb) - 1, horizon=5, n_folds=5)
