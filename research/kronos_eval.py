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
    df = df.dropna(subset=COLS).reset_index(drop=True)    # Kronos rejects any NaN (volume too)
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
def _universe(con, n, start):
    """Most liquid names by dollar volume in the ~6 months BEFORE `start` (the window's first
    origin), trading on `start` itself. Uses nothing at or after the window.

    Audit fix 2026-10-09: this used to rank on 2025-H1 volume and require the name to trade
    TODAY for every window. For the 2023-24 window that picked PLTR (x3.3), MSTR (x11.6),
    NVDA (x7.4) etc. *because* they later got huge -- strong trends, exactly where a
    mean-reverting model looks worst -- which confounded the memorisation comparison. The
    post-freeze universe is unchanged by the fix (checked)."""
    lo = (pd.Timestamp(start) - pd.Timedelta(days=182)).strftime("%Y-%m-%d")
    q = ("SELECT ticker, AVG(close*volume) dv FROM stock_history "
         "WHERE trade_date >= ? AND trade_date < ? AND volume>0 AND open IS NOT NULL "
         "GROUP BY ticker HAVING COUNT(*)>100 ORDER BY dv DESC")
    live = {r[0] for r in con.execute(
        "SELECT DISTINCT ticker FROM stock_history WHERE trade_date=?", (start,))}
    return [t for t, _ in con.execute(q, (lo, start)) if t in live][:n]


def _calendar(con):
    """Trading days (SPY's bars): window bounds and de-overlap distances use real sessions."""
    return [r[0] for r in con.execute(
        "SELECT trade_date FROM stock_history WHERE ticker='SPY' AND close IS NOT NULL "
        "ORDER BY trade_date")]


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
    for c in ("pvol", "rv", "ewma", "pvol_nj"):
        if c not in cols:
            oc.execute(f"ALTER TABLE kr_fc ADD COLUMN {c} REAL")
    if "universe" not in cols:     # which names the run used: audits selection per window
        oc.execute("ALTER TABLE kr_fc ADD COLUMN universe TEXT")
    oc.commit()


def run(args):
    import torch
    torch.set_num_threads(args.threads or max(1, (os.cpu_count() or 2) - 2))  # room for the bot
    con = sqlite3.connect(DB)
    hmax = max(HORIZONS)
    mdir, tdir, mctx = MODELS[args.arch]
    ctx = min(args.ctx, mctx)
    label = args.model or f"{args.arch}-c{ctx}"
    cal = pd.Series(_calendar(con))
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
    tickers = _universe(con, args.universe, origins[0])
    bars = {}
    for t in tickers:
        df = pd.read_sql("SELECT trade_date, open, high, low, close, volume FROM stock_history "
                         "WHERE ticker=? ORDER BY trade_date", con, params=(t,))
        df = df.dropna(subset=COLS).reset_index(drop=True)
        df["timestamps"] = pd.to_datetime(df["trade_date"])
        bars[t] = df
    con.close()
    rng = np.random.default_rng(0)
    order = rng.permutation(len(origins))     # partial results stay spread across the window
    if args.max_origins:
        order = order[:args.max_origins]
    if args.dates:
        # Explicit origins, so configs can be compared on the SAME dates. Audit 2026-10-09:
        # the random subset depends on the window's length, and a calendar change (one SPY
        # row with NULL volume) moved it from 30 to 31 dates and reshuffled 2 of 8 picks.
        want = args.dates.split(",")
        missing = [d_ for d_ in want if d_ not in origins]
        if missing:
            raise SystemExit(f"--dates not on this window's origin grid: {missing}")
        order = [origins.index(d_) for d_ in want]

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
        # Same seed per origin for every config: common random numbers, so a difference
        # between configs is the config, not sampling luck. Also makes reruns reproducible.
        torch.manual_seed(int(o.replace("-", "")))
        cl = forecast_paths(pred, frames, hmax, args.paths)
        rows = []
        ann = np.sqrt(252)
        for j, (t, s0, fut, s21, s63, wm, ewma) in enumerate(meta):
            for h in HORIZONS:
                pth = np.log(np.column_stack([np.full(cl.shape[1], s0), cl[j, :, :h]]))
                steps = np.diff(pth, axis=1)
                pvol = float(np.median(steps.std(axis=1))) * ann
                # Without the spot -> first-predicted-bar step: de-normalisation can make that
                # first bar jump (Kronos issue #26), which would inflate pvol on its own.
                pvol_nj = float(np.median(steps[:, 1:].std(axis=1))) * ann if h > 2 else None
                rv = float(np.diff(np.log(np.r_[s0, fut[:h]])).std()) * ann
                rows.append((o, t, h, s0, float(fut[h - 1]), s21, s63,
                             json.dumps([round(float(v), 4) for v in cl[j, :, h - 1]]), label, wm,
                             pvol, rv, ewma * ann, pvol_nj, ",".join(tickers)[:2000]))
        oc.executemany("INSERT OR REPLACE INTO kr_fc (origin, ticker, h, spot0, real_close, sig21, "
                       "sig63, paths, model, winmean, pvol, rv, ewma, pvol_nj, universe) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        oc.commit()
        print(f"[{k + 1}/{len(origins)}] {o}  {len(frames)} names  {time.time() - t0:.0f}s", flush=True)
    oc.close()
    return 0


# ---------------------------------------------------------------- scoring (main python)
def _crps(samples, y):
    """FAIR sample CRPS: E|X-y| - 1/(2N(N-1)) sum_{i!=j}|Xi-Xj|. Lower is better.
    Audit fix 2026-10-09: the plain estimator divides the spread term by N^2 (counting the
    zero diagonal), which at N=4 understates spread by 25% and penalises wide forecasts."""
    s = np.asarray(samples)
    n = len(s)
    return np.mean(np.abs(s - y)) - np.abs(s[:, None] - s[None, :]).sum() / (2 * n * (n - 1))


def _crps_normal(y, sd):
    """Closed-form CRPS of N(0, sd) at y (log-return space): the lognormal baseline."""
    from scipy import stats
    z = y / sd
    return sd * (z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi))


