#!/usr/bin/env python3
"""
Telegram bot hooks for event writeups — import from telegram_bot_optimized.py.

Scheduled times (New York wall clock, so they hold across DST):
  8:25 AM  — pre-event brief (T-5 min before typical 8:30 releases)
  9:35 AM  — post-open reaction writeup
  10:05 AM — post-event follow-up (30 min after 9:30 open)
  2:35 PM  — post-FOMC writeup (decision at 2:00 PM)
  Every 15 min during market hours — anomaly scan (deduped)

A post writeup covers only events released within the last POST_WINDOW_MIN minutes, so an
event is never written up before it happens and a morning release isn't re-sent at 2:35.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

import os as _os  # PRIMARY DB = OpenBB (matches the bot); override via env NYSE_DB_PATH
DB_PATH = _os.environ.get("NYSE_DB_PATH") or r"C:\Users\srini\Options_chain_data\US_data_OpenBB.db"

ET = ZoneInfo("America/New_York")
POST_WINDOW_MIN = 120   # a post writeup covers releases from the last 2 hours


def _ensure_dedup(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_dedup (
            alert_date TEXT NOT NULL,
            grp_key    TEXT NOT NULL,
            atype      TEXT NOT NULL,
            PRIMARY KEY (alert_date, grp_key, atype)
        )
    """)
    conn.commit()


def _already_sent(conn, today_str, grp_key, atype) -> bool:
    try:
        conn.execute(
            "INSERT INTO alert_dedup (alert_date, grp_key, atype) VALUES (?, ?, ?)",
            (today_str, grp_key, atype),
        )
        conn.commit()
        return False
    except sqlite3.IntegrityError:
        return True


def _in_market_hours(now_et) -> bool:
    """9:25 AM - 4:00 PM New York time. This used to compare UTC against a fixed 14:25-21:00,
    which is 9:25-4:00 only in winter: for the eight months of EDT it gated 10:25 AM-5:00 PM,
    and every ET time in this file was derived as UTC-5, an hour off (same bug as ID 249)."""
    if now_et.weekday() >= 5:
        return False
    hm = now_et.hour * 60 + now_et.minute
    return 9 * 60 + 25 <= hm <= 16 * 60


async def event_pre_brief_alert(ctx):
    """8:25 AM ET — pre-event brief for today's macro releases."""
    from event_writeup_engine import EventWriteupEngine

    now_et = datetime.now(ET)
    today_str = now_et.date().isoformat()

    engine = EventWriteupEngine()
    events = engine.events_today()
    if not events:
        return

    # Import bot helpers lazily
    from telegram_bot_optimized import get_conn, load_creds, H

    conn = get_conn()
    try:
        _ensure_dedup(conn)
        _, chat_id = load_creds()
        for ev in events:
            if _already_sent(conn, today_str, ev.event_id, "event_pre"):
                continue
            text = engine.generate_writeup(ev.event_id, phase="pre", save=True)
            html = engine.format_telegram(text)
            await ctx.bot.send_message(chat_id=chat_id, text=html, parse_mode=H)
    except Exception as e:
        log.warning(f"event_pre_brief_alert failed: {e}")
    finally:
        conn.close()


