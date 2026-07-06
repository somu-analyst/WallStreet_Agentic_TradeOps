"""Backtest the Risk-Off Radar vs DB history. Reconstruct the 5-pillar score per
trading day, join forward SPY returns (t+3, t+5), bucket, report hit-rate + avg move
vs baseline. Faithful where the data allows; pillar 3 (VRP) and 5 (gamma) use honest
EOD proxies (VIX-vs-RV; near-money net-OI sign) since per-name historical IV / intraday
GEX aren't stored. Prints exactly what's a proxy."""
import sqlite3, numpy as np, pandas as pd

DB = r"C:\Users\srini\Options_chain_data\US_data.db"
IDX = {"SPY","QQQ","IWM","DIA","SMH","SOXX","SOXL","XLK","XLF","XLE","XLI","XLRE",
       "EEM","FXI","KWEB","TLT","GLD","TQQQ","UPRO","SPXL"}
con = sqlite3.connect(DB)

# ── price panel (date x ticker close) ─────────────────────────────
sd = pd.read_sql("SELECT ticker,trade_date,close FROM stock_daily", con)
px = sd.pivot_table(index="trade_date", columns="ticker", values="close").sort_index()
dates = list(px.index)
stocks = [c for c in px.columns if not c.startswith("^")]      # breadth/zrev universe
vix = px["^VIX"] if "^VIX" in px.columns else None

logret = np.log(px / px.shift(1))
mean20 = px.rolling(20).mean()
std20  = px.rolling(20).std()
z20    = (px - mean20) / std20
rv20   = logret.rolling(20).std() * np.sqrt(252)               # realized vol

# ── options panels for pillars 1 & 5 ─────────────────────────────
qmarks = ",".join("?" * len(IDX))
od = pd.read_sql(
    f"SELECT ticker,trade_date,expiry_date,strike,openInt_Call,openInt_Put,vol_Put "
    f"FROM options_daily WHERE ticker IN ({qmarks})", con, params=tuple(IDX))
od["dte"] = (pd.to_datetime(od["expiry_date"], errors="coerce")
             - pd.to_datetime(od["trade_date"], errors="coerce")).dt.days
for c in ("openInt_Call","openInt_Put","vol_Put","strike"):
    od[c] = pd.to_numeric(od[c], errors="coerce")

# Pillar 1: index-ETF put UOA fires (vol>=2*OI, OI>50, vol>=300, DTE>=7) per date
uoa = od[(od.dte >= 7) & (od.openInt_Put > 50) & (od.vol_Put >= 300)
         & (od.vol_Put >= 2 * od.openInt_Put)]
p1_fires = uoa.groupby("trade_date")["ticker"].count()          # contract-level fires

# Pillar 5 proxy: near-money(+/-3%) front(<45d) net OI sign for SPY/QQQ/IWM
g3 = od[od.ticker.isin(["SPY","QQQ","IWM"]) & (od.dte >= 0) & (od.dte <= 45)].copy()
spot_map = {(r.ticker, r.trade_date): px.at[r.trade_date, r.ticker]
            for r in g3[["ticker","trade_date"]].drop_duplicates().itertuples()
            if r.trade_date in px.index and r.ticker in px.columns}
g3["spot"] = [spot_map.get((t, d), np.nan) for t, d in zip(g3.ticker, g3.trade_date)]
g3 = g3[np.abs(g3.strike / g3.spot - 1) <= 0.03]
netoi = g3.groupby(["trade_date","ticker"]).apply(
    lambda x: (x.openInt_Call.sum() - x.openInt_Put.sum())).rename("net")
neg_gamma = (netoi < 0).groupby(level=0).sum()                  # # of SPY/QQQ/IWM negative per date

