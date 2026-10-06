"""
Run the full analysis on a case file and write every output to outputs/.

    python run.py                     # base case
    python run.py data/sap.json       # a case produced by scripts/fetch_financials.py
"""
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from dcf import Assumptions, value, tornado, two_way_table, monte_carlo, summarise, write_workbook

case = Path(sys.argv[1] if len(sys.argv) > 1 else "data/base_case.json")
raw = {k: v for k, v in json.load(open(case)).items() if not k.startswith("_")}
a = Assumptions(**raw)
out = Path("outputs"); out.mkdir(exist_ok=True)

# ---- 1. Base case
res = value(a)
print(f"WACC               {res['wacc']:.2%}")
print(f"PV explicit        {res['pv_explicit']:,.1f}")
print(f"PV terminal value  {res['pv_terminal_value']:,.1f}  ({res['tv_share_of_ev']:.0%} of EV)")
print(f"Enterprise value   {res['enterprise_value']:,.1f}")
print(f"Equity value       {res['equity_value']:,.1f}")
if res["value_per_share"]:
    print(f"Value per share    {res['value_per_share']:,.2f}")
res["cash_flows"].round(1).to_csv(out / "cash_flows.csv")

# ---- 2. Tornado: each driver +/- a realistic band
shocks = {
    "revenue_growth": (a.revenue_growth - 0.02, a.revenue_growth + 0.02),
    "ebit_margin": (a.ebit_margin - 0.02, a.ebit_margin + 0.02),
    "terminal_growth": (a.terminal_growth - 0.01, a.terminal_growth + 0.01),
    "beta": (a.beta - 0.2, a.beta + 0.2),
    "equity_risk_premium": (a.equity_risk_premium - 0.01, a.equity_risk_premium + 0.01),
    "capex_pct": (a.capex_pct - 0.01, a.capex_pct + 0.01),
    "tax_rate": (a.tax_rate - 0.03, a.tax_rate + 0.03),
    "nwc_pct": (a.nwc_pct - 0.02, a.nwc_pct + 0.02),
}
tor = tornado(a, shocks)
tor.round(4).to_csv(out / "tornado.csv")
base_ev = res["enterprise_value"]
fig, ax = plt.subplots(figsize=(8, 4.5))
y = np.arange(len(tor))[::-1]
ax.barh(y, tor["value_at_high"] - base_ev, left=base_ev, color="#2e75b6", label="high input")
ax.barh(y, tor["value_at_low"] - base_ev, left=base_ev, color="#c55a11", label="low input")
ax.set_yticks(y); ax.set_yticklabels(tor.index)
ax.axvline(base_ev, color="black", lw=1)
ax.set_xlabel("Enterprise value"); ax.set_title("Tornado: EV sensitivity to each assumption")
ax.legend(loc="lower right"); fig.tight_layout(); fig.savefig(out / "tornado.png", dpi=150)

# ---- 3. Two-way table: WACC x terminal growth (the pair that always matters most)
w = res["wacc"]
tw = two_way_table(a, "wacc", [round(w + d, 4) for d in (-0.02, -0.01, 0, 0.01, 0.02)],
                   "terminal_growth", [round(a.terminal_growth + d, 4) for d in (-0.01, -0.005, 0, 0.005, 0.01)])
tw.round(0).to_csv(out / "two_way_wacc_g.csv")
print("\nEV: WACC (rows) x terminal growth (cols)\n", tw.round(0).to_string())

# ---- 4. Monte Carlo
dists = {
    "revenue_growth": ("normal", (a.revenue_growth, 0.015)),
    "ebit_margin": ("normal", (a.ebit_margin, 0.015)),
    "terminal_growth": ("triangular", (a.terminal_growth - 0.01, a.terminal_growth, a.terminal_growth + 0.01)),
    "beta": ("normal", (a.beta, 0.15)),
}
sim = monte_carlo(a, dists, n=10_000)
summ = summarise(sim)
summ.round(1).to_csv(out / "monte_carlo_summary.csv", header=["value"])
print("\nMonte Carlo EV\n", summ.round(1).to_string())
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.hist(sim["enterprise_value"], bins=80, color="#2e75b6", alpha=0.85)
for q, c in ((summ["p5"], "#c55a11"), (summ["median"], "black"), (summ["p95"], "#c55a11")):
    ax.axvline(q, color=c, lw=1.2)
ax.set_xlabel("Enterprise value"); ax.set_ylabel("simulations")
ax.set_title(f"Monte Carlo (n={int(summ['n']):,}): P5 / median / P95 marked")
fig.tight_layout(); fig.savefig(out / "monte_carlo.png", dpi=150)

# ---- 5. Excel with live formulas
xlsx = write_workbook(a, out / "dcf_model.xlsx", two_way=tw)
print(f"\nWrote {xlsx}")