async def event_post_writeup_alert(ctx):
    """Post-release / post-open writeup."""
    from event_writeup_engine import EventWriteupEngine

    now_et = datetime.now(ET)
    if not _in_market_hours(now_et):
        return
    today_str = now_et.date().isoformat()

    from telegram_bot_optimized import get_conn, load_creds, H

    engine = EventWriteupEngine()
    from event_writeup_engine import released_minutes_ago
    # Only releases that have happened, and recently. Before, anything dated today got a
    # "Markets reacting to ..." writeup at 9:35/10:05 -- including a 2:00 PM FOMC decision.
    events = []
    for ev in engine.events_today():
        mins = released_minutes_ago(ev, now_et)
        if mins is not None and 0 <= mins <= POST_WINDOW_MIN:
            events.append(ev)
    if not events:
        anomalies = engine.detect_intraday_anomalies()
        if not anomalies:
            return
        from event_writeup_engine import MarketEvent
        ev = MarketEvent(
            event_id=f"{today_str}_intraday_anomaly",
            name="Intraday Market Anomaly",
            category="Market Structure",
            event_date=today_str,
            release_time=now_et.strftime("%H:%M"),
            impact="HIGH",
            source="detector",
        )
        engine._upsert_event(ev)
        events = [ev]

    conn = get_conn()
    try:
        _ensure_dedup(conn)
        _, chat_id = load_creds()
        atype = f"event_post_{now_et.hour:02d}{now_et.minute:02d}"
        for ev in events:
            key = f"{ev.event_id}_{atype}"
            if _already_sent(conn, today_str, key, "event_post"):
                continue
            text = engine.generate_writeup(ev.event_id, phase="post", save=True)
            html = engine.format_telegram(text)
            await ctx.bot.send_message(chat_id=chat_id, text=html, parse_mode=H)
    except Exception as e:
        log.warning(f"event_post_writeup_alert failed: {e}")
    finally:
        conn.close()


