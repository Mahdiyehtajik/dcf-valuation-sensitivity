"""
Core discounted-cash-flow model.

Everything is a plain function over a small dataclass of assumptions so that the
same model can be run once (base case), on a grid (sensitivity tables) or
thousands of times (Monte Carlo) without changing any code.

Conventions
-----------
* All money amounts are in the same unit (e.g. EUR millions).
* Year 0 is the last historical year; projections run from year 1 to `years`.
* Free cash flow to the firm (FCFF):
      FCFF = EBIT * (1 - tax) + D&A - capex - change in NWC
* Terminal value uses the Gordon growth formula on year-N FCFF.
* Discounting uses end-of-year convention (mid-year is a one-line option).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Assumptions:
    # --- operating drivers (ratios to revenue unless noted)
    revenue_0: float            # last historical revenue
    revenue_growth: float       # annual growth in the explicit period
    ebit_margin: float          # EBIT / revenue
    tax_rate: float
    da_pct: float               # D&A / revenue
    capex_pct: float            # capex / revenue
    nwc_pct: float              # net working capital / revenue (level, not change)
    # --- discount rate (WACC build-up)
    risk_free: float
    equity_risk_premium: float
    beta: float
    cost_of_debt: float         # pre-tax
    debt_weight: float          # D / (D + E), target structure
    # --- terminal value
    terminal_growth: float
    # --- horizon and bridge
    years: int = 5
    net_debt: float = 0.0
    shares_outstanding: float | None = None
    mid_year: bool = False

    def with_(self, **kwargs) -> "Assumptions":
        """Return a copy with some fields overridden (used by sensitivity runs)."""
        return replace(self, **kwargs)


def cost_of_equity(a: Assumptions) -> float:
    """CAPM: r_e = r_f + beta * ERP."""
    return a.risk_free + a.beta * a.equity_risk_premium


def wacc(a: Assumptions) -> float:
    """Weighted average cost of capital with after-tax cost of debt."""
    re = cost_of_equity(a)
    rd_after_tax = a.cost_of_debt * (1 - a.tax_rate)
    return (1 - a.debt_weight) * re + a.debt_weight * rd_after_tax


def project_cash_flows(a: Assumptions) -> pd.DataFrame:
    """Build the explicit-period forecast, one row per projection year."""
    years = np.arange(1, a.years + 1)
    revenue = a.revenue_0 * (1 + a.revenue_growth) ** years
    revenue_prev = np.concatenate([[a.revenue_0], revenue[:-1]])

    ebit = revenue * a.ebit_margin
    nopat = ebit * (1 - a.tax_rate)
    da = revenue * a.da_pct
    capex = revenue * a.capex_pct
    nwc = revenue * a.nwc_pct
    delta_nwc = nwc - revenue_prev * a.nwc_pct
    fcff = nopat + da - capex - delta_nwc

    return pd.DataFrame(
        {
            "year": years,
            "revenue": revenue,
            "ebit": ebit,
            "nopat": nopat,
            "d_and_a": da,
            "capex": capex,
            "delta_nwc": delta_nwc,
            "fcff": fcff,
        }
    ).set_index("year")


def discount_factors(rate: float, years: int, mid_year: bool = False) -> np.ndarray:
    t = np.arange(1, years + 1, dtype=float)
    if mid_year:
        t = t - 0.5
    return (1 + rate) ** (-t)


def terminal_value(fcff_last: float, rate: float, g: float) -> float:
    """Gordon growth on next year's cash flow. Requires rate > g."""
    if rate <= g:
        raise ValueError(f"WACC ({rate:.2%}) must exceed terminal growth ({g:.2%})")
    return fcff_last * (1 + g) / (rate - g)


def value(a: Assumptions) -> dict:
    """
    Run the full model once and return every intermediate number a reviewer
    would want to check: WACC, PV of the explicit period, PV of terminal value,
    enterprise value, equity value, per-share value and the TV share of EV.
    """
    r = wacc(a)
    cf = project_cash_flows(a)
    df = discount_factors(r, a.years, a.mid_year)

    pv_explicit = float((cf["fcff"].values * df).sum())
    tv = terminal_value(float(cf["fcff"].iloc[-1]), r, a.terminal_growth)
    # TV sits at end of year N regardless of the mid-year convention
    pv_tv = tv * (1 + r) ** (-a.years)
    ev = pv_explicit + pv_tv
    equity = ev - a.net_debt
    per_share = equity / a.shares_outstanding if a.shares_outstanding else None

    return {
        "wacc": r,
        "cost_of_equity": cost_of_equity(a),
        "cash_flows": cf,
        "discount_factors": df,
        "pv_explicit": pv_explicit,
        "terminal_value": tv,
        "pv_terminal_value": pv_tv,
        "enterprise_value": ev,
        "equity_value": equity,
        "value_per_share": per_share,
        "tv_share_of_ev": pv_tv / ev,
    }
