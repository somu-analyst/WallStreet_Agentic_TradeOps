"""
NYSE_DATA MCP server — exposes the options-intelligence engine over MCP (stdio).

This wraps the running bot's engine (``telegram_bot_optimized``) as a small set of
read-only Model-Context-Protocol tools so any MCP client (Claude Desktop, an agent
framework, etc.) can query the same signals the Telegram bot serves — positions,
premium-selling scans, open-interest flow, capital-flow score, and historical
signal accuracy — without going through Telegram.

Phase 1 tools (all read-only, DB-first):
  - get_positions   : the current book from the ``trades`` table
  - scan_premium    : premium-selling candidates (credit spreads + cash-secured puts)
  - oi_breakdown    : latest-day open-interest change + capital-flow read for a ticker
  - capital_flow    : the /capflow composite score for a ticker
  - backtest_signal : historical hit-rate for a ticker from ``signal_accuracy``

Run:
    python mcp_server.py            # stdio transport (default)

Register in an MCP client, e.g. Claude Desktop ``claude_desktop_config.json``:
    {
      "mcpServers": {
        "nyse-options": {
          "command": "python",
          "args": ["C:/Users/srini/Options_chain_data/NYSE_DATA/mcp_server.py"]
        }
      }
    }

Design notes
------------
* The bot module is imported as a LIBRARY. Its ``run_polling`` loop lives under
  ``if __name__ == "__main__"`` (telegram_bot_optimized.py), so importing it only
  loads the engine — it does not start the Telegram bot.
* stdout is the MCP JSON-RPC channel. The bot prints at import time, so we redirect
  stdout -> stderr *during import* to keep the protocol stream clean.
* All returns pass through ``_json_safe`` (numpy/pandas -> plain JSON; NaN -> null),
  because the engine hands back numpy floats and occasional NaNs that raw JSON chokes on.
* These tools do not WRITE — no trades are opened/closed here. Keep it that way; a
  future phase can add guarded write tools behind an explicit flag.
"""
from __future__ import annotations

import os
import sys
import re
import time
import math
import sqlite3
import logging
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
sys.argv = ["mcp_server"]           # some engine paths read argv; keep it inert
logging.disable(logging.CRITICAL)   # silence the bot's logging on import

# Import the engine with stdout muted — stdio transport owns the real stdout.
with contextlib.redirect_stdout(sys.stderr):
    import telegram_bot_optimized as bot  # noqa: E402  (heavy, one-time ~20s)

import numpy as np                        # noqa: E402
import pandas as pd                       # noqa: E402
from mcp.server.fastmcp import FastMCP    # noqa: E402

mcp = FastMCP("nyse-options-engine")

_DEFAULT_TKS = ["AMD", "GOOG", "NVDA", "SPY", "QQQ"]


# ─────────────────────────── helpers ───────────────────────────
def _json_safe(o):
    """Coerce engine output (numpy/pandas/NaN) into plain JSON-serializable values."""
    if isinstance(o, dict):
        return {str(k): _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_json_safe(v) for v in o]
    if isinstance(o, np.ndarray):
        return [_json_safe(v) for v in o.tolist()]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        o = float(o)
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else round(o, 6)
    if o is None or isinstance(o, (int, str, bool)):
        return o
    try:
        if pd.isna(o):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


def _resolve_tickers(tickers):
    """Uppercase the given list, or fall back to open-position underlyings, or defaults."""
    if tickers:
        return [t.strip().upper() for t in tickers if t and t.strip()]
    try:
        pos = bot._positions_tickers()
    except Exception:
        pos = []
    return pos or list(_DEFAULT_TKS)


# ─────────────────────────── tools ───────────────────────────
@mcp.tool()
def get_positions(status: str = "OPEN", include_stock: bool = True) -> list:
    """Return the current book from the trades table.

    Args:
        status: trade status filter, e.g. "OPEN" or "CLOSED" (case-insensitive).
        include_stock: include STOCK legs (option_type == 'STOCK'). Stock legs are
            linear (strike 0, no expiry) and carry the tax clock; set False to see
            only option legs.

    Returns:
        List of position rows (ticker, strategy, option_type, strike, expiry,
        quantity, entry_price, entry_date, pnl, status, ...).
    """
    conn = bot.get_conn()
    try:
        df = pd.read_sql(
            "SELECT * FROM trades WHERE UPPER(status)=?", conn, params=(status.upper(),)
        )
    finally:
        conn.close()
    if not include_stock and not df.empty and "option_type" in df.columns:
        df = df[df["option_type"].astype(str).str.upper() != "STOCK"]
    return _json_safe(df.to_dict("records"))


