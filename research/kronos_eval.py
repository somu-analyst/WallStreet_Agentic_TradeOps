"""Kronos evaluation harness — is a K-line foundation model better calibrated than the
lognormal expected move we already compute for free?

Run with the isolated venv, NOT the bot's interpreter:
    research/kronos-venv/Scripts/python.exe research/kronos_eval.py smoke
    research/kronos-venv/Scripts/python.exe research/kronos_eval.py eval

LEAKAGE WARNING: Kronos was pretrained on historical market data through an unpublished
cutoff. Scoring it on bars it may have memorised manufactures a fake edge. `eval` therefore
takes an --after date and refuses to score anything at or before it.
"""
import os
import sys
import sqlite3
import argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "kronos"))          # vendored repo (gitignored)

DB = os.environ.get("NYSE_DB_PATH",
                    r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db")
TOKENIZER = os.path.join(HERE, "models", "Kronos-Tokenizer-base")
MODEL = os.path.join(HERE, "models", "Kronos-small")
CONTEXT = 512


def load_bars(ticker, end=None, limit=None):
    """OHLCV from stock_history. Rows missing `open` are dropped — the two most recent
    captures (2026-07-20/21) have a NULL open for every ticker, a derive-lane gap."""
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


def get_predictor(device="cpu"):
    from model import Kronos, KronosTokenizer, KronosPredictor
    tok = KronosTokenizer.from_pretrained(TOKENIZER)
    mdl = Kronos.from_pretrained(MODEL)
    return KronosPredictor(mdl, tok, device=device, max_context=CONTEXT)


def forecast(predictor, df, pred_len, sample_count=1, T=1.0, top_p=0.9):
    """Returns the raw predicted OHLCV frame for the `pred_len` bars after `df`."""
    x = df[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
    x_ts = df["timestamps"].reset_index(drop=True)
    # daily bars: project business days forward for the target stamps
    y_ts = pd.Series(pd.bdate_range(df["timestamps"].iloc[-1] + pd.Timedelta(days=1),
                                    periods=pred_len))
    return predictor.predict(df=x, x_timestamp=x_ts, y_timestamp=y_ts,
                             pred_len=pred_len, T=T, top_p=top_p,
                             sample_count=sample_count, verbose=False)


def smoke(args):
    df = load_bars(args.ticker, limit=CONTEXT)
    print(f"input bars: {len(df)}  {df['trade_date'].iloc[0]} -> {df['trade_date'].iloc[-1]}")
    print(f"last close: {df['close'].iloc[-1]:.2f}")
    pred = get_predictor()
    print("predictor loaded; forecasting...")
    out = forecast(pred, df, args.horizon, sample_count=args.samples)
    print(out.head(args.horizon).to_string())
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke"])
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--samples", type=int, default=1)
    args = ap.parse_args()
    return smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
