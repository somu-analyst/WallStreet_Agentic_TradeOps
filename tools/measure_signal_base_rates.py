# -*- coding: utf-8 -*-
"""Measure the base rate of every ensemble model in `signal_accuracy` (ID 243).

WHY THIS EXISTS
    `_signal_writeup()` (the house signal template, ID 241) refuses to print a base rate it
    has not been given -- it renders "Not measured here" instead. Converting a signal's
    writeup therefore means MEASURING it first. This is that measurement, kept as a tool so
    it can be re-run as the sample accrues rather than redone from scratch each time.

THE THREE WAYS THIS ANALYSIS GOES WRONG (all three were hit while writing it)
  1. WRONG BASELINE. `_score_signal` grades with a dead zone and by call type:
         BULL          correct if ret > +0.003
         BEAR          correct if ret < -0.003
         SELL_PREMIUM  correct if |ret| < 0.012   <- a VOLATILITY call, not a direction
     Comparing all three against "the up-rate" makes BEAR and SELL_PREMIUM look broken. The
     first run of this analysis reported 8 INVERSE models and 0 edges; with baselines matched
     to the grading rule the same data gives 0 inverse and 3 nominal edges. Same numbers,
     opposite conclusion.
  2. POOLED t-STAT. Banned repo-wide (.claude/rules/bot-conventions.md): 700+ tickers on one
     day are nowhere near 700 independent draws, and a pooled t inflates ~10x. Significance
     here is computed on DAILY differences (model hit-rate that day minus the baseline
     hit-rate on that SAME day), so n = days.
  3. MULTIPLICITY + CORRELATION. ~21 model x call combos are tested at once, so ~0.5 hits at
     p<0.05 are expected from noise alone. And the models are not independent: the three
     SELL_PREMIUM models overlap on 63-91% of their (date, ticker) fires because they all
     fire on the same quiet days. Three nominal hits can be one finding counted three times.

READING THE OUTPUT
    A model is only worth writing up as MEASURED if it clears the Bonferroni column, not the
    nominal one. Anything else stays "not measured" -- which is a real answer, not a failure.

Usage:  python tools/measure_signal_base_rates.py [--db PATH]
"""
import argparse
import io
import math
import os
import sqlite3
import sys
from collections import defaultdict

# Thresholds are IMPORTED from the engine, never copied. They were hardcoded here with a
# comment saying "must mirror _score_signal" -- which is a promise a comment cannot keep. If
# the engine's dead zone ever changed, this tool would have kept grading against the old one
# and reported confident verdicts computed from the wrong rule, with nothing failing loudly.
def _engine_thresholds():
    import inspect, os, re, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import telegram_bot_optimized as _B
        sig = inspect.signature(_B._score_signal)
        return (float(sig.parameters["dead"].default),
                float(sig.parameters["band"].default))
    except Exception:
        # Importing the 43k-line engine can fail in a bare analysis environment. Fall back to
        # READING the defaults out of the source rather than to a copied literal.
        try:
            src = io.open(os.path.join(root, "telegram_bot_optimized.py"),
                          encoding="utf-8").read()
            m = re.search(r"def _score_signal\([^)]*dead=([\d.]+),\s*band=([\d.]+)", src)
            if m:
                return float(m.group(1)), float(m.group(2))
        except Exception:
            pass
        raise SystemExit("cannot read the grading thresholds from the engine — refusing to "
                         "measure against guessed values")


DEAD, BAND = _engine_thresholds()
MIN_ROWS, MIN_DAYS = 100, 8


def _hit(sig, ret):
    if sig == "BULL":
        return ret > DEAD
    if sig == "BEAR":
        return ret < -DEAD
    if sig in ("SELL_PREMIUM", "NEUTRAL"):
        return abs(ret) < BAND
    return None