@mcp.tool()
def scan_premium(
    tickers: list[str] | None = None,
    strategy: str = "both",
    dte_lo: int = 20,
    dte_hi: int = 45,
    top: int = 8,
) -> dict:
    """Scan for premium-selling candidates.

    Args:
        tickers: underlyings to scan; defaults to your open-position underlyings
            (or a small liquid default set if the book is empty).
        strategy: "spreads" (defined-risk credit spreads), "wheel" (cash-secured
            puts), or "both".
        dte_lo, dte_hi: days-to-expiry window to search.
        top: max rows per strategy.

    Notes:
        POP is derived from ATM-mid implied vol — yfinance per-strike IV is
        unreliable (~1e-5 for OTM), so never trust a per-strike IV here.
    """
    tks = _resolve_tickers(tickers)
    strat = (strategy or "both").lower()
    out: dict = {"tickers": tks, "dte_window": [dte_lo, dte_hi]}
    if strat in ("spreads", "both"):
        try:
            rows = bot._spreads_scan_bot(tks, dte_lo=dte_lo, dte_hi=dte_hi)
            rows = rows if isinstance(rows, list) else []
            out["spreads"] = _json_safe(rows[:top])
        except Exception as e:  # noqa: BLE001
            out["spreads_error"] = str(e)[:200]
    if strat in ("wheel", "both"):
        try:
            rows = bot._wheel_scan_bot(tks, dte_lo=dte_lo, dte_hi=dte_hi)
            rows = rows if isinstance(rows, list) else []
            out["wheel"] = _json_safe(rows[:top])
        except Exception as e:  # noqa: BLE001
            out["wheel_error"] = str(e)[:200]
    return out


@mcp.tool()
def oi_breakdown(ticker: str) -> dict:
    """Latest-day open-interest change + capital-flow read for one ticker.

    Aggregates the most recent ``options_change`` snapshot: net call/put OI change,
    total call/put OI, put/call ratio, and the top strikes by |ΔOI| on each side —
    then attaches the /capflow composite for context.
    """
    tk = ticker.strip().upper()
    conn = bot.get_conn()
    oi: dict = {}
    asof = None
    try:
        row = conn.execute(
            "SELECT MAX(trade_date_now) FROM options_change WHERE ticker=?", (tk,)
        ).fetchone()
        asof = row[0] if row and row[0] else None
        if asof:
            df = pd.read_sql(
                "SELECT strike, expiry_date, change_OI_Call, change_OI_Put, "
                "openInt_Call_now, openInt_Put_now "
                "FROM options_change WHERE ticker=? AND trade_date_now=?",
                conn, params=(tk, asof),
            )
            if not df.empty:
                for c in ("change_OI_Call", "change_OI_Put", "openInt_Call_now", "openInt_Put_now"):
                    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                oi_call = float(df["openInt_Call_now"].sum())
                oi_put = float(df["openInt_Put_now"].sum())
                top_c = df.reindex(df["change_OI_Call"].abs().sort_values(ascending=False).index).head(5)
                top_p = df.reindex(df["change_OI_Put"].abs().sort_values(ascending=False).index).head(5)
                oi = {
                    "call_oi_change": float(df["change_OI_Call"].sum()),
                    "put_oi_change": float(df["change_OI_Put"].sum()),
                    "total_call_oi": oi_call,
                    "total_put_oi": oi_put,
                    "pcr_oi": round(oi_put / oi_call, 3) if oi_call else None,
                    "top_call_strikes": _json_safe(
                        top_c[["strike", "expiry_date", "change_OI_Call", "openInt_Call_now"]].to_dict("records")),
                    "top_put_strikes": _json_safe(
                        top_p[["strike", "expiry_date", "change_OI_Put", "openInt_Put_now"]].to_dict("records")),
                }
    finally:
        conn.close()
    try:
        cf = _json_safe(bot.compute_capflow(tk))
    except Exception as e:  # noqa: BLE001
        cf = {"error": str(e)[:200]}
    return {"ticker": tk, "asof": asof, "oi": oi, "capital_flow": cf}


@mcp.tool()
def capital_flow(ticker: str) -> dict:
    """The /capflow composite for one ticker.

    Blends options $-flow (ΔOI×price, net call vs put), RS-vs-SPY, relative volume,
    and PCR into a single score in roughly [-100, 100]. NOT yet backtested against
    forward returns — educational, not advice.
    """
    try:
        return _json_safe(bot.compute_capflow(ticker.strip().upper()))
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


