# -*- coding: utf-8 -*-
"""Build docs/IDEA_TRACKER.xlsx — one row per idea/question ever raised.

Re-runnable: edit ROWS below (or append) and re-run. Existing user edits in the sheet are
NOT preserved, so treat this script as the source of truth and add new items here.

    python tools/build_idea_tracker.py
"""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "docs", "IDEA_TRACKER.xlsx")

COLS = ["ID", "Date Added", "Raised By", "Category", "Idea / Question",
        "Detail", "Status", "Date Actioned", "Outcome / Evidence", "Commit",
        "Priority", "Next Step"]

# Status vocabulary: DONE | QUEUED | BLOCKED | REJECTED | WITHDRAWN | USER-ACTION
ROWS = [
# ---------------------------------------------------------------- security
(1,"2026-07-31","User","Security","Telegram bot token leaked on GitHub",
 "Secret scanning flagged 5 commits; live token 8407478799 exposed since 2025-12-23",
 "DONE","2026-07-31","Revoked via BotFather; new token installed; bot restarted, 0 auth errors","-","P0","-"),
(2,"2026-07-31","Claude","Security","Second bot @CE448_bot (8018716820) also leaked",
 "Token in 3 public commits; verified STILL ALIVE via getMe",
 "USER-ACTION","","Only BotFather /revoke or /deletebot can close it","-","P0",
 "You: @BotFather -> /revoke or /deletebot -> @CE448_bot"),
(3,"2026-07-31","User","Security","Purge git history / dangling commit 24e2ab8",
 "Asked whether to rewrite history to remove leaked tokens",
 "REJECTED","2026-07-31","filter-repo CANNOT reach dangling objects (not in clone); only GitHub Support can. Token now revoked = dead string. Rewrite would break 592 SHAs for cosmetics","-","P3",
 "Optional: dismiss GitHub alerts as 'revoked'"),
(4,"2026-07-30","Claude","Security","Full-history credential scan (all secret types)",
 "Scan for AWS/Anthropic/OpenAI/GitHub/Slack keys across 592 commits",
 "QUEUED","","Started twice, killed by timeout/parent-shell exit. No result yet","-","P2",
 "Re-run bounded to small files, in background"),
# ---------------------------------------------------------------- methodology
(5,"2026-07-31","Claude","Methodology","Pooled rank-IC t-stat is invalid on this data",
 "Random alpha expressions tested against the harness",
 "DONE","2026-07-31","68-79% of RANDOM alphas passed p<0.05 (best |t|=10.80); correct daily-IC test passes 0%. Cause: overlap + cross-correlation inflate t ~10x","5d0fa27","P0","-"),
(6,"2026-07-30","Claude","Strategy","/debate Technical agent weight 1.0 -> 1.3",
 "Raised on a backtest reporting rank-IC +0.047, t=+7.05",
 "WITHDRAWN","2026-07-31","REVERTED. That t-stat came from the broken pooled method. Correct test: t=+1.04 (5d) / +1.10 (10d) = no edge","5d0fa27","P0","-"),
(7,"2026-07-31","Claude","Methodology","Re-test 3 caveated significance claims",
 "Market Radar 'QQQ corr +0.37', Rotation 'IC +0.14', positioning 'IC +0.03' all used pooled stat",
 "QUEUED","","Caveated in-place in the UI pending re-test under daily-IC","5d0fa27","P1",
 "Re-run each with daily cross-sectional IC"),
(8,"2026-07-31","Claude","Methodology","Walk-forward convention (enforced train/test)",
 "Backtests are done ad-hoc; no enforced standard",
 "QUEUED","","Prerequisite for any alpha-search work","-","P1","-"),
# ---------------------------------------------------------------- rec engine
(9,"2026-07-31","User","Strategy","Backtest all settled recommendations",
 "311 settled recs (236 LIVE, 75 BACKFILL)",
 "DONE","2026-07-31","LIVE = ONE rec_date into ONE expiry = 1 market outcome, no significance possible. EV rule validated: 'trap' group wins MORE (96.8%) but returns 9x LESS (+1.89% vs +16.95%)","a910cb1","P1","-"),
(10,"2026-07-31","Claude","Data","Cash-secured put capital recorded as 0",
 "risk=None for CSP in both scanners -> capital=0 -> removed from every return denominator",
 "DONE","2026-07-31","Fixed at source (risk=(K-credit)*100) in both scanners; 89 historical rows repaired. Also silently understated 'Capital at risk' on the dashboard","5c76fe7","P0","-"),
(11,"2026-07-31","Claude","Analysis","BACKFILL '+136.8% return' claim",
 "Presented as confirming the EV-rule inversion",
 "WITHDRAWN","2026-07-31","Artifact of the CSP capital=0 bug. Restated on real capital: BACKFILL +18.79% vs LIVE +14.84% - they AGREE. No inversion in BACKFILL","5c76fe7","P1","-"),
(12,"2026-07-31","User","Strategy","Exit at 50% of max profit - better?",
 "Standard premium-selling practice; reconstructed from real daily chains, ask-side closes",
 "DONE","2026-07-31","LOSES money: -$19,065 (-0.58% on capital). 73% hit target early. Worst loss IDENTICAL - zero downside protection. Caps winners, does nothing for losers","-","P2",
 "Revisit once a LOSING cohort exists; sim excludes capital-redeployment benefit"),
(13,"2026-07-31","Claude","Strategy","Cash-secured puts are the capital sink",
 "84 CSPs absorb 95.9% of capital, return 1.52%; spreads return ~14.8%",
 "QUEUED","","CSPs collect 1.8% of width against an 18% requirement","a910cb1","P1",
 "Filter or shrink CSPs in the basket sizer"),
(14,"2026-07-31","Claude","Strategy","Basket sizer deploys only 27% of $10k",
 "EV ranking picks cheap spreads, leaves $7,276 idle -> -0.21% after fees vs +21.56% at full deployment",
 "QUEUED","","Deployment dominates selection at this account size","-","P1","Fix the deployment flaw"),
# ---------------------------------------------------------------- regime / hedging
(15,"2026-07-31","User","Strategy","Performance during market falls",
 "Claimed impossible pre-2026-07; user pushed back - correctly",
 "DONE","2026-07-31","I was WRONG. Outcomes depend only on the underlying, and stock_history reaches 1990. A 6-7% index drop = -100% on the spread. SPY 2022 = -179% on risk, erasing 2019+2021 combined","cb53358","P1","-"),
(16,"2026-07-31","User","Strategy","Index vs individual stocks - which is better?",
 "Common window 2020-08 to 2026-07 so every ticker sees 2022",
 "DONE","2026-07-31","NOT SIGNIFICANT (t=1.49, p=0.186). Withdrew a contaminated ranking - 6 tickers lacked pre-2020-07 history and skipped COVID. Within-stock dispersion dwarfs the index/stock gap","cb53358","P1","-"),
(17,"2026-07-31","User","Strategy","Hedge strategies for continuous income",
 "Tail put / collar / vol filter / wide-OTM tested on real crash cycles",
 "DONE","2026-07-31","Tail puts are -EV once REAL skew is priced (SPY 10% OTM = 1.80x ATM IV). TAIL PUT -506%, COLLAR -4016%. WIDE OTM best (+271%). Position sizing is the hedge, not options","d55400d","P1","-"),
(18,"2026-07-31","Claude","Methodology","Flat-vol pricing reversed every hedge conclusion",
 "First run priced all options at one ATM vol",
 "DONE","2026-07-31","Measured real skew in our own chains, refit, and TAIL PUT went +223% -> -506%. Caught before reporting as final","d55400d","P0","-"),
# ---------------------------------------------------------------- external tools
(19,"2026-07-30","User","Research","Review awesome-systematic-trading repo",
 "295 entries across 13 sections tabulated",
 "DONE","2026-07-30","Adopted volest (range-based vol estimators, shipped into /vrp) and the vectorbt pattern (60x faster, identical rank-IC)","e355ef7","P2","-"),
(20,"2026-07-30","User","Research","Private AI quant platforms survey",
 "GitHub API vitals, not marketing pages",
 "DONE","2026-07-30","QuantMuse flagged as a trap: 2,824 stars but 9 commits / 1 contributor. Category already absorbed by this project","c9da836","P2","-"),
(21,"2026-07-31","User","Research","QuantConnect / LEAN for backtests?",
 "Evaluated against limitations this session exposed",
 "DONE","2026-07-31","Worth a RESEARCH trial, not migration. Only thing carrying years of real option quotes w/ bid-ask (AlgoSeek + ThetaData). Will not fix statistical discipline","714cc33","P2",
 "Verify options data cost + coverage start dates"),
(22,"2026-07-31","User","Research","Quantiacs for backtests?",
 "Head-to-head vs QuantConnect, API-verified",
 "REJECTED","2026-07-31","NO options data at all. Toolbox 82 stars, ~7mo stale. Category mismatch for an equity-options book","7fe7c46","P3","-"),
(23,"2026-07-31","User","Research","Proven/backtested income-hedge strategies on GitHub",
 "Searched and verified claims",
 "DONE","2026-07-31","Headline '24.95% CAGR put selling' came from a repo with 0 commits / 0 contributors, and was internally contradictory. Real evidence base is CBOE BXM/PUT indices, not GitHub","-","P2","-"),
# ---------------------------------------------------------------- storage / schema
(24,"2026-07-31","User","Infra","How much disk does the data occupy?",
 "Measured empirically, one real day copied to temp DB",
 "DONE","2026-07-31","70.4 MB/trading-day -> ~18.2 GB/yr. 23 GB free = ~1.3 years runway","-","P1","-"),
(25,"2026-07-31","Claude","Infra","Drop options_daily as a duplicate",
 "Proposed on matching row counts",
 "WITHDRAWN","2026-07-31","WRONG - compared rows not schema. It has 29 extra columns and 20+ live read sites. Renaming would break /oi, ticker detail, expiry breakdown within minutes","-","P1","-"),
(26,"2026-07-31","Claude","Infra","Pre-July rows are irreplaceable",
 "Inverted my own archival advice",
 "DONE","2026-07-31","options_openbb starts 2026-07-02; options_daily starts 2025-12-12; US_data.db is EMPTY. Pre-July rows are the ONLY copy of Dec-Jun and cannot be regenerated","-","P0",
 "Back these up FIRST, delete last"),
(27,"2026-07-31","Claude","Infra","Drop 18 dead columns from options_daily",
 "money_*, vol_rank_*, *_info, chg_oi_* - zero references anywhere",
 "QUEUED","","Measured 16.7% smaller (18.6 -> 15.5 MB/day), ~0.24 GB/yr. Zero read sites change","-","P2",
 "Verify refs, back up schema, ALTER, VACUUM"),
(28,"2026-07-31","User","Infra","Consolidate onto options_openbb only, drop options_daily",
 "Asked whether to migrate fully",
 "QUEUED","","VIABLE - only 3 of 29 cols genuinely needed (company_name/asset_type/load_date); 18 dead, 8 OHLC only 0.4% populated post-July. Catch: pre-July has no options_openbb source, so merging breaks the 'every row has real quotes' invariant","-","P2",
 "Deferred by user - revisit when read paths need refactoring anyway"),
(29,"2026-07-31","Claude","Infra","Parquet archival as standing policy",
 "Parquet is 19x denser (3.7 vs 70 MB/day)",
 "QUEUED","","Would cut ~18 GB/yr to ~4-5 GB/yr; keep ~6mo hot in SQLite","-","P1",
 "Export + VERIFY readback before any delete"),
(30,"2026-07-30","Claude","Data","CBOE quote drifted from chain snapshot",
 "Backfilled underlying_price from a separately-timed quote",
 "DONE","2026-07-31","AAPL 6.4% / AMZN 9.4% off on their earnings evening. Switched to put-call parity off the same snapshot - internally consistent by construction","-","P1","-"),
(31,"2026-07-30","Claude","Infra","SQLite 'database is locked' killed a 734-ticker run",
 "My ad-hoc backfill collided with the EOD capture at 11%",
 "DONE","2026-07-30","busy_timeout=30s added to every writer across all capture scripts","-","P0","-"),
# ---------------------------------------------------------------- research queue
(32,"2026-07-31","Claude","Research","Inverted-edge test",
 "scn_revert / gex / left_skew have 95% CIs entirely BELOW 50%",
 "QUEUED","","A reliably-WRONG signal is as useful as a right one - same as the Vol agent that got sign-flipped. Must use daily-IC method now","-","P1","-"),
(33,"2026-07-31","Claude","Research","Realistic fill modelling",
 "Every backtest except the 50%-exit test assumes mid-price fills",
 "QUEUED","","Highest-value build: makes EXISTING results honest rather than chasing new edge","-","P1","-"),
(34,"2026-07-31","Claude","Research","Dispersion (#14) + skew backtest",
 "skew_snapshot now has 20 dates, past its original gate",
 "QUEUED","","Both unblocked","-","P2","-"),
(35,"2026-07-31","Claude","Research","Formulaic alpha discovery (AlphaGen/Genetic-Alpha)",
 "Initially ranked #1 for highest ceiling",
 "REJECTED","2026-07-31","DOWNGRADED to do-not-build. It is an overfitting machine; on this sample it would find exactly the garbage the random-alpha test just found","-","P3",
 "Revisit only with walk-forward + corrected harness"),
(36,"2026-07-31","Claude","Research","Cross-strategy capital allocator",
 "Size capital across strategies by measured edge",
 "BLOCKED","","~262 graded fires/model gives a 12-point 95% CI - a 44% model is indistinguishable from 50%. Needs n~1000 (~7 months)","24c6a8b","P2","-"),
(37,"2026-07-31","User","Feature","EOD digest like InsiderFinance newsletter",
 "Reviewed each section for feasibility",
 "QUEUED","","4 of 5 sections buildable (News / sector-flow / options plays / unusual-activity ranking). 'AI Noteworthy Trades' needs a real-time options TAPE we do not have","-","P2","-"),
(38,"2026-07-30","User","Feature","Ollama local-LLM narrative synthesis",
 "worldmonitor pattern; free, no API cost",
 "BLOCKED","","Needs Ollama installed - your call","-","P3","-"),
(39,"2026-07-24","User","Feature","NSE / India lane",
 "Endpoints verified (bhavcopy has real delivery %)",
 "QUEUED","","Not blocked, just large: own DB, EOD script, /india command, dashboard section","-","P3","-"),
(40,"2026-07-22","User","Research","Kronos foundation model",
 "Open-source K-line foundation model",
 "BLOCKED","","Pretrained through an unpublished cutoff - backtesting on our history is contaminated and would manufacture a fake edge","-","P3","-"),
]