def measure(db):
    conn = sqlite3.connect(db)
    rows = list(conn.execute(
        "SELECT model_name, signal, trade_date, ticker, actual_ret, correct FROM signal_accuracy"
        " WHERE actual_ret IS NOT NULL AND correct IS NOT NULL"))
    conn.close()
    if not rows:
        print("no graded fires yet")
        return []
    dates = sorted({r[2] for r in rows})
    print(f"{len(rows):,} graded fires · {len(dates)} dates ({dates[0]} -> {dates[-1]})\n")

    # Baseline per call type, per DAY -- what an always-on call of that type scores.
    day_base = defaultdict(lambda: defaultdict(list))
    for _m, _s, d, _tk, ret, _c in rows:
        for k in ("BULL", "BEAR", "SELL_PREMIUM"):
            day_base[k][d].append(1 if _hit(k, ret) else 0)
    overall = {k: sum(sum(v) for v in dd.values()) / sum(len(v) for v in dd.values())
               for k, dd in day_base.items()}
    print("baselines (an always-on call of that type):")
    for k, v in overall.items():
        print(f"   {k:<13} {v * 100:5.1f}%")

    by = defaultdict(lambda: defaultdict(list))
    fires = defaultdict(set)
    for m, s, d, tk, ret, corr in rows:
        by[(m, s)][d].append(corr)
        fires[(m, s)].add((d, tk))

    out = []
    for (m, s), per_day in by.items():
        if s not in overall:
            continue
        n_obs = sum(len(v) for v in per_day.values())
        diffs = [sum(v) / len(v) - sum(day_base[s][d]) / len(day_base[s][d])
                 for d, v in per_day.items() if v and day_base[s].get(d)]
        if n_obs < MIN_ROWS or len(diffs) < MIN_DAYS:
            continue
        mu = sum(diffs) / len(diffs)
        var = sum((x - mu) ** 2 for x in diffs) / (len(diffs) - 1)
        se = math.sqrt(var / len(diffs)) if var > 0 else 0.0
        t = (mu / se) if se else 0.0
        hit = sum(sum(v) for v in per_day.values()) / n_obs
        out.append(dict(model=m, call=s, n=n_obs, days=len(diffs), hit=hit,
                        base=overall[s], edge=mu, t=t))

    n_tests = len(out)
    # two-sided Bonferroni-corrected critical t, normal approx
    crit = 0.0
    if n_tests:
        p = 0.05 / n_tests
        x = 1 - p / 2
        # inverse normal (Acklam-lite): good enough for a threshold display
        crit = math.sqrt(2) * _erfinv(2 * x - 1)
    print(f"\n{'model':<16}{'call':<13}{'n':>7}{'hit%':>8}{'base%':>7}{'edge':>8}"
          f"{'days':>6}{'t':>7}  verdict")
    print("-" * 92)
    for o in sorted(out, key=lambda z: -z["t"]):
        v = "MEASURED" if o["t"] >= crit else ("nominal only" if o["t"] > 2 else "not measured")
        print(f"{o['model']:<16}{o['call']:<13}{o['n']:>7,}{o['hit']*100:>7.1f}%"
              f"{o['base']*100:>6.1f}%{o['edge']*100:>+7.1f}{o['days']:>6}{o['t']:>7.2f}  {v}")
    passed = [o for o in out if o["t"] >= crit]
    nominal = [o for o in out if 2 < o["t"] < crit]
    print(f"\n{n_tests} tests · Bonferroni critical t = {crit:.2f} (p<{0.05/max(n_tests,1):.4f})")
    print(f"MEASURED (safe to write up): {len(passed) or 'NONE'}")
    if nominal:
        print(f"nominal-only (do NOT write up as measured): "
              f"{', '.join(o['model'] + '/' + o['call'] for o in nominal)}")
        # correlation check: nominal hits firing on the same names/days are ONE finding
        keys = [(o["model"], o["call"]) for o in nominal]
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = fires[keys[i]], fires[keys[j]]
                if a and b:
                    ov = len(a & b) / min(len(a), len(b)) * 100
                    if ov > 40:
                        print(f"   overlap {keys[i][0]} vs {keys[j][0]}: {ov:.0f}% of fires "
                              f"-> likely the SAME finding, not two")
    return out, by, day_base


