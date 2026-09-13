"""Expiry-wise validation + tradeable table (live spot, REAL OpenBB bid/ask/IV/delta).

Run:  python tools/validate_trades.py [TICKER]

Fixes two flaws found in validate_writeup.py:
  * POP test must skip 0-DTE (it silently checked 0 strikes and returned nan)
  * no-arb failures must be split by moneyness - deep-ITM stale `lastPrice` is a data
    artifact, near-the-money violations are real pricing bugs
Then builds per-expiry defined-risk trades with probability / investment / risk,
using options_openbb (real CBOE bid/ask/iv/delta) instead of stale lastPrice.
"""
import sys, os, logging, io
from datetime import date

logging.disable(logging.CRITICAL)
sys.argv = ["x"]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)
import telegram_bot_optimized as bot          # noqa: E402
import pandas as pd, numpy as np              # noqa: E402
from scipy.stats import norm                  # noqa: E402


def pa(S, K, T, sigma, r=0.04):
    """P(S_T > K) under GBM = N(d2). The bot computes this inline; replicated here."""
    if not (S > 0 and K > 0 and T > 0 and sigma > 0):
        return float("nan")
    d2 = (np.log(S / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d2))

TK = (sys.argv[1] if len(sys.argv) > 1 else "QQQ").upper()
OUT = []
P = lambda *a: OUT.append(" ".join(str(x) for x in a))

conn = bot.get_conn()
spot, is_live, asof = bot._cur_price(TK, 0.0)
spot = float(spot or 0)
ld = conn.execute("SELECT MAX(trade_date) FROM options_openbb WHERE ticker=?", (TK,)).fetchone()[0]
P(f"===== {TK}  spot={spot:.2f} ({asof})  options_openbb trade_date={ld} =====")

bb = pd.read_sql("""SELECT expiry_date, strike, bid_Call, ask_Call, iv_Call, delta_Call,
                           bid_Put, ask_Put, iv_Put, delta_Put, openInt_Call, openInt_Put
                    FROM options_openbb WHERE ticker=? AND trade_date=?""",
                 conn, params=(TK, ld))
for c in bb.columns:
    if c != "expiry_date":
        bb[c] = pd.to_numeric(bb[c], errors="coerce")
bb["mid_C"] = (bb.bid_Call + bb.ask_Call) / 2
bb["mid_P"] = (bb.bid_Put + bb.ask_Put) / 2
today = date.fromisoformat(ld)
P(f"rows={len(bb)}  expiries={bb.expiry_date.nunique()}")

# ---------- A. no-arbitrage split by moneyness, lastPrice vs BB mid ----------
oc = pd.read_sql("""SELECT expiry_date, strike, lastPrice_Call_now, lastPrice_Put_now
                    FROM options_change WHERE ticker=? AND trade_date_now=?""",
                 conn, params=(TK, ld))
for c in ("strike", "lastPrice_Call_now", "lastPrice_Put_now"):
    oc[c] = pd.to_numeric(oc[c], errors="coerce")
oc["mny"] = (oc.strike / spot - 1).abs()
bad = oc[(oc.lastPrice_Call_now > 0) & (oc.lastPrice_Call_now < (spot - oc.strike) - 0.01)]
P(f"\n----- A. no-arbitrage (lastPrice vs intrinsic @ live spot) -----")
P(f"  calls below intrinsic: {len(bad)} of {(oc.lastPrice_Call_now>0).sum()}")
for lo, hi, lab in ((0, .05, "NEAR the money (<5%)"), (.05, .15, "5-15%"), (.15, 9, "deep (>15%)")):
    n = len(bad[(bad.mny >= lo) & (bad.mny < hi)])
    P(f"    {lab:<22} {n:>5}")
P("  -> deep-ITM violations = stale untraded lastPrice (data artifact).")
P("  -> NEAR-the-money violations would be real pricing bugs.")
mrg = oc.merge(bb[["expiry_date", "strike", "mid_C"]], on=["expiry_date", "strike"], how="inner")
mrg = mrg.dropna(subset=["mid_C"])
bad_mid = mrg[(mrg.mid_C > 0) & (mrg.mid_C < (spot - mrg.strike) - 0.01)]
P(f"  SAME test using OpenBB bid/ask MID: {len(bad_mid)} of {(mrg.mid_C>0).sum()} violate")
P("  -> if BB mid is clean where lastPrice is not, the fix is: price from BB mid, not lastPrice.")

