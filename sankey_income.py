# -*- coding: utf-8 -*-
"""Income-statement Sankey diagrams (Plotly), for any company.

WHY THIS EXISTS RATHER THAN A LIBRARY
    Searched first: the published work is either generic Sankey tutorials or ledger-specific
    scripts. None of them model an income statement, and none of them check that the flows
    actually balance -- which is the part that matters, because a Sankey will happily render
    numbers that do not add up and look completely convincing while doing it.

THE STRUCTURE MODELLED
    revenue sources ─┐
                     ├─> TOTAL REVENUE ─┬─> GROSS PROFIT ─┬─> OPERATING INCOME ─┬─> NET INCOME
                     ┘                  └─> COST OF REVENUE└─> OPERATING EXPENSES└─> TAXES
    with optional expense breakdown (SG&A, R&D ...) and other income folded into net income.

USAGE
    python sankey_income.py                 # renders the bundled example
    python sankey_income.py --json my.json  # your own figures
    from sankey_income import IncomeStatement, build_sankey
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

try:
    import plotly.graph_objects as go
except ImportError:                                    # pragma: no cover
    sys.exit("plotly is required:  pip install plotly")


# ── Finance palette ──────────────────────────────────────────────────────────────────
# Convention, not decoration: money coming IN and money KEPT are green; money going OUT is
# red. Links are the same hue as their destination at low alpha, so a flow reads as
# "where this money went" at a glance. Grey is reserved for revenue before it is classified
# as either -- revenue is not yet profit, and colouring it green would prejudge the statement.
GREEN, GREEN_L = "#16a34a", "rgba(22,163,74,0.38)"
RED,   RED_L   = "#dc2626", "rgba(220,38,38,0.30)"
GREY,  GREY_L  = "#6b7280", "rgba(156,163,175,0.32)"


def _money(v: float, unit: str = "M", currency: str = "$") -> str:
    """1234.5 -> '$1,235M'. Sankey node labels are cramped; no decimals on millions."""
    return f"{currency}{v:,.0f}{unit}"


def _label(name: str, value: float, yoy: float | None,
           unit: str = "M", currency: str = "$") -> str:
    """Node label: name, amount, and the year-over-year move underneath.

    YoY is the whole reason a reader looks at one of these twice -- the level says how big
    the business is, the change says what is happening to it. Rendered on its own line so
    the number stays readable when nodes crowd.
    """
    out = f"<b>{name}</b><br>{_money(value, unit, currency)}"
    if yoy is not None:
        arrow = "▲" if yoy >= 0 else "▼"
        out += f"<br><span style='font-size:11px'>{arrow} {yoy:+.0f}% Y/Y</span>"
    return out


@dataclass
class IncomeStatement:
    """One period of an income statement, in a single unit (millions by default)."""
    period: str
    company: str
    revenue_sources: dict[str, float]          # e.g. {"US revenue": 1570, "Other": 370}
    cost_of_revenue: float
    operating_expenses: dict[str, float]       # e.g. {"SG&A": 534, "R&D": 193}
    taxes: float
    other_income: float = 0.0
    yoy: dict[str, float] = field(default_factory=dict)   # label -> % change
    unit: str = "M"
    currency: str = "$"

    # ── derived, never passed in: deriving them is what makes the diagram trustworthy ──
    @property
    def total_revenue(self) -> float:
        return sum(self.revenue_sources.values())

    @property
    def gross_profit(self) -> float:
        return self.total_revenue - self.cost_of_revenue

    @property
    def total_opex(self) -> float:
        return sum(self.operating_expenses.values())

    @property
    def operating_income(self) -> float:
        return self.gross_profit - self.total_opex

    @property
    def net_income(self) -> float:
        return self.operating_income + self.other_income - self.taxes

    def validate(self) -> list[str]:
        """Return a list of problems. A Sankey renders unbalanced numbers without complaint,
        so this is the only thing standing between a typo and a confident-looking lie."""
        problems = []
        if self.total_revenue <= 0:
            problems.append("total revenue is zero or negative — nothing to flow")
        if self.cost_of_revenue < 0:
            problems.append("cost of revenue is negative")
        if self.gross_profit < 0:
            problems.append(
                f"gross profit is negative ({_money(self.gross_profit, self.unit, self.currency)})"
                " — a Sankey cannot show a negative flow; this statement needs a waterfall")
        if self.operating_income < 0:
            problems.append(
                f"operating income is negative "
                f"({_money(self.operating_income, self.unit, self.currency)}) — same problem")
        if self.net_income < 0:
            problems.append("net income is negative — Sankey cannot represent it")
        for k, v in {**self.revenue_sources, **self.operating_expenses}.items():
            if v < 0:
                problems.append(f"'{k}' is negative ({v})")
        return problems


def build_sankey(stmt: IncomeStatement, *, width: int = 1180, height: int = 640) -> go.Figure:
    """Build the figure. Raises ValueError if the statement does not balance."""
    problems = stmt.validate()
    if problems:
        raise ValueError("income statement does not balance:\n  - " + "\n  - ".join(problems))

    labels: list[str] = []
    colors: list[str] = []
    idx: dict[str, int] = {}

    def node(key: str, display: str, value: float, color: str) -> int:
        """Register a node ONCE and return its index.

        Every link is (source_index, target_index), and Plotly silently draws a wrong diagram
        if an index is off by one. Allocating indices through this helper -- never by hand --
        is what keeps the mapping correct as nodes are added or removed.
        """
        if key in idx:
            return idx[key]
        idx[key] = len(labels)
        labels.append(_label(display, value, stmt.yoy.get(key), stmt.unit, stmt.currency))
        colors.append(color)
        return idx[key]

    src: list[int] = []
    tgt: list[int] = []
    val: list[float] = []
    lnk: list[str] = []

    def link(a: int, b: int, v: float, color: str) -> None:
        if v > 0:
            src.append(a); tgt.append(b); val.append(v); lnk.append(color)

    # 1. revenue sources -> total revenue        (grey: not yet profit or cost)
    total = node("Total revenue", "Total revenue", stmt.total_revenue, GREY)
    for name, amount in stmt.revenue_sources.items():
        link(node(name, name, amount, GREY), total, amount, GREY_L)

    # 2. total revenue -> gross profit / cost of revenue
    gross = node("Gross profit", "Gross profit", stmt.gross_profit, GREEN)
    link(total, gross, stmt.gross_profit, GREEN_L)
    cogs = node("Cost of revenue", "Cost of revenue", stmt.cost_of_revenue, RED)
    link(total, cogs, stmt.cost_of_revenue, RED_L)

    # 3. gross profit -> operating income / operating expenses
    opinc = node("Operating income", "Operating income", stmt.operating_income, GREEN)
    link(gross, opinc, stmt.operating_income, GREEN_L)
    opex = node("Operating expenses", "Operating expenses", stmt.total_opex, RED)
    link(gross, opex, stmt.total_opex, RED_L)

    # 3b. operating expenses -> their components
    for name, amount in stmt.operating_expenses.items():
        link(opex, node(name, name, amount, RED), amount, RED_L)

    # 4. operating income (+ other income) -> net income / taxes
    net = node("Net income", "Net income", stmt.net_income, GREEN)
    link(opinc, net, stmt.operating_income - stmt.taxes, GREEN_L)
    tax = node("Taxes", "Taxes", stmt.taxes, RED)
    link(opinc, tax, stmt.taxes, RED_L)
    if stmt.other_income > 0:
        # Other income joins at the END: it never passed through gross profit, and routing it
        # earlier would overstate operating performance.
        link(node("Other income", "Other income", stmt.other_income, GREEN),
             net, stmt.other_income, GREEN_L)

    margin = stmt.net_income / stmt.total_revenue * 100
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(pad=26, thickness=17, line=dict(color="rgba(0,0,0,0)", width=0),
                  label=labels, color=colors,
                  hovertemplate="%{label}<br>%{value:,.0f}" + stmt.unit + "<extra></extra>"),
        link=dict(source=src, target=tgt, value=val, color=lnk,
                  hovertemplate="%{source.label} → %{target.label}"
                                "<br><b>%{value:,.0f}" + stmt.unit + "</b><extra></extra>"),
    ))
    fig.update_layout(
        title=dict(text=f"<b>{stmt.company}</b> — how the money flows &nbsp;·&nbsp; "
                        f"<span style='font-size:14px;color:#6b7280'>{stmt.period} &nbsp;·&nbsp; "
                        f"net margin {margin:.0f}%</span>",
                   x=0.02, xanchor="left", font=dict(size=21)),
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", size=12.5, color="#171d24"),
        paper_bgcolor="white", width=width, height=height,
        margin=dict(l=14, r=14, t=74, b=22),
    )
    return fig


# ── Example: Palantir Q2 2026, from the reference figures ────────────────────────────
EXAMPLE = IncomeStatement(
    company="Palantir", period="Q2 2026",
    revenue_sources={"US revenue": 1570, "Other": 370},
    cost_of_revenue=297,
    operating_expenses={"SG&A": 534, "R&D": 193},
    other_income=165,
    taxes=15,
    yoy={"US revenue": 93, "Other": 93, "Total revenue": 93, "Gross profit": 102,
         "Cost of revenue": 54, "Operating income": 239, "Operating expenses": 34,
         "SG&A": 32, "R&D": 43, "Net income": 225, "Taxes": 275, "Other income": 170},
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", help="income statement as JSON (see EXAMPLE for the shape)")
    ap.add_argument("--out", default="income_sankey.html")
    ap.add_argument("--png", help="also write a static PNG (needs kaleido)")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if a.json:
        with open(a.json, encoding="utf-8") as f:
            stmt = IncomeStatement(**json.load(f))
    else:
        stmt = EXAMPLE

    problems = stmt.validate()
    if problems:
        print("REFUSING TO RENDER — the statement does not balance:")
        for p in problems:
            print("   -", p)
        return 1

    u, c = stmt.unit, stmt.currency
    print(f"{stmt.company} · {stmt.period}")
    print(f"  total revenue     {_money(stmt.total_revenue, u, c):>10}"
          f"   = {' + '.join(stmt.revenue_sources)}")
    print(f"  gross profit      {_money(stmt.gross_profit, u, c):>10}"
          f"   ({stmt.gross_profit / stmt.total_revenue * 100:.0f}% margin)")
    print(f"  operating income  {_money(stmt.operating_income, u, c):>10}"
          f"   ({stmt.operating_income / stmt.total_revenue * 100:.0f}% margin)")
    print(f"  net income        {_money(stmt.net_income, u, c):>10}"
          f"   ({stmt.net_income / stmt.total_revenue * 100:.0f}% margin)")

    fig = build_sankey(stmt)
    fig.write_html(a.out, include_plotlyjs="cdn")
    print(f"\nwrote {a.out}")
    if a.png:
        fig.write_image(a.png, scale=2)
        print(f"wrote {a.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
