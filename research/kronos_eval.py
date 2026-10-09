"""Kronos evaluation harness — is a K-line foundation model better calibrated than the
lognormal expected move we already compute for free, and does it call direction?

Two halves, two interpreters (the venv has torch, the main interpreter has scipy):
    research/kronos-venv/Scripts/python.exe research/kronos_eval.py smoke
    research/kronos-venv/Scripts/python.exe research/kronos_eval.py run      # resumable
    python research/kronos_eval.py report

LEAKAGE: the weights on Hugging Face were added 2025-06-30 ("add model") and every later
commit on NeoQuasar/Kronos-small and Kronos-Tokenizer-base is README-only (checked
2026-10-09). A bar after that date cannot have been in pretraining, so the default window
only makes forecasts from origins strictly after WEIGHTS_FROZEN. The paper's own stated
cutoff (June 2024) opens a second window, --paper; see PAPER_CUTOFF. --insample is the
memorisation check, never a skill score.

Nothing here is tuned: context, temperature and top_p are the repo defaults / a speed
choice made before any result was seen. That is what lets `report` score it with
`daily_ic` directly rather than through walk_forward.
"""
import os
import sys
import json
import sqlite3
import argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "kronos"))          # vendored repo (gitignored)

DB = os.environ.get("NYSE_DB_PATH",
                    r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
OUT_DB = os.path.join(HERE, "kronos_eval.db")             # research store, never the main DB
TOKENIZER = os.path.join(HERE, "models", "Kronos-Tokenizer-base")
MODEL = os.path.join(HERE, "models", "Kronos-small")
CONTEXT = 512

WEIGHTS_FROZEN = "2025-06-30"
# The paper (arXiv 2508.02739, App. D): "The pre-training data for Kronos extends up to June
# 2024. Consequently, our test period for all tasks begins in July 2024." So three windows,
# each labelled and NEVER pooled: -IS (<= PAPER_CUTOFF, memorisation check), -P (the year the
# paper says is clean but the released weights could in principle have seen), and the default
# (after the weights froze: clean by construction). P scoring far above default = a red flag.
PAPER_CUTOFF = "2024-06-30"
EVAL_CTX = 256          # 1.7s/path vs 3.3s at 512 on this CPU (timed 2026-10-09)
HORIZONS = (5, 10, 21)
PATHS = 16
ORIGIN_STEP = 10        # trading days between forecast origins
UNIVERSE_N = 40
COLS = ["open", "high", "low", "close", "volume"]


def load_bars(ticker, end=None, limit=None):
    """OHLCV from stock_history. Rows missing `open` are dropped. (Until 2026-10-09 the
    daily sync wrote open=NULL on every row since 2025-12-22, so this silently served
    bars months stale; fixed in _sync_history_from_daily.)"""
    con = sqlite3.connect(DB)
    q = ("SELECT trade_date, open, high, low, close, volume FROM stock_history "
         "WHERE ticker=? AND open IS NOT NULL AND close IS NOT NULL")
    p = [ticker.upper()]
    if end:
        q += " AND trade_date<=?"
        p.append(end)
    q += " ORDER BY trade_date"
    df = pd.read_sql(q, con, params=p)
    con.close()
    df["timestamps"] = pd.to_datetime(df["trade_date"])
    if limit:
        df = df.tail(limit).reset_index(drop=True)
    return df


def get_predictor(device="cpu", model_dir=MODEL, tok_dir=TOKENIZER, ctx=CONTEXT):
    from model import Kronos, KronosTokenizer, KronosPredictor
    tok = KronosTokenizer.from_pretrained(tok_dir)
    mdl = Kronos.from_pretrained(model_dir)
    return KronosPredictor(mdl, tok, device=device, max_context=ctx)


# name -> (model dir, tokenizer dir, max context). All weights were added to HF on
# 2025-06-30 / 2025-07-01 with only model-card edits after (checked 2026-10-09).
MODELS = {
    "small": ("Kronos-small", "Kronos-Tokenizer-base", 512),
    "base": ("Kronos-base", "Kronos-Tokenizer-base", 512),
    "mini": ("Kronos-mini", "Kronos-Tokenizer-2k", 2048),
}


def _future_stamps(last_ts, n):
    return pd.Series(pd.bdate_range(last_ts + pd.Timedelta(days=1), periods=n))


def forecast(predictor, df, pred_len, sample_count=1, T=1.0, top_p=0.9):
    """Returns the raw predicted OHLCV frame for the `pred_len` bars after `df`.
    NOTE: Kronos AVERAGES its `sample_count` paths (kronos.py auto_regressive_inference),
    so this is a point forecast. Use forecast_paths() for a distribution."""
    x = df[COLS].reset_index(drop=True)
    x_ts = df["timestamps"].reset_index(drop=True)
    return predictor.predict(df=x, x_timestamp=x_ts, y_timestamp=_future_stamps(x_ts.iloc[-1], pred_len),
                             pred_len=pred_len, T=T, top_p=top_p,
                             sample_count=sample_count, verbose=False)


def forecast_paths(predictor, frames, pred_len, paths, T=1.0, top_p=0.9):
    """Independent sample paths for several equal-length series in ONE batch.
    Each frame is repeated `paths` times with sample_count=1, so nothing is averaged.
    Returns an array (len(frames), paths, pred_len) of predicted closes."""
    xs, xts, yts = [], [], []
    for df in frames:
        x = df[COLS].reset_index(drop=True)
        ts = df["timestamps"].reset_index(drop=True)
        y = _future_stamps(ts.iloc[-1], pred_len)
        xs += [x] * paths
        xts += [ts] * paths
        yts += [y] * paths
    out = predictor.predict_batch(xs, xts, yts, pred_len=pred_len, T=T, top_p=top_p,
                                  sample_count=1, verbose=False)
    closes = np.array([o["close"].to_numpy() for o in out])
    return closes.reshape(len(frames), paths, pred_len)


def smoke(args):
    df = load_bars(args.ticker, limit=CONTEXT)
    print(f"input bars: {len(df)}  {df['trade_date'].iloc[0]} -> {df['trade_date'].iloc[-1]}")
    print(f"last close: {df['close'].iloc[-1]:.2f}")
    pred = get_predictor()
    print("predictor loaded; forecasting...")
    out = forecast(pred, df, args.horizon, sample_count=args.samples)
    print(out.head(args.horizon).to_string())
    return 0


# ---------------------------------------------------------------- out-of-sample run
def _universe(con, n):
    """Most liquid names by dollar volume in the 6 months BEFORE the test window, so the
    pick cannot know which names did well inside it. Must still trade at the end."""
    q = ("SELECT ticker, AVG(close*volume) dv FROM stock_history "
         "WHERE trade_date BETWEEN '2025-01-01' AND ? AND volume>0 AND open IS NOT NULL "
         "GROUP BY ticker HAVING COUNT(*)>100 ORDER BY dv DESC")
    last = con.execute("SELECT MAX(trade_date) FROM stock_history").fetchone()[0]
    live = {r[0] for r in con.execute(
        "SELECT DISTINCT ticker FROM stock_history WHERE trade_date=?", (last,))}
    return [t for t, _ in con.execute(q, (WEIGHTS_FROZEN,)) if t in live][:n]


def _ensure_out(oc):
    oc.execute("""CREATE TABLE IF NOT EXISTS kr_fc (
        origin TEXT, ticker TEXT, h INTEGER, spot0 REAL, real_close REAL,
        sig21 REAL, sig63 REAL, paths TEXT, model TEXT,
        PRIMARY KEY (origin, ticker, h, model))""")
    cols = {r[1] for r in oc.execute("PRAGMA table_info(kr_fc)")}
    if "winmean" not in cols:      # mean close of the context window: measures the pull
        oc.execute("ALTER TABLE kr_fc ADD COLUMN winmean REAL")
    # Volatility race (added 2026-10-09 after Say43/Finance-ETF-Forecasting found Kronos's
    # only real skill is vol, and that vol measured ALONG each path beats the spread BETWEEN
    # paths). All annualised: pvol = median per-path realised vol over the h bars, rv = what
    # actually happened over those h bars, ewma = RiskMetrics(0.94) baseline at the origin.
    for c in ("pvol", "rv", "ewma"):
        if c not in cols:
            oc.execute(f"ALTER TABLE kr_fc ADD COLUMN {c} REAL")
    oc.commit()


def run(args):
    import torch
    torch.set_num_threads(max(1, (os.cpu_count() or 2) - 2))   # leave room for the bot
    con = sqlite3.connect(DB)
    tickers = _universe(con, args.universe)
    bars = {}
    for t in tickers:
        df = pd.read_sql("SELECT trade_date, open, high, low, close, volume FROM stock_history "
                         "WHERE ticker=? ORDER BY trade_date", con, params=(t,))
        df = df.dropna(subset=COLS).reset_index(drop=True)
        df["timestamps"] = pd.to_datetime(df["trade_date"])
        bars[t] = df
    con.close()

    hmax = max(HORIZONS)
    mdir, tdir, mctx = MODELS[args.arch]
    ctx = min(args.ctx, mctx)
    label = args.model or f"{args.arch}-c{ctx}"
    cal = bars["SPY"]["trade_date"] if "SPY" in bars else next(iter(bars.values()))["trade_date"]
    if args.insample:
        # Pre-cutoff window: these bars ARE in pretraining, so this measures MEMORISATION,
        # never skill. Labelled -IS so it can never be pooled with the out-of-sample rows.
        label += "-IS"
        lo, hi = args.insample, PAPER_CUTOFF
        cal = cal[(cal >= lo) & (cal <= hi)].tolist()
        cal = cal[:len(cal) - hmax]           # the realised window must also end pre-cutoff
    elif args.paper:
        label += "-P"
        lo, hi = PAPER_CUTOFF, WEIGHTS_FROZEN
        cal = cal[(cal > lo) & (cal <= hi)].tolist()
        cal = cal[:len(cal) - hmax]
    else:
        lo, hi = WEIGHTS_FROZEN, "9999"
        cal = cal[cal > WEIGHTS_FROZEN].tolist()
        cal = cal[:len(cal) - hmax]
    origins = cal[::ORIGIN_STEP]
    rng = np.random.default_rng(0)
    order = rng.permutation(len(origins))     # partial results stay spread across the window
    if args.max_origins:
        order = order[:args.max_origins]

    oc = sqlite3.connect(OUT_DB)
    _ensure_out(oc)
    done = {r[0] for r in oc.execute("SELECT DISTINCT origin FROM kr_fc WHERE model=?", (label,))}
    pred = get_predictor(model_dir=os.path.join(HERE, "models", mdir),
                         tok_dir=os.path.join(HERE, "models", tdir), ctx=mctx)
    print(f"{label}: universe {len(tickers)}  origins {len(order)} of {len(origins)} "
          f"({origins[0]}..{origins[-1]})  done {len(done)}", flush=True)
    import time
    for k, i in enumerate(order):
        o = origins[i]
        assert (lo <= o <= hi) if args.insample else (lo < o <= hi)
        if o in done:
            continue
        t0 = time.time()
        frames, meta = [], []
        for t, df in bars.items():
            hist = df[df["trade_date"] <= o]
            fut = df[df["trade_date"] > o]
            if len(hist) < ctx + 63 or len(fut) < hmax or hist["trade_date"].iloc[-1] != o:
                continue
            lr = np.diff(np.log(hist["close"].to_numpy()))
            win = hist.tail(ctx)
            w = 0.94 ** np.arange(len(lr[-250:]))[::-1]
            ewma = float(np.sqrt(np.sum(w * lr[-250:] ** 2) / w.sum()))
            meta.append((t, float(hist["close"].iloc[-1]), fut["close"].to_numpy()[:hmax],
                         float(lr[-21:].std()), float(lr[-63:].std()), float(win["close"].mean()),
                         ewma))
            frames.append(win)
        if not frames:
            continue
        cl = forecast_paths(pred, frames, hmax, args.paths)
        rows = []
        ann = np.sqrt(252)
        for j, (t, s0, fut, s21, s63, wm, ewma) in enumerate(meta):
            for h in HORIZONS:
                pth = np.log(np.column_stack([np.full(cl.shape[1], s0), cl[j, :, :h]]))
                pvol = float(np.median(np.diff(pth, axis=1).std(axis=1))) * ann
                rv = float(np.diff(np.log(np.r_[s0, fut[:h]])).std()) * ann
                rows.append((o, t, h, s0, float(fut[h - 1]), s21, s63,
                             json.dumps([round(float(v), 4) for v in cl[j, :, h - 1]]), label, wm,
                             pvol, rv, ewma * ann))
        oc.executemany("INSERT OR REPLACE INTO kr_fc (origin, ticker, h, spot0, real_close, sig21, "
                       "sig63, paths, model, winmean, pvol, rv, ewma) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        oc.commit()
        print(f"[{k + 1}/{len(origins)}] {o}  {len(frames)} names  {time.time() - t0:.0f}s", flush=True)
    oc.close()
    return 0


# ---------------------------------------------------------------- scoring (main python)
def _crps(samples, y):
    """Sample CRPS: E|X-y| - 0.5 E|X-X'|. Lower is better."""
    s = np.asarray(samples)
    return np.mean(np.abs(s - y)) - 0.5 * np.mean(np.abs(s[:, None] - s[None, :]))


def evaluate(model="kronos-small", db=OUT_DB):
    """Every number the report shows, as plain dicts, so the bot/dashboard can render the
    same result. Returns None until there is data."""
    from scipy import stats
    sys.path.insert(0, os.path.join(HERE, "..", "tools"))
    from walkforward import daily_ic

    if not os.path.exists(db):
        return None
    oc = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM kr_fc WHERE model=?", oc, params=(model,))
    oc.close()
    if df.empty:
        return None
    P = np.array([json.loads(p) for p in df["paths"]])
    df["real_ret"] = df["real_close"] / df["spot0"] - 1
    df["pred_ret"] = np.median(P, axis=1) / df["spot0"] - 1
    df["pred_disp"] = (np.quantile(P, .95, axis=1) - np.quantile(P, .05, axis=1)) / df["spot0"]
    df["k_lo90"], df["k_hi90"] = np.quantile(P, .05, axis=1), np.quantile(P, .95, axis=1)
    df["k_lo50"], df["k_hi50"] = np.quantile(P, .25, axis=1), np.quantile(P, .75, axis=1)
    z90, z50 = 1.6449, 0.6745
    sd = df["sig21"] * np.sqrt(df["h"])
    df["b_lo90"], df["b_hi90"] = df["spot0"] * np.exp(-z90 * sd), df["spot0"] * np.exp(z90 * sd)
    df["b_lo50"], df["b_hi50"] = df["spot0"] * np.exp(-z50 * sd), df["spot0"] * np.exp(z50 * sd)
    zq = stats.norm.ppf((np.arange(P.shape[1]) + 0.5) / P.shape[1])   # same count as Kronos
    df["crps_k"] = [_crps(P[i], y) / s for i, (y, s) in enumerate(zip(df["real_close"], df["spot0"]))]
    df["crps_b"] = [_crps(s * np.exp(zq * v), y) / s
                    for y, s, v in zip(df["real_close"], df["spot0"], sd)]

    out = {"model": model, "n_origins": int(df["origin"].nunique()),
           "n_names": int(df["ticker"].nunique()),
           "first": df["origin"].min(), "last": df["origin"].max(), "rows": []}
    for h in HORIZONS:
        d = df[df["h"] == h]
        if d.empty:
            continue
        hit = float(((d["pred_ret"] > 0) == (d["real_ret"] > 0)).mean())
        base = float(max((d["real_ret"] > 0).mean(), 1 - (d["real_ret"] > 0).mean()))
        sig = d.pivot(index="origin", columns="ticker", values="pred_ret").sort_index()
        fwd = d.pivot(index="origin", columns="ticker", values="real_ret").sort_index()
        disp = d.pivot(index="origin", columns="ticker", values="pred_disp").sort_index()
        absr = fwd.abs()
        bvol = d.pivot(index="origin", columns="ticker", values="sig21").sort_index()
        step = max(1, int(np.ceil(h / ORIGIN_STEP)))     # de-overlap: origins are 10d apart
        ic_dir = daily_ic(sig, fwd, step=step)
        ic_vol_k = daily_ic(disp, absr, step=step)
        ic_vol_b = daily_ic(bvol, absr, step=step)
        ls = []
        for o in sig.index[::step]:
            a, f = sig.loc[o], fwd.loc[o]
            m = a.notna() & f.notna()
            if m.sum() < 10:
                continue
            q = a[m].rank(pct=True)
            ls.append(f[m][q >= .8].mean() - f[m][q <= .2].mean())
        ls_t = stats.ttest_1samp(ls, 0) if len(ls) > 3 else None
        cr = d.groupby("origin")[["crps_k", "crps_b"]].mean()
        cr_t = stats.ttest_1samp((cr["crps_k"] - cr["crps_b"]).iloc[::step], 0) if len(cr) > 3 else None
        y = d["real_close"]
        # The window-mean pull (found 2026-10-09): how much of the forecast is just "revert to
        # the context average". Real returns show ~0 here, so a high value is an artifact.
        g = (d["spot0"] / d["winmean"] - 1) if "winmean" in d and d["winmean"].notna().all() else None
        vr = {}
        if "pvol" in d and d["pvol"].notna().sum() > 50:
            dv = d[d["pvol"].notna() & (d["rv"] > 0)]
            rvp = dv.pivot(index="origin", columns="ticker", values="rv").sort_index()
            ql = {}
            for name, col, scale in (("kronos", "pvol", 1.0), ("ewma", "ewma", 1.0),
                                     ("trail21", "sig21", np.sqrt(252))):
                fc = dv.pivot(index="origin", columns="ticker", values=col).sort_index() * scale
                ic = daily_ic(fc, rvp, step=step)
                r2 = (rvp / fc) ** 2
                ql[name] = (r2 - np.log(r2) - 1).mean(axis=1)     # QLIKE per origin
                vr[name] = {"ic": ic["ic"] if ic else None, "ic_t": ic["t"] if ic else None,
                            "qlike": float(ql[name].mean())}
            dq = (ql["kronos"] - ql["ewma"]).iloc[::step].dropna()
            vr["kronos_vs_ewma_t"] = float(stats.ttest_1samp(dq, 0).statistic) if len(dq) > 3 else None
        out["rows"].append({
            "vrace": vr,
            "pull":float(np.corrcoef(g, d["pred_ret"])[0, 1]) if g is not None else None,
            "pull_real": float(np.corrcoef(g, d["real_ret"])[0, 1]) if g is not None else None,
            "h": h, "n": len(d),
            "bias_pred": float(d["pred_ret"].mean()), "bias_real": float(d["real_ret"].mean()),
            "hit": hit, "hit_base": base,
            "ic": ic_dir["ic"] if ic_dir else None, "ic_t": ic_dir["t"] if ic_dir else None,
            "ls": float(np.mean(ls)) if ls else None, "ls_t": float(ls_t.statistic) if ls_t else None,
            "cov90_k": float(((y >= d["k_lo90"]) & (y <= d["k_hi90"])).mean()),
            "cov90_b": float(((y >= d["b_lo90"]) & (y <= d["b_hi90"])).mean()),
            "cov50_k": float(((y >= d["k_lo50"]) & (y <= d["k_hi50"])).mean()),
            "cov50_b": float(((y >= d["b_lo50"]) & (y <= d["b_hi50"])).mean()),
            "crps_k": float(d["crps_k"].mean()), "crps_b": float(d["crps_b"].mean()),
            "crps_t": float(cr_t.statistic) if cr_t else None,
            "volic_k": ic_vol_k["ic"] if ic_vol_k else None,
            "volic_b": ic_vol_b["ic"] if ic_vol_b else None,
        })
    return out


def report(args):
    r = evaluate(args.model)
    if not r:
        print("no forecasts yet - run `run` first")
        return 1
    f = lambda v, p=3: "-" if v is None else f"{v:.{p}f}"
    print(f"{r['model']}: {r['n_origins']} origins x {r['n_names']} names, {r['first']}..{r['last']}"
          f"  (all after weights froze {WEIGHTS_FROZEN})")
    print("h  n     predRet realRet | hit  base  | IC    t     | L/S   t     | cov90 K/B   cov50 K/B   "
          "| CRPS K/B  t(K-B) | volIC K/B   | pull K/real")
    for x in r["rows"]:
        print(f"{x['h']:<2} {x['n']:<5} {x['bias_pred']:+.4f} {x['bias_real']:+.4f} | "
              f"{x['hit']:.2f} {x['hit_base']:.2f} | {f(x['ic'])} {f(x['ic_t'], 2)} | "
              f"{f(x['ls'], 4)} {f(x['ls_t'], 2)} | {x['cov90_k']:.2f}/{x['cov90_b']:.2f}   "
              f"{x['cov50_k']:.2f}/{x['cov50_b']:.2f}   | {x['crps_k']:.4f}/{x['crps_b']:.4f} "
              f"{f(x['crps_t'], 2)} | {f(x['volic_k'])}/{f(x['volic_b'])} | "
              f"{f(x['pull'], 2)}/{f(x['pull_real'], 2)}")
    if any(x["vrace"] for x in r["rows"]):
        print("\nVolatility race (forecast vs realised vol over the horizon; QLIKE lower=better)")
        for x in r["rows"]:
            v = x["vrace"]
            if not v:
                continue
            print(f"h={x['h']:<2} " + "  ".join(
                f"{k}: IC {f(v[k]['ic'])} (t {f(v[k]['ic_t'], 1)}) QLIKE {v[k]['qlike']:.3f}"
                for k in ("kronos", "ewma", "trail21")) +
                f"  | t(QLIKE kronos-ewma) {f(v['kronos_vs_ewma_t'], 2)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "run", "report"])
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--universe", type=int, default=UNIVERSE_N)
    ap.add_argument("--paths", type=int, default=PATHS)
    ap.add_argument("--model", default=None, help="result label (default <arch>-c<ctx>)")
    ap.add_argument("--arch", choices=sorted(MODELS), default="small")
    ap.add_argument("--ctx", type=int, default=EVAL_CTX)
    ap.add_argument("--max-origins", type=int, default=0)
    ap.add_argument("--insample", default=None, metavar="START",
                    help="score the PRE-cutoff window from START (memorisation check)")
    ap.add_argument("--paper", action="store_true",
                    help="score 2024-07..2025-06 (clean per the paper, pre weights-freeze)")
    args = ap.parse_args()
    if args.mode == "report" and not args.model:
        args.model = f"small-c{EVAL_CTX}"
    return {"smoke": smoke, "run": run, "report": report}[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
