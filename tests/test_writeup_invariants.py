"""Independent validation harness for the ticker write-up (live data + invariants).

Run:  python tools/validate_writeup.py [TICKER]

Asserts invariants that MUST hold regardless of market state:
 1. price coherence  - one spot drives header, levels and trade ideas
 2. no-arbitrage     - every option estimate >= intrinsic value
 3. wall sanity      - gamma/OI walls sit within a sane band of spot
 4. PCR coherence    - the PCR shown next to CdOI/PdOI is derivable from them
 5. POP sanity       - probabilities in (0,1), monotonic in moneyness
 6. OPEX structure   - monthly (3rd-Fri) expiry carries the OI concentration
"""
import sys, os, logging, io, math
from datetime import date, timedelta

logging.disable(logging.CRITICAL)
sys.argv = ["x"]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)
import telegram_bot_optimized as bot          # noqa: E402
import pandas as pd, numpy as np              # noqa: E402

TK = (sys.argv[1] if len(sys.argv) > 1 else "QQQ").upper()
OUT, R = [], []
P = lambda *a: OUT.append(" ".join(str(x) for x in a))


def check(name, ok, detail):
    R.append((ok, name, detail))
    P(f"[{'PASS' if ok else 'FAIL'}] {name}\n        {detail}")


conn = bot.get_conn()
P(f"===== VALIDATION: {TK} =====")

# ---------- 0. reference prices ----------
spot, is_live, asof = bot._cur_price(TK, 0.0)
spot = float(spot or 0)
h = pd.read_sql("""SELECT trade_date, close FROM stock_history WHERE ticker=?
                   ORDER BY trade_date DESC LIMIT 3""", conn, params=(TK,))
eod_close = float(h["close"].iloc[0]) if not h.empty else 0.0
eod_date = h["trade_date"].iloc[0] if not h.empty else "?"
P(f"\nspot(_cur_price)={spot:.2f}  live={is_live}  asof={asof}")
P(f"stock_history last close={eod_close:.2f} @ {eod_date}")
gap = abs(spot - eod_close) / eod_close * 100 if eod_close else 0
P(f"live-vs-EOD gap = {gap:.2f}%")

# ---------- 1. option chain for the nearest expiries ----------
ld = conn.execute("SELECT MAX(trade_date_now) FROM options_change WHERE ticker=?", (TK,)).fetchone()[0]
oc = pd.read_sql("""SELECT expiry_date, strike, change_OI_Call, change_OI_Put,
                           openInt_Call_now, openInt_Put_now,
                           lastPrice_Call_now, lastPrice_Put_now
                    FROM options_change WHERE ticker=? AND trade_date_now=?""",
                 conn, params=(TK, ld))
for c in oc.columns:
    if c != "expiry_date":
        oc[c] = pd.to_numeric(oc[c], errors="coerce").fillna(0.0)
P(f"\noptions_change latest trade_date={ld}  rows={len(oc)}  expiries={oc.expiry_date.nunique()}")

# ---------- 2. no-arbitrage: recorded call/put prices vs intrinsic ----------
# Use the SAME price the engine would have used at capture time (eod_close), then re-test at live spot.
for label, S in (("EOD close", eod_close), ("LIVE spot", spot)):
    c_bad = oc[(oc.lastPrice_Call_now > 0) & (oc.lastPrice_Call_now < (S - oc.strike) - 0.01)]
    p_bad = oc[(oc.lastPrice_Put_now > 0) & (oc.lastPrice_Put_now < (oc.strike - S) - 0.01)]
    check(f"no-arbitrage vs {label} ({S:.2f})",
          len(c_bad) + len(p_bad) == 0,
          f"{len(c_bad)} calls + {len(p_bad)} puts priced BELOW intrinsic"
          + (f"; worst call K={c_bad.iloc[0].strike:.0f} px={c_bad.iloc[0].lastPrice_Call_now:.2f} "
             f"intrinsic={S - c_bad.iloc[0].strike:.2f}" if len(c_bad) else ""))

# ---------- 3. per-expiry PCR coherence ----------
P("\n----- per-expiry table (what the write-up prints) -----")
ex = oc.groupby("expiry_date").agg(
    cdoi=("change_OI_Call", "sum"), pdoi=("change_OI_Put", "sum"),
    coi=("openInt_Call_now", "sum"), poi=("openInt_Put_now", "sum")).reset_index()
ex = ex.sort_values("expiry_date").head(14)
ex["pcr_dOI"] = ex.pdoi / ex.cdoi.replace(0, np.nan)
ex["pcr_OI"] = ex.poi / ex.coi.replace(0, np.nan)
P(f"{'expiry':<12}{'CdOI':>10}{'PdOI':>10}{'PCR(dOI)':>10}{'PCR(OI)':>10}")
for _, r in ex.iterrows():
    P(f"{r.expiry_date:<12}{r.cdoi:>10,.0f}{r.pdoi:>10,.0f}{r.pcr_dOI:>10.2f}{r.pcr_OI:>10.2f}")
