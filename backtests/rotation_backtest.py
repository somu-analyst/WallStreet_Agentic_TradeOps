"""Rotation quadrant backtest — cross-sectional, pooled over names x dates.
For each name/date: strength = 63d excess vs SPY, momentum = 21d excess - strength/3.
Quadrant (Leading/Weakening/Improving/Lagging). Test forward 5/10/20d return + excess.
Hypothesis: Leading/Improving (momentum+) outperform Weakening/Lagging."""
import sqlite3, numpy as np, pandas as pd
from scipy.stats import spearmanr
c = sqlite3.connect(r"C:\Users\srini\Options_chain_data\US_data.db")
sd = pd.read_sql("SELECT ticker,trade_date,close FROM stock_daily", c); c.close()
px = sd.pivot_table(index="trade_date", columns="ticker", values="close").sort_index()
dates = list(px.index)
tks = [t for t in px.columns if not t.startswith("^")]
spy = px["SPY"]
r63 = px[tks] / px[tks].shift(63) - 1; s63 = spy / spy.shift(63) - 1
r21 = px[tks] / px[tks].shift(21) - 1; s21 = spy / spy.shift(21) - 1
strength = r63.sub(s63, axis=0); short_exc = r21.sub(s21, axis=0)
momentum = short_exc - strength / 3

def quad(st, mo):
    if st >= 0 and mo >= 0: return "Leading"
    if st >= 0 and mo < 0:  return "Weakening"
    if st < 0 and mo >= 0:  return "Improving"
    return "Lagging"

recs = []
for i, d in enumerate(dates):
    if i < 64 or i + 20 >= len(dates):
        continue
    for tk in tks:
        stg = strength.loc[d, tk]; mom = momentum.loc[d, tk]
        if pd.isna(stg) or pd.isna(mom):
            continue
        row = {"q": quad(stg, mom), "strength": stg, "momentum": mom}
        for h in (5, 10, 20):
            f = px[tk].iloc[i + h] / px[tk].iloc[i] - 1
            sr = spy.iloc[i + h] / spy.iloc[i] - 1
            row[f"f{h}"] = f; row[f"e{h}"] = f - sr
        recs.append(row)
R = pd.DataFrame(recs)
print(f"Rotation backtest: {len(R):,} name-date observations\n")

for h in (5, 10, 20):
    print(f"=== forward {h}-day, by quadrant ===")
    print(f"{'Quadrant':<11}{'N':>7}{'avgRet':>9}{'%up':>6}{'avgExcess':>11}{'%outperf':>10}")
    for q in ["Leading", "Improving", "Weakening", "Lagging"]:
        s = R[R.q == q]
        if len(s) == 0:
            continue
        print(f"{q:<11}{len(s):>7}{s[f'f{h}'].mean()*100:>+8.2f}%{(s[f'f{h}']>0).mean()*100:>5.0f}%"
              f"{s[f'e{h}'].mean()*100:>+10.2f}%{(s[f'e{h}']>0).mean()*100:>9.0f}%")
    lead = R[R.q == "Leading"]; lag = R[R.q == "Lagging"]
    imp = R[R.q == "Improving"]; wk = R[R.q == "Weakening"]
    print(f"  Leading−Lagging excess spread: {(lead[f'e{h}'].mean()-lag[f'e{h}'].mean())*100:+.2f}%")
    print(f"  Improving−Weakening spread:    {(imp[f'e{h}'].mean()-wk[f'e{h}'].mean())*100:+.2f}%")
    # rank IC of momentum & strength vs forward excess
    icm = np.mean([spearmanr(g.momentum, g[f"e{h}"])[0] for _, g in R.assign(dd=range(len(R))).groupby(R.index//len(tks)) if len(g) > 15]) if False else None
    print()
# continuous IC (per-date) of momentum and strength vs forward return
R["date_i"] = (R.index // 1)  # not grouped; compute pooled Spearman instead
for h in (10,):
    im = spearmanr(R.momentum, R[f"f{h}"]); ist = spearmanr(R.strength, R[f"f{h}"])
    print(f"Pooled rank corr vs f{h}:  momentum {im[0]:+.3f} (p={im[1]:.1e})  |  strength {ist[0]:+.3f} (p={ist[1]:.1e})")
print("\n~6mo, one regime. Positive Leading/Improving vs Lagging + positive momentum IC = rotation edge is real.")