def build():
    wb = Workbook(); ws = wb.active; ws.title = "Ideas & Questions"
    hdr_fill = PatternFill("solid", fgColor="1F3864")
    hdr_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    status_fill = {
        "DONE":      PatternFill("solid", fgColor="C6EFCE"),
        "QUEUED":    PatternFill("solid", fgColor="FFF2CC"),
        "BLOCKED":   PatternFill("solid", fgColor="F8CBAD"),
        "REJECTED":  PatternFill("solid", fgColor="D9D9D9"),
        "WITHDRAWN": PatternFill("solid", fgColor="FFC7CE"),
        "USER-ACTION": PatternFill("solid", fgColor="BDD7EE"),
    }
    prio_font = {"P0": Font(bold=True, color="9C0006"), "P1": Font(bold=True, color="974706")}

    ws.append(COLS)
    for i, cell in enumerate(ws[1], 1):
        cell.fill = hdr_fill; cell.font = hdr_font; cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for r in ROWS:
        ws.append(list(r))
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(COLS)):
        for c in row:
            c.border = border
            c.alignment = Alignment(vertical="top", wrap_text=True)
        st = row[COLS.index("Status")].value
        if st in status_fill:
            row[COLS.index("Status")].fill = status_fill[st]
            row[COLS.index("Status")].font = Font(bold=True)
        pr = row[COLS.index("Priority")].value
        if pr in prio_font:
            row[COLS.index("Priority")].font = prio_font[pr]

    widths = {"ID":5,"Date Added":12,"Raised By":10,"Category":13,"Idea / Question":34,
              "Detail":42,"Status":12,"Date Actioned":13,"Outcome / Evidence":62,
              "Commit":10,"Priority":8,"Next Step":34}
    for i, c in enumerate(COLS, 1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 18)
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLS))}{ws.max_row}"

    # summary sheet
    s = wb.create_sheet("Summary")
    s.append(["Status", "Count"]);
    counts = {}
    for r in ROWS: counts[r[6]] = counts.get(r[6], 0) + 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1]): s.append([k, v])
    s.append([]); s.append(["Category", "Count"])
    cc = {}
    for r in ROWS: cc[r[3]] = cc.get(r[3], 0) + 1
    for k, v in sorted(cc.items(), key=lambda x: -x[1]): s.append([k, v])
    for row in s.iter_rows():
        for c in row:
            if c.row == 1 or (c.value in ("Category",) and c.column == 1):
                c.font = Font(bold=True)
    s.column_dimensions["A"].width = 16; s.column_dimensions["B"].width = 8

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT}  ({len(ROWS)} rows)")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {k:12s} {v}")

if __name__ == "__main__":
    build()