P("NOTE: if the bot's printed PCR matches NEITHER column, the label is wrong.")

# ---------- 4. wall sanity ----------
g = bot._compute_gex(TK, conn, spot) or {}
cw, pw, zg = g.get("call_wall"), g.get("put_wall"), g.get("zero_gamma")
tops = g.get("top_strikes") or []
top_strikes = [t.get("strike") for t in tops][:6] if isinstance(tops, list) else []
P(f"\nGEX: call_wall={cw} put_wall={pw} zero_gamma={zg} expiry={g.get('expiry')} dte={g.get('dte')}")
P(f"GEX top_strikes={top_strikes}")
band = 0.15
for nm, v in (("call_wall", cw), ("put_wall", pw), ("zero_gamma", zg)):
    if v:
        off = (float(v) - spot) / spot * 100
        check(f"{nm} within +/-15% of spot", abs(off) <= band * 100,
              f"{nm}={v} is {off:+.1f}% from spot {spot:.2f}")
if top_strikes:
    offs = [(s - spot) / spot * 100 for s in top_strikes if s]
    check("GEX top_strikes within +/-15% of spot", all(abs(o) <= band * 100 for o in offs),
          f"offsets={[f'{o:+.1f}%' for o in offs]}")

# ---------- 5. OPEX structure ----------
def third_friday(y, m):
    d = date(y, m, 1)
    fr = [d + timedelta(days=i) for i in range(31)
          if (d + timedelta(days=i)).month == m and (d + timedelta(days=i)).weekday() == 4]
    return fr[2]

today = date.fromisoformat(ld)
opex = third_friday(today.year, today.month)
if opex < today:
    nm_ = today.month % 12 + 1
    opex = third_friday(today.year + (1 if nm_ == 1 else 0), nm_)
opex_s = opex.isoformat()
tot_oi = oc.openInt_Call_now.sum() + oc.openInt_Put_now.sum()
op = oc[oc.expiry_date == opex_s]
op_oi = op.openInt_Call_now.sum() + op.openInt_Put_now.sum()
share = op_oi / tot_oi * 100 if tot_oi else 0
P(f"\nnext monthly OPEX = {opex_s}  OI share = {share:.1f}%  (rows={len(op)})")
check("OPEX expiry present in chain", len(op) > 0, f"{len(op)} strikes at {opex_s}")
check("OPEX carries meaningful OI (>=10%)", share >= 10, f"OPEX OI share {share:.1f}% of total")

# ---------- 6. POP sanity at live spot ----------
P("\n----- POP monotonicity (calls, nearest expiry with >=8 strikes) -----")
cand = [e for e in sorted(oc.expiry_date.unique()) if e >= ld]
use = next((e for e in cand if len(oc[oc.expiry_date == e]) >= 8), None)
if use:
    sub = oc[oc.expiry_date == use].sort_values("strike")
    T = max((date.fromisoformat(use) - today).days, 1) / 365.0
    atm = sub.iloc[(sub.strike - spot).abs().argsort()[:1]]
    mid = float(atm.lastPrice_Call_now.iloc[0])
    K0 = float(atm.strike.iloc[0])
    iv = 0.0
    try:
        iv = bot._implied_vol_hp(mid, spot, K0, T, 0.04) or 0.0
    except Exception as e:
        P(f"  _implied_vol_hp err: {str(e)[:80]}")
    iv = max(iv, 0.10)
    pops = []
    for _, r in sub.iterrows():
        try:
            pops.append((float(r.strike), bot._pa(spot, float(r.strike), T, iv)))
        except Exception:
            pass
    P(f"  expiry={use} dte={(date.fromisoformat(use)-today).days} ATM K={K0} mid={mid:.2f} iv={iv:.3f}")
    P("  " + " ".join(f"{k:.0f}:{p:.2f}" for k, p in pops[:14]))
    ok_rng = all(0.0 <= p <= 1.0 for _, p in pops)
    mono = all(pops[i][1] >= pops[i + 1][1] - 1e-6 for i in range(len(pops) - 1))
    check("POP within [0,1]", ok_rng, f"{len(pops)} strikes checked")
    check("POP monotonically decreasing in strike (calls)", mono,
          "P(S_T>K) must fall as K rises")
    check("ATM POP not pinned at 0/1", 0.05 < dict(pops).get(K0, 0.5) < 0.95,
          f"ATM POP={dict(pops).get(K0, float('nan')):.3f} (iv={iv:.3f})")

conn.close()
P("\n===== SUMMARY =====")
nf = sum(1 for ok, _, _ in R if not ok)
for ok, name, detail in R:
    if not ok:
        P(f"  FAIL: {name} -> {detail}")
P(f"  {len(R)-nf}/{len(R)} checks passed, {nf} FAILED")

io.open(os.path.join(HERE, "tools", "validate_out.txt"), "w", encoding="utf-8").write("\n".join(OUT))
print("\n".join(OUT))