async def event_anomaly_scan(ctx):
    """Lightweight anomaly scan during market hours — only alerts on HIGH/CRITICAL."""
    from event_writeup_engine import EventWriteupEngine

    now_et = datetime.now(ET)
    if not _in_market_hours(now_et):
        return
    today_str = now_et.date().isoformat()

    from telegram_bot_optimized import get_conn, load_creds, H

    engine = EventWriteupEngine()
    alerts = engine.detect_intraday_anomalies()
    severe = [a for a in alerts if a.get("severity") in ("HIGH", "CRITICAL")]
    if not severe:
        return

    # RELEVANCE GATE (user 2026-08-07: "SNDK +9.3% keeps coming, trim it").
    # A 5% intraday move is common across a 700-name universe, so alerting on all of them
    # is noise that trains you to ignore the channel. Alert on names you actually hold or
    # watch, plus the index/vol complex which is market-wide context. Anything else has to
    # clear a much higher bar to interrupt.
    _RELEVANT_ALWAYS = {"SPY", "QQQ", "IWM", "DIA", "^VIX", "VIX"}
    _OTHER_MIN_MOVE = 12.0          # unheld name: only a genuinely exceptional move
    try:
        _c0 = get_conn()
        try:
            _mine = {r[0] for r in _c0.execute(
                "SELECT DISTINCT UPPER(ticker) FROM trades WHERE status='OPEN'")}
            try:
                _mine |= {r[0] for r in _c0.execute(
                    "SELECT DISTINCT UPPER(ticker) FROM watchlist")}
            except Exception:
                pass
        finally:
            _c0.close()
    except Exception:
        _mine = set()
    _keep = []
    for _a in severe:
        _t = str(((_a.get("data") or {}).get("ticker") or "")).upper()
        if not _t:
            _keep.append(_a); continue                     # market-wide alert, always keep
        if _t in _mine or _t in _RELEVANT_ALWAYS:
            _keep.append(_a); continue
        if abs(float((_a.get("data") or {}).get("chg_pct") or 0)) >= _OTHER_MIN_MOVE:
            _keep.append(_a)
    if not _keep:
        log.info("anomaly: %d severe, none relevant (held/watched/index or >=%.0f%%)",
                 len(severe), _OTHER_MIN_MOVE)
        return
    severe = _keep

    conn = get_conn()
    try:
        _ensure_dedup(conn)
        _, chat_id = load_creds()
        from telegram_bot_optimized import _pipe_table, make_line_chart
        for a in severe:
            # Dedup on type+TICKER, never the description: it reads "SNDK +9.3% from open",
            # so the percentage was IN the key and every tick minted a fresh one -- the same
            # name re-alerted all day (user 2026-08-07). One alert per name per day.
            _dk = str(((a.get("data") or {}).get("ticker") or "")).upper()
            key = a["type"] + "_" + (_dk or (a.get("description") or "")[:30])
            if _already_sent(conn, today_str, key, "anomaly"):
                continue
            msg = f"⚠️ <b>MARKET ANOMALY</b>\n\n{a['description']}"
            _d = a.get("data") or {}
            _tk = _d.get("ticker")
            # Ticker shocks: PURE text/number table — no emoji anywhere inside
            # the <pre> block. Every working table elsewhere in the bot either
            # gives emoji its OWN column on EVERY row, or leaves it out; mixing
            # emoji + text in a single cell (e.g. "🟢 Move") renders wider than
            # the width math predicts on some Telegram clients and breaks pipe
            # alignment (user flagged twice, 2026-07-17). Direction now goes in
            # the plain-text title line instead, where alignment doesn't matter.
            if a["type"] == "TICKER_SHOCK" and _tk and _d.get("now_px"):
                _chg = float(_d.get("chg_pct") or 0)
                # No pure green/red arrow glyph exists in Unicode (🔺🔻🔼🔽 are
                # all red, no green counterpart; ⬆️⬇️ aren't colored). 📈/📉 is
                # the closest real match — genuinely green-up/red-down by
                # design, single glyph, safe width. Decided 2026-07-17.
                _dir_word = "📈" if _chg >= 0 else "📉"
                _rows = [("Now", f"${float(_d['now_px']):.2f}")]
                _pc = _d.get("prev_close")
                if _pc:
                    _rows.append(("PrevCls", f"${float(_pc):.2f}"))
                _rows.append(("Open", f"${float(_d.get('day_open') or 0):.2f}"))
                _rows.append(("Move", f"{_chg:+.1f}%"))
                _mc = _d.get("mcap_impact")
                if _mc:
                    _rows.append(("MCapΔ", f"{'-' if _mc < 0 else '+'}${abs(_mc)/1e9:.1f}B"))
                msg = (f"⚠️ <b>MARKET ANOMALY — {_tk} {_dir_word} {_chg:+.1f}%</b>\n\n"
                       + _pipe_table(("Metric", "Value"), _rows, right_cols={1},
                                     legend="move measured vs TODAY's open"))
            await ctx.bot.send_message(chat_id=chat_id, text=msg, parse_mode=H)
            if a["type"] == "TICKER_SHOCK" and _tk:
                try:
                    _img = make_line_chart(_tk, days=365)
                    await ctx.bot.send_photo(chat_id=chat_id, photo=_img,
                                             caption=f"{_tk} — last 1 year")
                except Exception:
                    log.debug("anomaly mini chart failed", exc_info=True)
    except Exception as e:
        log.warning(f"event_anomaly_scan failed: {e}")
    finally:
        conn.close()


def register_event_writeup_jobs(job_queue, log_fn=None):
    """Call from telegram_bot main() after job_queue is created."""
    from datetime import time as dt_time

    if not job_queue:
        return
    try:
        import sys
        import os
        lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)

        # New York wall-clock times (ID 249). A naive dt_time is read as UTC, so 13:25 was
        # 8:25 AM only in winter -- in summer the "pre" brief ran at 9:25, after the 8:30
        # releases it previews.
        job_queue.run_daily(event_pre_brief_alert, time=dt_time(8, 25, 0, tzinfo=ET),
                            name="event_pre_0825")
        for hh, mm in ((9, 35), (10, 5), (14, 35)):    # 14:35 = 35 min after an FOMC decision
            job_queue.run_daily(event_post_writeup_alert, time=dt_time(hh, mm, 0, tzinfo=ET),
                                name=f"event_post_{hh:02d}{mm:02d}")
        job_queue.run_repeating(event_anomaly_scan, interval=900, first=120)
        if log_fn:
            log_fn.info("Scheduled event writeup jobs (ET: pre 8:25, post 9:35/10:05/14:35, anomaly 15m)")
    except Exception as e:
        if log_fn:
            log_fn.warning(f"Could not register event writeup jobs: {e}")
