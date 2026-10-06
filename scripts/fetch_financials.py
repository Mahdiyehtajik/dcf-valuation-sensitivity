"""
Pull historical financials for a listed company with yfinance and derive the
operating ratios the model needs (growth, EBIT margin, D&A, capex, NWC as % of
revenue) from the last three fiscal years.

Usage:
    pip install yfinance
    python scripts/fetch_financials.py SAP.DE > data/sap.json

Market inputs (risk-free, ERP, beta, cost of debt, target leverage) are NOT
derived here: they are judgement calls and are left at the base-case values
for you to overwrite.
"""
import json, sys
import yfinance as yf

t = yf.Ticker(sys.argv[1])
inc, cf, bs = t.income_stmt, t.cashflow, t.balance_sheet
rev = inc.loc["Total Revenue"].sort_index()
ebit = inc.loc["EBIT"].sort_index()
da = cf.loc["Depreciation And Amortization"].sort_index()
capex = -cf.loc["Capital Expenditure"].sort_index()
nwc = (bs.loc["Current Assets"] - bs.loc["Current Liabilities"]).sort_index()

base = json.load(open("data/base_case.json"))
base.update({
    "revenue_0": float(rev.iloc[-1]) / 1e6,
    "revenue_growth": float((rev.iloc[-1] / rev.iloc[0]) ** (1 / (len(rev) - 1)) - 1),
    "ebit_margin": float((ebit / rev).mean()),
    "da_pct": float((da / rev).mean()),
    "capex_pct": float((capex / rev).mean()),
    "nwc_pct": float((nwc / rev).mean()),
    "beta": float(t.info.get("beta", base["beta"])),
    "net_debt": float((bs.loc["Total Debt"].iloc[-1] - bs.loc["Cash And Cash Equivalents"].iloc[-1]) / 1e6),
    "shares_outstanding": float(t.info.get("sharesOutstanding", 0)) / 1e6,
    "_comment": f"Derived from yfinance for {sys.argv[1]}; amounts in millions of reporting currency.",
})
print(json.dumps(base, indent=2))