@mcp.tool()
def backtest_signal(ticker: str, model: str | None = None) -> dict:
    """Historical hit-rate for a ticker's scanner signals, from signal_accuracy.

    Returns per-model accuracy for fired signals that already have a graded outcome:
    hit% (share of correct directional calls), sample N, and average forward return.
    ``correct`` is -1 until graded, so ungraded fires are excluded. Thin N (the DB
    holds ~6 months of graded fires) is statistically weak — treat low-N rows with care.

    Args:
        ticker: underlying symbol.
        model: optional model_name filter (e.g. a specific scanner); omit for all.
    """
    tk = ticker.strip().upper()
    conn = bot.get_conn()
    try:
        q = ("SELECT model_name, signal, "
             "AVG(correct)*100.0 AS hit_pct, COUNT(*) AS n, AVG(actual_ret) AS avg_fwd_ret "
             "FROM signal_accuracy WHERE ticker=? AND correct >= 0 ")
        params: list = [tk]
        if model:
            q += "AND model_name=? "
            params.append(model)
        q += "GROUP BY model_name, signal ORDER BY n DESC"
        df = pd.read_sql(q, conn, params=params)
    finally:
        conn.close()
    return {
        "ticker": tk,
        "graded_groups": int(len(df)),
        "rows": _json_safe(df.to_dict("records")),
        "note": "hit_pct over graded fires only; low n is weak evidence.",
    }


# ─────────────────────── RAG retrieval (search_notes) ───────────────────────
# Local SQLite FTS5 index over the engine's notes corpus — no external API/embeddings.
_RAG_DB = os.path.join(HERE, "rag_index.db")
_RAG_TTL = 600  # rebuild the index if it is older than this many seconds


def _chunk_md(text: str, max_chars: int = 1200) -> list[str]:
    """Split a markdown doc into heading/dated-entry chunks for retrieval."""
    parts = re.split(r"\n(?=#{1,3}\s|\d{4}-\d\d-\d\d)", text)
    out: list[str] = []
    for p in parts:
        p = p.strip("\n")
        if len(p) <= max_chars:
            out.append(p)
        else:
            out.extend(p[i:i + max_chars] for i in range(0, len(p), max_chars))
    return out


def _rag_docs() -> list[tuple]:
    """Collect (source, ref, date, title, body) docs from DB tables + docs/*.md."""
    docs: list[tuple] = []
    conn = bot.get_conn()

    def _q(sql):
        try:
            return list(conn.execute(sql))
        except Exception:  # noqa: BLE001  (table may not exist on some DBs)
            return []

    try:
        for r in _q("SELECT id, event_id, phase, writeup_text, generated_at FROM event_writeups "
                    "WHERE writeup_text IS NOT NULL AND writeup_text != ''"):
            docs.append(("event_writeup", f"ew{r[0]}/evt{r[1]}/{r[2]}", str(r[4] or ""),
                         f"Event {r[1]} · {r[2]}", r[3]))
        for r in _q("SELECT news_id, ticker, headline, summary, source, published_date, sentiment "
                    "FROM news_feed"):
            body = f"[{r[4] or ''} · {r[6] or ''}] {(r[2] or '')} — {(r[3] or '')}".strip()
            docs.append(("news", f"news{r[0]}/{r[1] or ''}", str(r[5] or ""),
                         f"{r[1] or ''}: {r[2] or ''}", body))
        for r in _q("SELECT event_id, name, category, event_date, impact, related_tickers, "
                    "estimate, actual, prior, unit FROM event_catalog"):
            body = (f"{r[1]} ({r[2]}, impact {r[4]}). tickers={r[5]}. "
                    f"est={r[6]} actual={r[7]} prior={r[8]} {r[9] or ''}")
            docs.append(("event_catalog", f"cat{r[0]}", str(r[3] or ""), r[1] or "", body))
        for r in _q("SELECT id, ticker, direction, note, entry_date, status FROM event_journal "
                    "WHERE note IS NOT NULL AND note != ''"):
            docs.append(("journal", f"jrn{r[0]}/{r[1] or ''}", str(r[4] or ""),
                         f"{r[1] or ''} {r[2] or ''} {r[5] or ''}", r[3]))
        for r in _q("SELECT id, kind, label, content, created FROM bookmarks "
                    "WHERE content IS NOT NULL AND content != ''"):
            docs.append(("bookmark", f"bm{r[0]}/{r[1] or ''}", str(r[4] or ""), r[2] or "", r[3]))
    finally:
        conn.close()

    for fn in ("LOG.md", "NEXT.md", "PLAN.md"):
        p = os.path.join(HERE, "docs", fn)
        if not os.path.exists(p):
            continue
        try:
            text = open(p, encoding="utf-8").read()
        except Exception:  # noqa: BLE001
            continue
        for i, chunk in enumerate(_chunk_md(text)):
            if chunk.strip():
                docs.append((f"doc:{fn}", f"{fn}#{i}", "", fn, chunk))
    return docs


