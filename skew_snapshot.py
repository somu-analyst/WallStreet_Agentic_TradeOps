"""skew_snapshot.py — derive an options-IV metrics panel from the OpenBB capture.

Reads options_openbb (US_data_OpenBB.db: real IV/bid-ask/delta) and, for every capture
date, computes per-ticker options-derived signals that plain lastPrice data can't produce.
Writes them to skew_snapshot so history accrues cleanly for a proper cross-sectional
backtest once enough dates exist. Parallel test lane only — never touches US_data.db.

Metrics per (trade_date, ticker), front expiry (10-45 DTE, most-liquid):
  skew25   IV(25Δ put) - IV(25Δ call)   downside fear priced (research skew)
  atm_iv   mean ATM call/put IV          overall vol level
  pc_iv    IV(ATM put) - IV(ATM call)    put-call IV spread
  pcvol    Σ put vol / Σ call vol        flow put/call
  pcoi     Σ put OI  / Σ call OI         positioning put/call
  liq      median relative bid-ask       liquidity (wide = illiquid/risky)

Run:  python skew_snapshot.py            # process all capture dates (idempotent)
"""
import os, sqlite3, numpy as np, pandas as pd

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "US_data_OpenBB.db")
DB = os.path.normpath(DB) if os.path.exists(os.path.normpath(DB)) else \
    r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db"


def _metrics(g):
    """One ticker's chain on one date -> metrics dict (or None)."""
    g = g.copy()
    for c in ("iv_Call", "iv_Put", "delta_Call", "delta_Put", "vol_Call", "vol_Put",
              "openInt_Call", "openInt_Put", "bid_Call", "ask_Call", "bid_Put", "ask_Put"):
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g = g[(g.dte >= 10) & (g.dte <= 45)]
    if g.empty:
        return None
    exp = g.expiry_date.value_counts().idxmax()          # most-liquid front expiry
    e = g[g.expiry_date == exp]
    gc = e[(e.iv_Call > 0.01) & e.delta_Call.between(0.05, 0.7)]
    gp = e[(e.iv_Put > 0.01) & e.delta_Put.between(-0.7, -0.05)]
    if len(gc) < 2 or len(gp) < 2:
        return None
    c25 = gc.iloc[(gc.delta_Call - 0.25).abs().argmin()]
    c50 = gc.iloc[(gc.delta_Call - 0.50).abs().argmin()]
    p25 = gp.iloc[(gp.delta_Put + 0.25).abs().argmin()]
    p50 = gp.iloc[(gp.delta_Put + 0.50).abs().argmin()]
    def relspr(row, side):
        b, a = row[f"bid_{side}"], row[f"ask_{side}"]
        m = (b + a) / 2
        return (a - b) / m if (m and m > 0 and a >= b) else np.nan
    liq = np.nanmedian([relspr(c50, "Call"), relspr(p50, "Put")])
    vc, vp = e.vol_Call.sum(), e.vol_Put.sum()
    oc, op = e.openInt_Call.sum(), e.openInt_Put.sum()
    return {"skew25": p25.iv_Put - c25.iv_Call,
            "atm_iv": np.nanmean([c50.iv_Call, p50.iv_Put]),
            "pc_iv": p50.iv_Put - c50.iv_Call,
            "pcvol": (vp / vc) if vc else np.nan,
            "pcoi": (op / oc) if oc else np.nan,
            "liq": liq}


def build(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS skew_snapshot (
        trade_date TEXT, ticker TEXT, skew25 REAL, atm_iv REAL, pc_iv REAL,
        pcvol REAL, pcoi REAL, liq REAL, PRIMARY KEY (trade_date, ticker))""")
    conn.commit()
    dates = [r[0] for r in conn.execute("SELECT DISTINCT trade_date FROM options_openbb ORDER BY trade_date")]
    print(f"capture dates: {dates}")
    for d in dates:
        df = pd.read_sql("SELECT ticker,strike,expiry_date,iv_Call,iv_Put,delta_Call,delta_Put,"
                         "vol_Call,vol_Put,openInt_Call,openInt_Put,bid_Call,ask_Call,bid_Put,ask_Put "
                         "FROM options_openbb WHERE trade_date=?", conn, params=(d,))
        df["dte"] = (pd.to_datetime(df.expiry_date, errors="coerce") - pd.to_datetime(d)).dt.days
        rows = []
        for tk, g in df.groupby("ticker"):
            m = _metrics(g)
            if m:
                rows.append((d, tk, m["skew25"], m["atm_iv"], m["pc_iv"], m["pcvol"], m["pcoi"], m["liq"]))
        conn.executemany("INSERT OR REPLACE INTO skew_snapshot "
                         "(trade_date,ticker,skew25,atm_iv,pc_iv,pcvol,pcoi,liq) VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()
        print(f"  {d}: wrote {len(rows)} tickers")


if __name__ == "__main__":
    print(f"skew_snapshot -> {DB}")
    c = sqlite3.connect(DB)
    try:
        build(c)
        n = c.execute("SELECT COUNT(*), COUNT(DISTINCT trade_date) FROM skew_snapshot").fetchone()
        print(f"skew_snapshot now holds {n[0]} rows across {n[1]} dates")
    finally:
        c.close()
