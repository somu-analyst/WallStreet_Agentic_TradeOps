"""Validate the redesigned TWO-GAUGE model vs the old blend.
Turbulence gauge  = index put-flow (P1)           -> predict |move|
Direction gauge   = z(neg-gamma) + z(breadth)     -> predict signed move (down)
Compare Spearman vs old composite (P1..P5 summed, capped)."""
import sqlite3, numpy as np, pandas as pd
from scipy.stats import spearmanr
DB=r"C:\Users\srini\Options_chain_data\US_data.db"
IDX={"SPY","QQQ","IWM","DIA","SMH","SOXX","SOXL","XLK","XLF","XLE","XLI","XLRE","EEM","FXI","KWEB","TLT","GLD","TQQQ","UPRO","SPXL"}
con=sqlite3.connect(DB)
sd=pd.read_sql("SELECT ticker,trade_date,close FROM stock_daily",con)
px=sd.pivot_table(index="trade_date",columns="ticker",values="close").sort_index()
dates=list(px.index); stocks=[c for c in px.columns if not c.startswith("^")]; vix=px.get("^VIX")
logret=np.log(px/px.shift(1)); mean20=px.rolling(20).mean(); std20=px.rolling(20).std()
z20=(px-mean20)/std20; rv20=logret.rolling(20).std()*np.sqrt(252)
qm=",".join("?"*len(IDX))
od=pd.read_sql(f"SELECT ticker,trade_date,expiry_date,strike,openInt_Call,openInt_Put,vol_Put FROM options_daily WHERE ticker IN ({qm})",con,params=tuple(IDX))
od["dte"]=(pd.to_datetime(od.expiry_date,errors="coerce")-pd.to_datetime(od.trade_date,errors="coerce")).dt.days
for c in("openInt_Call","openInt_Put","vol_Put","strike"): od[c]=pd.to_numeric(od[c],errors="coerce")
uoa=od[(od.dte>=7)&(od.openInt_Put>50)&(od.vol_Put>=300)&(od.vol_Put>=2*od.openInt_Put)]
p1=uoa.groupby("trade_date").size()
g3=od[od.ticker.isin(["SPY","QQQ","IWM"])&(od.dte>=0)&(od.dte<=45)].copy()
sm={(t,d):px.at[d,t] for t,d in g3[["ticker","trade_date"]].drop_duplicates().itertuples(index=False) if d in px.index and t in px.columns}
g3["spot"]=[sm.get((t,d),np.nan) for t,d in zip(g3.ticker,g3.trade_date)]
g3=g3[np.abs(g3.strike/g3.spot-1)<=0.03]
netoi=g3.groupby(["trade_date","ticker"]).apply(lambda x:x.openInt_Call.sum()-x.openInt_Put.sum(),include_groups=False)
neg_gamma=(netoi<0).groupby(level=0).sum()
rows=[]
for i,d in enumerate(dates):
    if i<20: continue
    ob=int((z20.loc[d,stocks]>2).sum())
    below=int((px.loc[d,stocks]<mean20.loc[d,stocks]).sum()); tot=int(px.loc[d,stocks].notna().sum())
    pb=below/tot*100 if tot else np.nan
    vv=vix.loc[d]/100 if (vix is not None and not np.isnan(vix.loc[d])) else np.nan
    negvrp=sum(1 for tk in("SPY","QQQ","IWM") if tk in rv20.columns and not np.isnan(rv20.loc[d,tk]) and not np.isnan(vv) and vv<rv20.loc[d,tk])
    P1=float(p1.get(d,0)); P4=pb; P5=float(neg_gamma.get(d,0))
    old=min(20,P1*4)+min(20,ob*2.5)+min(20,negvrp*7)+max(0,min(20,(pb-40)/40*20))+min(20,P5*7)
    rows.append(dict(date=d,i=i,P1=P1,P4=P4,P5=P5,old=old))
bt=pd.DataFrame(rows).set_index("date")
# z-score the direction inputs and combine
bt["Zbr"]=(bt.P4-bt.P4.mean())/bt.P4.std(); bt["Zgm"]=(bt.P5-bt.P5.mean())/bt.P5.std()
bt["DIR"]=bt.Zbr+bt.Zgm                # higher = more downside risk
bt["TURB"]=bt.P1                        # turbulence gauge
def fwd(tk,i,h):
    s=px[tk]; return (s.iloc[i+h]/s.iloc[i]-1) if i+h<len(dates) else np.nan
for tk in("SPY","QQQ"):
    for h in(3,5): bt[f"{tk}_f{h}"]=[fwd(tk,int(i),h) for i in bt.i]
con.close()
def sp(a,b):
    s=bt[[a,b]].dropna(); r,p=spearmanr(s[a],s[b]); return r,p,len(s)
print("DIRECTION gauge (z-breadth + z-neggamma) vs SIGNED return  [want NEGATIVE]:")
for tk in("SPY","QQQ"):
    for h in(3,5):
        r,p,n=sp("DIR",f"{tk}_f{h}"); print(f"  DIR vs {tk}_f{h}:  rho={r:+.3f}  p={p:.3f}  n={n}")
print("\nOLD composite vs SIGNED return  [was ~0]:")
for tk in("SPY","QQQ"):
    for h in(3,5):
        r,p,n=sp("old",f"{tk}_f{h}"); print(f"  old vs {tk}_f{h}:  rho={r:+.3f}  p={p:.3f}")
print("\nTURBULENCE gauge (put-flow) vs |return|  [want POSITIVE]:")
for tk in("SPY","QQQ"):
    for h in(3,5):
        s=bt[["TURB",f"{tk}_f{h}"]].dropna(); r,p=spearmanr(s.TURB,s[f"{tk}_f{h}"].abs())
        print(f"  TURB vs |{tk}_f{h}|:  rho={r:+.3f}  p={p:.3f}")
# actionable: when BOTH DIR high AND TURB high -> worst days?
hi=bt[(bt.DIR>bt.DIR.quantile(.6))&(bt.TURB>=bt.TURB.quantile(.6))]
print(f"\nDIR-high AND TURB-high days (n={len(hi)}): QQQ avg f5={hi.QQQ_f5.mean()*100:+.2f}%  %down={ (hi.QQQ_f5<0).mean()*100:.0f}%  |f5|={hi.QQQ_f5.abs().mean()*100:.2f}%")
alld=bt.dropna(subset=["QQQ_f5"]); print(f"   baseline: QQQ avg f5={alld.QQQ_f5.mean()*100:+.2f}%  %down={(alld.QQQ_f5<0).mean()*100:.0f}%  |f5|={alld.QQQ_f5.abs().mean()*100:.2f}%")