# ---------- B. POP validation on a REAL expiry (dte>=1) ----------
P("\n----- B. POP sanity (dte>=1, real chain) -----")
exs = sorted(e for e in bb.expiry_date.unique() if e > ld)
use = next((e for e in exs if len(bb[(bb.expiry_date == e) & bb.mid_C.notna()]) >= 8), None)
if use:
    sub = bb[bb.expiry_date == use].sort_values("strike").dropna(subset=["mid_C"])
    dte = (date.fromisoformat(use) - today).days
    T = max(dte, 1) / 365.0
    i = (sub.strike - spot).abs().values.argmin()
    K0, mid0 = float(sub.strike.iloc[i]), float(sub.mid_C.iloc[i])
    iv_bb = float(sub.iv_Call.iloc[i]) if pd.notna(sub.iv_Call.iloc[i]) else np.nan
    iv_hp = bot._implied_vol_hp(mid0, spot, K0, T, 0.04) or 0.0
    P(f"  expiry={use} dte={dte} ATM K={K0} mid={mid0:.2f} | BB iv={iv_bb:.4f} | backed-out iv={iv_hp:.4f}")
    iv = iv_bb if (iv_bb and 0.03 < iv_bb < 3) else max(iv_hp, 0.10)
    pops = [(float(r.strike), pa(spot, float(r.strike), T, iv)) for _, r in sub.iterrows()]
    mono = all(pops[j][1] >= pops[j + 1][1] - 1e-6 for j in range(len(pops) - 1))
    atm_pop = dict(pops).get(K0, float("nan"))
    P(f"  strikes checked={len(pops)}  monotonic={mono}  ATM POP={atm_pop:.3f}")
    P("  " + " ".join(f"{k:.0f}:{p:.2f}" for k, p in pops[:12]))
    P(f"  [{'PASS' if (mono and 0.05 < atm_pop < 0.95 and len(pops) >= 8) else 'FAIL'}] POP sane")

# ---------- C. expiry-wise trade table ----------
P("\n----- C. EXPIRY-WISE TRADES (defined risk, from BB bid/ask/delta) -----")
def third_friday(y, m):
    ds = [date(y, m, d) for d in range(15, 22)]
    return next(d for d in ds if d.weekday() == 4)
opex = third_friday(today.year, today.month)
if opex < today:
    m2 = today.month % 12 + 1
    opex = third_friday(today.year + (1 if m2 == 1 else 0), m2)

P(f"{'expiry':<12}{'dte':>4}{'OPEX':>5}{'ATM_IV':>8}{'1SD':>8}  {'PUT CREDIT SPREAD (short/long)':<34}"
  f"{'cr':>7}{'risk':>7}{'POP':>7}{'R/R':>6}")
rows = []
for e in exs[:12]:
    sub = bb[bb.expiry_date == e].sort_values("strike")
    sub = sub.dropna(subset=["mid_P"])
    if len(sub) < 6:
        continue
    dte = (date.fromisoformat(e) - today).days
    if dte < 1:
        continue
    T = dte / 365.0
    i = (sub.strike - spot).abs().values.argmin()
    iv = sub.iv_Put.iloc[i]
    iv = float(iv) if pd.notna(iv) and 0.03 < float(iv) < 3 else np.nan
    if not (iv == iv):
        continue
    sd = spot * iv * np.sqrt(T)
    # short put ~ delta -0.25 (fallback: nearest strike to spot-1SD), long put one strike lower
    cand = sub.dropna(subset=["delta_Put"])
    if len(cand) and cand.delta_Put.abs().between(0.05, 0.95).any():
        j = (cand.delta_Put.abs() - 0.25).abs().values.argmin()
        Ks = float(cand.strike.iloc[j]); dsh = abs(float(cand.delta_Put.iloc[j]))
    else:
        Ks = float(sub.strike.iloc[(sub.strike - (spot - sd)).abs().values.argmin()]); dsh = np.nan
    lower = sub[sub.strike < Ks]
    if lower.empty:
        continue
    Kl = float(lower.strike.iloc[-1])
    ms = float(sub.loc[sub.strike == Ks, "mid_P"].iloc[0])
    ml = float(lower.mid_P.iloc[-1])
    credit = ms - ml
    width = Ks - Kl
    risk = width - credit
    if not (credit > 0 and risk > 0):
        continue
    pop = pa(spot, Ks, T, iv)          # P(S_T > Ks) = P(short put expires OTM)
    rr = credit / risk
    is_opex = "YES" if e == opex.isoformat() else ""
    P(f"{e:<12}{dte:>4}{is_opex:>5}{iv*100:>7.1f}%{sd:>8.1f}  "
      f"{'sell ' + format(Ks,'.0f') + ' / buy ' + format(Kl,'.0f'):<34}"
      f"{credit:>7.2f}{risk:>7.2f}{pop:>6.1%}{rr:>6.2f}")
    rows.append((e, dte, is_opex, iv, credit, risk, pop, rr, Ks, Kl))

P("\n  credit/risk are PER SHARE (x100 = per contract). POP = P(short strike expires OTM).")
P("  Investment (defined risk) = risk x 100 per contract; max gain = credit x 100.")
if rows:
    best = max(rows, key=lambda r: r[6] * r[7])
    P(f"  Best POP x R/R: {best[0]} sell {best[8]:.0f}/buy {best[9]:.0f} "
      f"POP={best[6]:.1%} R/R={best[7]:.2f} risk=${best[5]*100:.0f}/ctr credit=${best[4]*100:.0f}")

conn.close()
io.open(os.path.join(HERE, "tools", "validate_trades_out.txt"), "w", encoding="utf-8").write("\n".join(OUT))
print("\n".join(OUT))
