"""Per-pillar diagnostic: does any single pillar carry signal the blend washed out?
For each pillar (continuous raw form) test Spearman corr vs forward returns of SPY & QQQ
at t+1/t+3/t+5 — for DIRECTION (signed return) and TURBULENCE (|return|). A risk-off
pillar should be NEGATIVE vs signed return (hot -> down) and/or POSITIVE vs |return|
(hot -> big move). Also terciles: when a pillar is HOT, what's the down-rate & avg move."""
import sqlite3, numpy as np, pandas as pd
from scipy.stats import spearmanr

DB = r"C:\Users\srini\Options_chain_data\US_data.db"
IDX = {"SPY","QQQ","IWM","DIA","SMH","SOXX","SOXL","XLK","XLF","XLE","XLI","XLRE",
       "EEM","FXI","KWEB","TLT","GLD","TQQQ","UPRO","SPXL"}
con = sqlite3.connect(DB)

sd = pd.read_sql("SELECT ticker,trade_date,close FROM stock_daily", con)
px = sd.pivot_table(index="trade_date", columns="ticker", values="close").sort_index()
dates = list(px.index)
stocks = [c for c in px.columns if not c.startswith("^")]
vix = px.get("^VIX")
logret = np.log(px / px.shift(1))
mean20 = px.rolling(20).mean(); std20 = px.rolling(20).std()
z20 = (px - mean20) / std20
rv20 = logret.rolling(20).std() * np.sqrt(252)

qmarks = ",".join("?" * len(IDX))
od = pd.read_sql(f"SELECT ticker,trade_date,expiry_date,strike,openInt_Call,openInt_Put,vol_Put "
                 f"FROM options_daily WHERE ticker IN ({qmarks})", con, params=tuple(IDX))
od["dte"] = (pd.to_datetime(od.expiry_date, errors="coerce") - pd.to_datetime(od.trade_date, errors="coerce")).dt.days
for c in ("openInt_Call","openInt_Put","vol_Put","strike"):
    od[c] = pd.to_numeric(od[c], errors="coerce")
uoa = od[(od.dte>=7)&(od.openInt_Put>50)&(od.vol_Put>=300)&(od.vol_Put>=2*od.openInt_Put)]
p1_fires = uoa.groupby("trade_date").size()
g3 = od[od.ticker.isin(["SPY","QQQ","IWM"])&(od.dte>=0)&(od.dte<=45)].copy()
sm = {(t,d): px.at[d,t] for t,d in g3[["ticker","trade_date"]].drop_duplicates().itertuples(index=False)
      if d in px.index and t in px.columns}
g3["spot"] = [sm.get((t,d), np.nan) for t,d in zip(g3.ticker,g3.trade_date)]
g3 = g3[np.abs(g3.strike/g3.spot-1)<=0.03]
netoi = g3.groupby(["trade_date","ticker"]).apply(lambda x: x.openInt_Call.sum()-x.openInt_Put.sum(), include_groups=False).rename("net")
neg_gamma = (netoi<0).groupby(level=0).sum()
# continuous SPY net-OI (normalized) — more granular than the 0..3 count
spy_net = netoi.xs("SPY", level=1) if "SPY" in netoi.index.get_level_values(1) else pd.Series(dtype=float)

rows=[]
for i,d in enumerate(dates):
    if i<20: continue
    ob = int((z20.loc[d,stocks]>2).sum())
    below = int((px.loc[d,stocks]<mean20.loc[d,stocks]).sum()); tot=int(px.loc[d,stocks].notna().sum())
    pct_below = below/tot*100 if tot else np.nan
    vv = vix.loc[d]/100 if (vix is not None and not np.isnan(vix.loc[d])) else np.nan
    vrp_gap = np.nanmean([rv20.loc[d,tk]-vv for tk in ("SPY","QQQ","IWM") if tk in rv20.columns]) if not np.isnan(vv) else np.nan
    rows.append(dict(date=d, i=i,
        P1_putflow=float(p1_fires.get(d,0)),
        P2_froth=ob,
        P3_volunder=vrp_gap,                       # RV - IV : positive = vol underpriced (risk)
        P4_breadth=pct_below,
        P5_neggamma=-(spy_net.get(d, np.nan)),     # negative net-OI -> positive risk value
    ))
bt = pd.DataFrame(rows).set_index("date")

def fwd(tk,i,h):
    s=px[tk]
    return (s.iloc[i+h]/s.iloc[i]-1) if i+h<len(dates) else np.nan
for tk in ("SPY","QQQ"):
    for h in (1,3,5):
        bt[f"{tk}_f{h}"] = [fwd(tk,int(i),h) for i in bt["i"]]
con.close()

pillars=["P1_putflow","P2_froth","P3_volunder","P4_breadth","P5_neggamma"]
print(f"Window {bt.index.min()}..{bt.index.max()} · {len(bt)} days\n")
print("SPEARMAN corr — DIRECTION (signed ret): NEG = pillar hot -> price DOWN (risk-off works)")
print(f"{'pillar':<13}{'SPY_f1':>9}{'SPY_f3':>9}{'SPY_f5':>9}{'QQQ_f1':>9}{'QQQ_f3':>9}{'QQQ_f5':>9}")
for p in pillars:
    vals=[]
    for tk in ("SPY","QQQ"):
        for h in (1,3,5):
            sub=bt[[p,f"{tk}_f{h}"]].dropna()
            r,_=spearmanr(sub[p],sub[f"{tk}_f{h}"]) if len(sub)>10 else (np.nan,1)
            vals.append(r)
    print(f"{p:<13}"+"".join(f"{v:>+9.2f}" for v in vals))

print("\nSPEARMAN corr — TURBULENCE (|ret|): POS = pillar hot -> BIG move coming (vol radar works)")
print(f"{'pillar':<13}{'SPY_f1':>9}{'SPY_f3':>9}{'SPY_f5':>9}{'QQQ_f1':>9}{'QQQ_f3':>9}{'QQQ_f5':>9}")
for p in pillars:
    vals=[]
    for tk in ("SPY","QQQ"):
        for h in (1,3,5):
            sub=bt[[p,f"{tk}_f{h}"]].dropna()
            r,_=spearmanr(sub[p],sub[f"{tk}_f{h}"].abs()) if len(sub)>10 else (np.nan,1)
            vals.append(r)
    print(f"{p:<13}"+"".join(f"{v:>+9.2f}" for v in vals))

print("\nHOT-tercile behaviour (top 1/3 of each pillar) — QQQ 3-day forward:")
print(f"{'pillar':<13}{'N':>4}{'avgF3':>9}{'%down':>8}{'avg|F3|':>9}{'  vs all-days |F3|'}")
allabs = bt["QQQ_f3"].abs().mean()
for p in pillars:
    sub=bt[[p,"QQQ_f3"]].dropna()
    thr=sub[p].quantile(2/3); hot=sub[sub[p]>=thr]
    if len(hot)<5:
        print(f"{p:<13}{len(hot):>4}{'—':>9}"); continue
    print(f"{p:<13}{len(hot):>4}{hot.QQQ_f3.mean()*100:>+8.2f}%{(hot.QQQ_f3<0).mean()*100:>7.0f}%"
          f"{hot.QQQ_f3.abs().mean()*100:>8.2f}%   (all={allabs*100:.2f}%)")
print("\n~6mo uptrend, low power. NEG direction-corr or POS turbulence-corr = worth keeping.")