def _regimes(db, dates):
    """Label each date with a market regime. {date: {axis: label}}.

    THE IDEA, BORROWED FROM ATLAS: a real edge shows up independently in more than one market
    regime. An artifact of fitting shows up in exactly one and vanishes elsewhere. That is a
    CONSISTENCY check, not a significance test -- splitting an already-thin sample makes each
    cohort thinner, so it can raise doubt but never confer confidence. Anything that survives
    still has to clear the Bonferroni bar on the full sample.

    Two axes, both from data already captured:
      volatility  VIX above / below its own median over the window
      trend       SPY above / below its 20-day mean
    """
    out = {d: {} for d in dates}
    try:
        conn = sqlite3.connect(db)
        vix = {d: v for d, v in conn.execute(
            "SELECT trade_date, close FROM stock_daily WHERE ticker='^VIX' "
            "AND close IS NOT NULL")}
        spy = sorted(conn.execute(
            "SELECT trade_date, close FROM stock_daily WHERE ticker='SPY' "
            "AND close IS NOT NULL ORDER BY trade_date"))
        conn.close()
    except Exception:
        return out

    have = [vix[d] for d in dates if d in vix]
    if have:
        med = sorted(have)[len(have) // 2]
        for d in dates:
            if d in vix:
                out[d]["vol"] = "high-vol" if vix[d] >= med else "low-vol"

    closes = {d: c for d, c in spy}
    order = [d for d, _ in spy]
    for d in dates:
        if d not in closes:
            continue
        i = order.index(d)
        if i >= 20:
            mean20 = sum(closes[x] for x in order[i - 20:i]) / 20
            out[d]["trend"] = "uptrend" if closes[d] >= mean20 else "downtrend"
    return out


def cohorts(db, out, by, day_base):
    """Per-regime edge for every model, and whether the sign holds across cohorts."""
    dates = sorted({d for per in by.values() for d in per})
    reg = _regimes(db, dates)
    axes = {}
    for d, lab in reg.items():
        for axis, name in lab.items():
            axes.setdefault(axis, {}).setdefault(name, set()).add(d)
    if not axes:
        print("\nno regime data available — skipping cohort check")
        return

    print("\n" + "=" * 92)
    print("REGIME COHORTS — does the edge survive in more than one market?")
    print("=" * 92)
    for axis, groups in axes.items():
        print(f"\n{axis.upper()}: " + " · ".join(f"{k} ({len(v)}d)" for k, v in groups.items()))

    names = sorted({n for g in axes.values() for n in g})
    print(f"\n{'model':<16}{'call':<13}" + "".join(f"{n:>12}" for n in names) + "   verdict")
    print("-" * (29 + 12 * len(names) + 12))
    consistent = []
    for o in sorted(out, key=lambda z: -z["t"]):
        per_day = by[(o["model"], o["call"])]
        cells, signs = [], []
        for n in names:
            ds = next((g[n] for g in axes.values() if n in g), set())
            diffs = [sum(v) / len(v) - sum(day_base[o["call"]][d]) / len(day_base[o["call"]][d])
                     for d, v in per_day.items()
                     if d in ds and v and day_base[o["call"]].get(d)]
            if len(diffs) < 4:
                cells.append(f"{'thin':>12}"); signs.append(None); continue
            m = sum(diffs) / len(diffs) * 100
            cells.append(f"{m:>+11.1f}%"); signs.append(m > 0)
        known = [x for x in signs if x is not None]
        if len(known) >= 2 and all(known):
            verdict = "consistent +"
            consistent.append(o)
        elif len(known) >= 2 and not any(known):
            verdict = "consistent -"
        elif known:
            verdict = "FLIPS"
        else:
            verdict = "too thin"
        print(f"{o['model']:<16}{o['call']:<13}" + "".join(cells) + f"   {verdict}")

    print(f"\npositive in EVERY regime tested: {len(consistent) or 'NONE'}")
    for o in consistent:
        print(f"   {o['model']}/{o['call']}  (full-sample t={o['t']:.2f})")
    print("\nA sign that FLIPS between regimes is the tell: the same rule cannot be an edge in")
    print("one market and a liability in another unless it was fitted to whichever came first.")
    print("Consistency is necessary, NOT sufficient — the Bonferroni column above still rules.")


def _erfinv(y):
    """Small inverse error function (Winitzki), enough for a critical-value display."""
    a = 0.147
    ln = math.log(1 - y * y) if abs(y) < 1 else -30.0
    term = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(max(math.sqrt(term * term - ln / a) - term, 0.0)), y)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohorts", action="store_true",
                    help="also split by market regime (ATLAS-style convergence check)")
    ap.add_argument("--db", default=os.environ.get(
        "NYSE_DB_PATH", r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db"))
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    res = measure(a.db)
    if a.cohorts and res:
        cohorts(a.db, *res)
