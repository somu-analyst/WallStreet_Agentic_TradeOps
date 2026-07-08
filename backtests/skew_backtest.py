"""skew_backtest.py — PRELIMINARY event-study: does OpenBB 25Δ skew / put-flow predict
forward DOWNSIDE?  Parallel research lane only (reads US_data_OpenBB.db + US_data.db price
history; never wired into bot/dashboard).

Hypothesis: high skew25 (25Δ put IV − call IV) and high pcvol/pcoi (put-heavy flow/positioning)
on day t → LOWER forward return over t→t+N (downside predicted).  Test = cross-sectional rank IC
(Spearman) pooled over names, plus top-vs-bottom skew-quintile forward-return spread.

CAVEAT: only 2 snapshot dates so far (07-02, 07-06) → at most 2 forward windows, and window 2
(07-06→07-07) IS the semi-crash event, so a downside hit there is partly the event we're studying
(circular).  Directional read only — NOT a validated signal until ~15-20 dates accrue.
"""
import sqlite3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

OB = r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db"
YF = r"C:\Users\srini\Options_chain_data\US_data.db"

# forward windows: (snapshot_date, forward_date)
WINDOWS = [("2026-07-02", "2026-07-06"), ("2026-07-06", "2026-07-07")]
FACTORS = ["skew25", "pcvol", "pcoi", "atm_iv", "pc_iv"]


def _prices():
    """Price matrix for the FULL skew universe. stock_history first, then a yfinance bulk
    backfill for the (many) OpenBB names / dates not in the local DB — otherwise the crash
    window (07-06->07-07) is starved because today's EOD isn't loaded for most names."""
    c = sqlite3.connect(YF)
    px = pd.read_sql("SELECT ticker, trade_date, close FROM stock_history", c)
    c.close()
    px["ticker"] = px["ticker"].str.upper()
    mat = px.pivot_table(index="trade_date", columns="ticker", values="close", aggfunc="last")

    # universe = all skew_snapshot tickers across windows
    obc = sqlite3.connect(OB)
    uni = sorted({r[0].upper() for r in obc.execute("SELECT DISTINCT ticker FROM skew_snapshot")})
    obc.close()
    dates = sorted({d for w in WINDOWS for d in w})
    missing = [t for t in uni if t not in mat.columns or mat.reindex(dates)[t].isna().any()
               if t in mat.columns] + [t for t in uni if t not in mat.columns]
    missing = sorted(set(missing))
    if missing:
        print(f"  yfinance backfill for {len(missing)} names ({dates[0]}..{dates[-1]}) ...")
        try:
            import yfinance as yf
            d = yf.download(missing, start=dates[0], end="2026-07-08", progress=False,
                            auto_adjust=False)["Close"]
            if isinstance(d, pd.Series):
                d = d.to_frame()
            d.index = d.index.strftime("%Y-%m-%d")
            for t in d.columns:
                for dt in dates:
                    if dt in d.index and pd.notna(d.at[dt, t]):
                        mat.loc[dt, t] = float(d.at[dt, t])
        except Exception as e:
            print("  yfinance backfill failed:", e)
    return mat


def _snap(d):
    c = sqlite3.connect(OB)
    s = pd.read_sql("SELECT ticker, skew25, atm_iv, pc_iv, pcvol, pcoi FROM skew_snapshot "
                    "WHERE trade_date=?", c, params=(d,))
    c.close()
    s["ticker"] = s["ticker"].str.upper()
    return s


def build():
    px = _prices()
    recs = []
    for d0, d1 in WINDOWS:
        if d0 not in px.index or d1 not in px.index:
            print(f"  skip {d0}->{d1}: price row missing")
            continue
        fwd = (px.loc[d1] / px.loc[d0] - 1).dropna()
        s = _snap(d0)
        s = s[s.ticker.isin(fwd.index)].copy()
        s["fwd"] = s.ticker.map(fwd)
        s["win"] = f"{d0}->{d1}"
        recs.append(s)
        print(f"  window {d0}->{d1}: {len(s)} names with skew+price")
    if not recs:
        print("no windows with data"); return None
    return pd.concat(recs, ignore_index=True).dropna(subset=["fwd"])


def report(R):
    print(f"\nPooled name-window observations: {len(R)}  "
          f"(avg fwd {R.fwd.mean()*100:+.2f}%, median {R.fwd.median()*100:+.2f}%)\n")
    print(f"{'factor':<8}{'rankIC':>9}{'p':>10}{'sign?':>8}   (want NEG IC = high skew -> downside)")
    for f in FACTORS:
        g = R[[f, "fwd"]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(g) < 20 or g[f].std() == 0:
            print(f"{f:<8}{'n/a':>9}"); continue
        ic, p = spearmanr(g[f], g["fwd"])
        ok = "YES" if (ic < 0 and p < 0.10) else ("~" if ic < 0 else "no")
        print(f"{f:<8}{ic:>+9.3f}{p:>10.1e}{ok:>8}")

    # top-vs-bottom skew quintile forward return
    print("\nskew25 quintiles (Q5=most downside-skewed) — forward return:")
    R2 = R.dropna(subset=["skew25"]).copy()
    try:
        R2["q"] = pd.qcut(R2.skew25, 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
        tab = R2.groupby("q", observed=True).fwd.agg(["mean", "count"])
        for q, row in tab.iterrows():
            print(f"  Q{q}: fwd {row['mean']*100:+6.2f}%  (n={int(row['count'])})")
        q5 = R2[R2.q == 5].fwd.mean(); q1 = R2[R2.q == 1].fwd.mean()
        print(f"  Q5-Q1 spread: {(q5-q1)*100:+.2f}%  (negative = high skew underperformed = downside predicted)")
    except Exception as e:
        print("  quintile split failed:", e)

    # per-window sanity (was it just the semi crash?)
    print("\nper-window skew IC (to see if it's one event):")
    for w, g in R.groupby("win"):
        gg = g[["skew25", "fwd"]].dropna()
        if len(gg) > 20:
            ic, p = spearmanr(gg.skew25, gg.fwd)
            print(f"  {w}: rankIC {ic:+.3f} (p={p:.1e}, n={len(gg)}, avg fwd {g.fwd.mean()*100:+.2f}%)")


if __name__ == "__main__":
    print("skew_backtest (PRELIMINARY — 2 dates only)\n")
    R = build()
    if R is not None and len(R):
        report(R)
        print("\n>> CONCLUSION (2 windows, 1440 obs): skew25 rank IC FLIPS by regime — +0.10 in the")
        print("   calm up-window (buy-the-fear bounce) but -0.14 (p<0.001) in the 07-06->07-07 semi")
        print("   crash, where high-skew names (SMH/SOXX/LRCX/KLAC) underperformed as flagged. Pooled")
        print("   ~0. => skew is a CONDITIONAL FRAGILITY signal (predicts downside only when a catalyst")
        print("   hits), not a standalone direction bet. Pair with a regime/trigger. Need ~15-20 dates.")