# ── assemble per-date score ──────────────────────────────────────
rows = []
for i, d in enumerate(dates):
    if i < 20:                                                  # need 20d lookback
        continue
    zt = z20.loc[d, stocks].dropna()
    ob = int((zt > 2).sum())                                    # overbought count
    below = int((px.loc[d, stocks] < mean20.loc[d, stocks]).sum())
    tot = int(px.loc[d, stocks].notna().sum())
    pct_below = below / tot * 100 if tot else 0
    # pillar 3: VIX vs each name's RV20
    negvrp = 0
    if vix is not None and not np.isnan(vix.loc[d]):
        vv = vix.loc[d] / 100.0
        for tk in ("SPY","QQQ","IWM"):
            if tk in rv20.columns and not np.isnan(rv20.loc[d, tk]) and vv < rv20.loc[d, tk]:
                negvrp += 1
    p1 = min(20.0, float(p1_fires.get(d, 0)) * 4.0)
    p2 = min(20.0, ob * 2.5)
    p3 = min(20.0, negvrp * 7.0)
    p4 = max(0.0, min(20.0, (pct_below - 40) / 40 * 20))
    p5 = min(20.0, float(neg_gamma.get(d, 0)) * 7.0)
    score = p1 + p2 + p3 + p4 + p5
    # forward SPY returns
    sp = px["SPY"]
    f3 = (sp.iloc[i+3] / sp.iloc[i] - 1) if i+3 < len(dates) else np.nan
    f5 = (sp.iloc[i+5] / sp.iloc[i] - 1) if i+5 < len(dates) else np.nan
    rows.append(dict(date=d, score=score, p1=p1, p2=p2, p3=p3, p4=p4, p5=p5,
                     ob=ob, pct_below=pct_below, negvrp=negvrp,
                     idx_put_fires=int(p1_fires.get(d,0)), neg_gamma=int(neg_gamma.get(d,0)),
                     fwd3=f3, fwd5=f5))
df = pd.DataFrame(rows)
val = df.dropna(subset=["fwd5"])
con.close()

print(f"Backtest window: {df.date.min()} .. {df.date.max()}  ·  {len(df)} scored days, {len(val)} with fwd5\n")
print("Score distribution:")
print(f"  min {df.score.min():.0f}  median {df.score.median():.0f}  mean {df.score.mean():.0f}  max {df.score.max():.0f}")
print(f"  days >=55 (RED): {(df.score>=55).sum()}   30-54 (amber): {((df.score>=30)&(df.score<55)).sum()}   <30 (green): {(df.score<30).sum()}\n")

base3 = val.fwd3.mean(); base5 = val.fwd5.mean(); basedn5 = (val.fwd5<0).mean()
print(f"BASELINE (all days): avg fwd3 {base3*100:+.2f}%  avg fwd5 {base5*100:+.2f}%  down5 {basedn5*100:.0f}%\n")

print(f"{'Bucket':<14}{'N':>4}{'avgFwd3':>10}{'avgFwd5':>10}{'%down5':>9}{'vsBase5':>10}")
for lab, m in (("<30 green", val.score<30), ("30-54 amber", (val.score>=30)&(val.score<55)),
               (">=55 RED", val.score>=55)):
    s = val[m]
    if len(s)==0:
        print(f"{lab:<14}{0:>4}{'—':>10}{'—':>10}{'—':>9}{'—':>10}"); continue
    print(f"{lab:<14}{len(s):>4}{s.fwd3.mean()*100:>+9.2f}%{s.fwd5.mean()*100:>+9.2f}%"
          f"{(s.fwd5<0).mean()*100:>8.0f}%{(s.fwd5.mean()-base5)*100:>+9.2f}%")

# quartile (continuous) view + rank correlation
q = val.copy()
q["bucket"] = pd.qcut(q.score, 4, labels=["Q1 low","Q2","Q3","Q4 high"], duplicates="drop")
print(f"\n{'Quartile':<10}{'N':>4}{'scoreRange':>16}{'avgFwd5':>10}{'%down5':>9}")
for b, s in q.groupby("bucket", observed=True):
    print(f"{str(b):<10}{len(s):>4}{f'{s.score.min():.0f}-{s.score.max():.0f}':>16}"
          f"{s.fwd5.mean()*100:>+9.2f}%{(s.fwd5<0).mean()*100:>8.0f}%")
from scipy.stats import spearmanr
rho, p = spearmanr(val.score, val.fwd5)
print(f"\nSpearman rank corr(score, fwd5) = {rho:+.3f}  (p={p:.3f})   "
      f"[negative = higher score precedes lower SPY = radar works]")
print("\nNOTE: pillar3 (VRP) uses VIX vs RV proxy; pillar5 (gamma) uses near-money net-OI"
      " sign proxy. ~6mo window = low statistical power — read as directional, not proof.")