def _rag_index(force: bool = False) -> sqlite3.Connection:
    """Open rag_index.db, (re)building the FTS5 table if missing or stale. Returns the conn."""
    rc = sqlite3.connect(_RAG_DB)
    rc.execute("CREATE TABLE IF NOT EXISTS rag_meta(k TEXT PRIMARY KEY, v TEXT)")
    fresh = False
    if not force:
        built = rc.execute("SELECT v FROM rag_meta WHERE k='built_at'").fetchone()
        has = rc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes'").fetchone()
        fresh = bool(built and has and (time.time() - float(built[0])) < _RAG_TTL)
    if not fresh:
        rc.execute("DROP TABLE IF EXISTS notes")
        rc.execute("CREATE VIRTUAL TABLE notes USING fts5("
                   "source, ref, date, title, body, tokenize='porter unicode61')")
        docs = _rag_docs()
        rc.executemany("INSERT INTO notes(source, ref, date, title, body) VALUES (?,?,?,?,?)",
                       [(d[0], d[1], d[2], d[3], d[4] or "") for d in docs])
        rc.execute("INSERT OR REPLACE INTO rag_meta(k,v) VALUES('built_at',?)", (str(time.time()),))
        rc.execute("INSERT OR REPLACE INTO rag_meta(k,v) VALUES('n_docs',?)", (str(len(docs)),))
        rc.commit()
    return rc


def _fts_query(q: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (strip syntax-breaking punctuation)."""
    q2 = re.sub(r'[^\w\s"*]', ' ', q)
    return re.sub(r'\s+', ' ', q2).strip()


@mcp.tool()
def search_notes(query: str, top_k: int = 6, source: str | None = None) -> dict:
    """Full-text search across the engine's notes corpus (RAG retrieval).

    Indexes event write-ups, the news_feed, the macro/earnings event_catalog, trade
    journal + bookmarks, and the docs/*.md continuity logs (LOG/NEXT/PLAN) into a local
    SQLite FTS5 index, rebuilt on demand — no external API or embeddings, fully free and
    offline. Returns the top matches ranked by BM25, each with source, ref, date, title
    and a snippet.

    Args:
        query: free text; FTS5 operators work (e.g. 'semis OR memory', '"max pain"').
        top_k: number of results (default 6).
        source: optional exact source filter (e.g. 'news', 'event_writeup', 'doc:LOG.md').
    """
    q = (query or "").strip()
    if not q:
        return {"query": query, "results": [], "error": "empty query"}
    rc = _rag_index()
    try:
        def run(expr):
            sql = ("SELECT source, ref, date, title, "
                   "snippet(notes, 4, '<<', '>>', ' … ', 12) AS snip, bm25(notes) AS rank "
                   "FROM notes WHERE notes MATCH ? ")
            params: list = [expr]
            if source:
                sql += "AND source = ? "
                params.append(source)
            sql += "ORDER BY rank LIMIT ?"
            params.append(int(top_k))
            return rc.execute(sql, params).fetchall()

        expr = _fts_query(q)
        rows: list = []
        if expr:
            try:
                rows = run(expr)
                if not rows and " " in expr:   # recall fallback: strict AND -> OR of terms
                    rows = run(" OR ".join(expr.split()))
            except Exception as e:  # noqa: BLE001
                return {"query": q, "results": [], "error": f"fts: {str(e)[:150]}"}
        meta = rc.execute("SELECT v FROM rag_meta WHERE k='n_docs'").fetchone()
    finally:
        rc.close()
    results = [{"source": r[0], "ref": r[1], "date": r[2], "title": r[3], "snippet": r[4]}
               for r in rows]
    return {"query": q, "matched_query": expr,
            "corpus_docs": int(meta[0]) if meta else None, "results": results}


if __name__ == "__main__":
    # Default transport is stdio; the client launches this process and speaks JSON-RPC.
    mcp.run()