def _spaced(origins, h, cal_idx):
    """Origins kept so consecutive ones are >= h TRADING days apart: no shared forward days.
    Audit fix 2026-10-09: de-overlap used to slice `[::ceil(h/10)]` on the assumption that
    origins are 10 days apart, but --max-origins takes a random subset, so the gaps vary.
    At h=21 that left <4 origins and every IC came back empty."""
    keep, last = [], None
    for o in sorted(origins):
        i = cal_idx.get(o)
        if i is None:
            continue
        if last is None or i - last >= h:
            keep.append(o)
            last = i
    return keep


def evaluate(model="kronos-small", db=OUT_DB, dates=None):
    """Every number the report shows, as plain dicts, so the bot/dashboard can render the
    same result. Returns None until there is data. `dates` restricts to those origins, so
    configs can be scored on exactly the same days."""
    from scipy import stats
    sys.path.insert(0, os.path.join(HERE, "..", "tools"))
    from walkforward import daily_ic

    if not os.path.exists(db):
        return None
    oc = sqlite3.connect(db)
    df = pd.read_sql("SELECT * FROM kr_fc WHERE model=?", oc, params=(model,))
    oc.close()
    if dates is not None:
        df = df[df["origin"].isin(dates)]
    if df.empty:
        return None
    P = np.array([json.loads(p) for p in df["paths"]])
    df["real_ret"] = df["real_close"] / df["spot0"] - 1
    df["pred_ret"] = np.median(P, axis=1) / df["spot0"] - 1
    df["pred_disp"] = (np.quantile(P, .95, axis=1) - np.quantile(P, .05, axis=1)) / df["spot0"]
    # Everything probabilistic is scored in LOG-RETURN space, Kronos and baseline alike.
    LP = np.log(P / df["spot0"].to_numpy()[:, None])
    ly = np.log(df["real_close"] / df["spot0"]).to_numpy()
    sd = (df["sig21"] * np.sqrt(df["h"])).to_numpy()          # lognormal baseline, zero drift
    # Calibration via PIT (where the outcome falls in the forecast distribution; uniform when
    # calibrated). Audit fix 2026-10-09: band coverage from np.quantile on 4 samples is not a
    # 90% band at all, so "Kronos covers 25% vs baseline 86%" compared unlike things.
    rng = np.random.default_rng(0)
    n = P.shape[1]
    df["pit_k"] = ((LP < ly[:, None]).sum(1) + rng.random(len(df))) / (n + 1)
    df["pit_b"] = stats.norm.cdf(ly / sd)
    df["crps_k"] = [_crps(LP[i], ly[i]) for i in range(len(df))]
    df["crps_b"] = _crps_normal(ly, sd)

    con = sqlite3.connect(DB)
    cal_idx = {d_: i for i, d_ in enumerate(_calendar(con))}
    con.close()
    first, last = df["origin"].min(), df["origin"].max()
    window = ("IN-SAMPLE (memorisation check, not skill)" if model.endswith("-IS") else
              "2024-07..2025-06 (clean per paper; pre weights-freeze)" if model.endswith("-P") else
              f"after weights froze {WEIGHTS_FROZEN} (clean by construction)")
    out = {"model": model, "n_origins": int(df["origin"].nunique()),
           "n_names": int(df["ticker"].nunique()), "window": window, "n_paths": n,
           "first": first, "last": last, "rows": []}
    for h in HORIZONS:
        d = df[df["h"] == h]
        if d.empty:
            continue
        hit = float(((d["pred_ret"] > 0) == (d["real_ret"] > 0)).mean())
        base = float(max((d["real_ret"] > 0).mean(), 1 - (d["real_ret"] > 0).mean()))
        keep = _spaced(d["origin"].unique(), h, cal_idx)
        di = d[d["origin"].isin(keep)]                         # non-overlapping origins only
        sig = di.pivot(index="origin", columns="ticker", values="pred_ret").sort_index()
        fwd = di.pivot(index="origin", columns="ticker", values="real_ret").sort_index()
        disp = di.pivot(index="origin", columns="ticker", values="pred_disp").sort_index()
        absr = fwd.abs()
        bvol = di.pivot(index="origin", columns="ticker", values="sig21").sort_index()
        step = 1
        ic_dir = daily_ic(sig, fwd, step=step)
        ic_vol_k = daily_ic(disp, absr, step=step)
        ic_vol_b = daily_ic(bvol, absr, step=step)
        ls = []
        for o in sig.index:
            a, f = sig.loc[o], fwd.loc[o]
            m = a.notna() & f.notna()
            if m.sum() < 10:
                continue
            q = a[m].rank(pct=True)
            ls.append(f[m][q >= .8].mean() - f[m][q <= .2].mean())
        ls_t = stats.ttest_1samp(ls, 0) if len(ls) > 3 else None
        cr = di.groupby("origin")[["crps_k", "crps_b"]].mean()
        cr_t = stats.ttest_1samp(cr["crps_k"] - cr["crps_b"], 0) if len(cr) > 3 else None
        # The window-mean pull (found 2026-10-09): how much of the forecast is just "revert to
        # the context average". Real returns show ~0 here, so a high value is an artifact.
        g = (d["spot0"] / d["winmean"] - 1) if "winmean" in d and d["winmean"].notna().all() else None
        vr = {}
        if "pvol" in di and di["pvol"].notna().sum() > 50:
            dv = di[di["pvol"].notna() & (di["rv"] > 0)]
            rvp = dv.pivot(index="origin", columns="ticker", values="rv").sort_index()
            ql = {}
            racers = [("kronos", "pvol", 1.0), ("ewma", "ewma", 1.0), ("trail21", "sig21", np.sqrt(252))]
            if "pvol_nj" in dv and dv["pvol_nj"].notna().all():
                racers.insert(1, ("kronos_nj", "pvol_nj", 1.0))
            for name, col, scale in racers:
                fc = dv.pivot(index="origin", columns="ticker", values=col).sort_index() * scale
                ic = daily_ic(fc, rvp, step=step)
                r2 = (rvp / fc) ** 2
                ql[name] = (r2 - np.log(r2) - 1).mean(axis=1)     # QLIKE per origin
                vr[name] = {"ic": ic["ic"] if ic else None, "ic_t": ic["t"] if ic else None,
                            "qlike": float(ql[name].mean())}
            dq = (ql["kronos"] - ql["ewma"]).dropna()
            vr["kronos_vs_ewma_t"] = float(stats.ttest_1samp(dq, 0).statistic) if len(dq) > 3 else None
        out["rows"].append({
            "vrace": vr,
            "pull":float(np.corrcoef(g, d["pred_ret"])[0, 1]) if g is not None else None,
            "pull_real": float(np.corrcoef(g, d["real_ret"])[0, 1]) if g is not None else None,
            "h": h, "n": len(d), "n_indep": len(keep),
            "bias_pred": float(d["pred_ret"].mean()), "bias_real": float(d["real_ret"].mean()),
            "hit": hit, "hit_base": base,
            "ic": ic_dir["ic"] if ic_dir else None, "ic_t": ic_dir["t"] if ic_dir else None,
            "ls": float(np.mean(ls)) if ls else None, "ls_t": float(ls_t.statistic) if ls_t else None,
            "cov90_k": float(((d["pit_k"] - .5).abs() < .45).mean()),
            "cov90_b": float(((d["pit_b"] - .5).abs() < .45).mean()),
            "cov50_k": float(((d["pit_k"] - .5).abs() < .25).mean()),
            "cov50_b": float(((d["pit_b"] - .5).abs() < .25).mean()),
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
    print(f"{r['model']}: {r['n_origins']} origins x {r['n_names']} names x {r['n_paths']} paths, "
          f"{r['first']}..{r['last']}  [{r['window']}]")
    print("h  n    ind predRet realRet | hit  base  | IC    t     | L/S   t     | cov90 K/B   cov50 K/B   "
          "| CRPS K/B  t(K-B) | volIC K/B   | pull K/real")
    print("   (ind = non-overlapping origins behind IC / L-S / CRPS t; cov = PIT-based, nominal .90/.50;"
          " CRPS in log-return units)")
    for x in r["rows"]:
        print(f"{x['h']:<2} {x['n']:<4} {x['n_indep']:<3} {x['bias_pred']:+.4f} {x['bias_real']:+.4f} | "
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
                for k in ("kronos", "kronos_nj", "ewma", "trail21") if k in v) +
                f"  | t(QLIKE kronos-ewma) {f(v['kronos_vs_ewma_t'], 2)}")
    return 0


COMPARE = ["small-c64", "small-c128", "small-c256", "small-c512", "base-c256", "mini-c1024",
           "small-c256-P", "small-c256-IS"]


def compare(args):
    """One line per config. Post-freeze configs are scored on the origins they ALL share;
    the -P / -IS windows are separate periods and are shown as-is, never pooled."""
    oc = sqlite3.connect(OUT_DB)
    have = {m: {r[0] for r in oc.execute("SELECT DISTINCT origin FROM kr_fc WHERE model=?", (m,))}
            for m in COMPARE}
    oc.close()
    oos = [m for m in COMPARE if have[m] and not m.endswith(("-P", "-IS"))]
    common = sorted(set.intersection(*(have[m] for m in oos))) if oos else []
    print(f"post-freeze configs scored on {len(common)} shared origins: {common}")
    f = lambda v, p=2: "  -  " if v is None else f"{v:+.{p}f}"
    print(f"{'config':<15}{'h':>3} {'pull':>6} {'hit-base':>9} {'IC':>6} {'t':>6} {'CRPS K/B':>9} "
          f"{'cov90':>6} {'cov50':>6} | {'volQLIKE K/E':>13} {'t':>6}")
    for m in COMPARE:
        if not have[m]:
            continue
        r = evaluate(m, dates=None if m.endswith(("-P", "-IS")) else common)
        if not r:
            continue
        for x in r["rows"]:
            v = x["vrace"] or {}
            q = (f"{v['kronos']['qlike']:.2f}/{v['ewma']['qlike']:.2f}" if "kronos" in v else "     -")
            print(f"{m:<15}{x['h']:>3} {f(x['pull']):>6} {x['hit'] - x['hit_base']:>+9.2f} "
                  f"{f(x['ic'], 3):>6} {f(x['ic_t']):>6} {x['crps_k'] / x['crps_b']:>9.2f} "
                  f"{x['cov90_k']:>6.2f} {x['cov50_k']:>6.2f} | {q:>13} "
                  f"{f(v.get('kronos_vs_ewma_t')):>6}")
    print("pull: corr(forecast, spot/window-mean - 1), real returns show ~0 | CRPS K/B > 1 = worse "
          "than lognormal | cov nominal .90/.50 | volQLIKE lower = better, t > 2 = Kronos worse")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "run", "report", "compare"])
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--samples", type=int, default=1)
    ap.add_argument("--universe", type=int, default=UNIVERSE_N)
    ap.add_argument("--paths", type=int, default=PATHS)
    ap.add_argument("--model", default=None, help="result label (default <arch>-c<ctx>)")
    ap.add_argument("--arch", choices=sorted(MODELS), default="small")
    ap.add_argument("--ctx", type=int, default=EVAL_CTX)
    ap.add_argument("--max-origins", type=int, default=0)
    ap.add_argument("--dates", default=None,
                    help="comma-separated origin dates to run (overrides --max-origins)")
    ap.add_argument("--threads", type=int, default=0,
                    help="torch threads (default cores-2; set it on a 2-core VM)")
    ap.add_argument("--insample", default=None, metavar="START",
                    help="score the PRE-cutoff window from START (memorisation check)")
    ap.add_argument("--paper", action="store_true",
                    help="score 2024-07..2025-06 (clean per the paper, pre weights-freeze)")
    args = ap.parse_args()
    if args.mode == "report" and not args.model:
        args.model = f"small-c{EVAL_CTX}"
    return {"smoke": smoke, "run": run, "report": report, "compare": compare}[args.mode](args)


if __name__ == "__main__":
    raise SystemExit(main())
