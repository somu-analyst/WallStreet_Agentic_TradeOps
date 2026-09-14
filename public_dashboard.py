# -*- coding: utf-8 -*-
"""Public-facing showcase dashboard (ID 356) — reads ONLY public_export.db.

WHY THIS FILE IS SEPARATE FROM dashboard.py, NOT A TRIMMED COPY OF IT
    dashboard.py freely reaches into the production database and live vendor APIs wherever
    convenient, which is exactly right for a private single-user tool and exactly wrong here.
    Auditing every function dashboard.py calls, transitively, forever, to make sure none of
    them touch options_change/stock_daily/yfinance is not a real safety strategy - one missed
    call is a real leak (verified the hard way, 2026-09-12: 4 of 5 candidate "safe" pages
    turned out to have live vendor-data calls buried inside them).

    This file is small on purpose and imports NOTHING from telegram_bot_optimized.py or
    dashboard.py. It opens exactly one file, DB_PATH below, and nothing else. The export
    script (tools/export_public_data.py) is the one reviewable choke point that decides what
    is safe to put in that file; this file just displays whatever is already in it.

WHAT'S ON THIS PAGE
    1. 13F institutional holdings - a required public SEC disclosure, not vendor-licensed data.
    2. Signal-accuracy track record, AGGREGATED (hit-rate + edge per model, never a per-ticker
       per-date row) - demonstrates the walk-forward validation discipline without exposing
       what the system said about any specific name on any specific day.

Run: streamlit run public_dashboard.py --server.port 8505
"""
import os
import sqlite3

import pandas as pd
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public_export.db")

st.set_page_config(page_title="Signal Track Record — Public", page_icon="📊", layout="wide")


@st.cache_resource
def _conn():
    # read-only URI connection: this process can never write to the file it reads, even if a
    # future edit to this page introduced a bug that tried to.
    uri = f"file:{os.path.abspath(DB_PATH)}?mode=ro"
    return sqlite3.connect(uri, uri=True, check_same_thread=False)


@st.cache_data(ttl=3600)
def _load_signal_accuracy():
    return pd.read_sql(
        "SELECT * FROM public_signal_accuracy ORDER BY avg_ret_pct DESC", _conn())


@st.cache_data(ttl=3600)
def _load_13f(fund=None):
    if fund:
        return pd.read_sql(
            "SELECT * FROM public_13f WHERE fund=? ORDER BY quarter DESC",
            _conn(), params=(fund,))
    return pd.read_sql(
        "SELECT DISTINCT fund FROM public_13f ORDER BY fund", _conn())


st.title("📊 Signal Track Record")
st.caption(
    "A public showcase: institutional 13F holdings (required SEC disclosure) and this "
    "system's own signal-accuracy track record, aggregated. No live quotes, no option "
    "chains, no per-day trading calls — see the README for what's deliberately excluded "
    "and why."
)

tab_sig, tab_13f = st.tabs(["🎯 Signal Accuracy", "🏆 13F Holdings"])

with tab_sig:
    try:
        df = _load_signal_accuracy()
    except Exception as e:
        st.error(f"Could not load signal accuracy data: {e}")
        df = pd.DataFrame()
    if df.empty:
        st.info("No aggregate signal-accuracy data exported yet.")
    else:
        st.dataframe(
            df.style.format(
                {"hit_rate_pct": "{:.1f}%", "avg_ret_pct": "{:+.3f}%"},
                precision=2, thousands=","),
            use_container_width=True, hide_index=True)
        st.caption(
            "hit_rate_pct = % of resolved fires where the signal's direction matched the "
            "forward move · avg_ret_pct = average directional return per fire · n = resolved "
            "sample size (unresolved/pending fires are excluded, not counted as wrong). "
            "Every number here comes from a walk-forward test, never fit on the data it's "
            "judged on."
        )

with tab_13f:
    try:
        funds = _load_13f()
    except Exception as e:
        st.error(f"Could not load 13F data: {e}")
        funds = pd.DataFrame()
    if funds.empty:
        st.info("No 13F data exported yet.")
    else:
        fund = st.selectbox("Investor", funds["fund"].tolist())
        if fund:
            holdings = _load_13f(fund)
            st.dataframe(holdings, use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Source is a private repository; this page reads a small, separately-exported, "
    "read-only database updated periodically — never the production system."
)
