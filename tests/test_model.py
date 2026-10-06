import json
import numpy as np
import pytest

from dcf import Assumptions, value, wacc, two_way_table, monte_carlo


def base():
    raw = {k: v for k, v in json.load(open("data/base_case.json")).items() if not k.startswith("_")}
    return Assumptions(**raw)


def test_wacc_build_up_by_hand():
    a = base()
    re = 0.028 + 1.10 * 0.055
    expected = 0.70 * re + 0.30 * 0.045 * 0.75
    assert wacc(a) == pytest.approx(expected)


def test_fcff_identity_year_one():
    a = base()
    cf = value(a)["cash_flows"].loc[1]
    assert cf["fcff"] == pytest.approx(cf["nopat"] + cf["d_and_a"] - cf["capex"] - cf["delta_nwc"])


def test_higher_wacc_lowers_value():
    a = base()
    lo = value(a)["enterprise_value"]
    hi = value(a.with_(risk_free=a.risk_free + 0.01))["enterprise_value"]
    assert hi < lo


def test_terminal_growth_must_be_below_wacc():
    a = base()
    with pytest.raises(ValueError):
        value(a.with_(terminal_growth=0.50))


def test_bridge_adds_up():
    r = value(base())
    assert r["enterprise_value"] == pytest.approx(r["pv_explicit"] + r["pv_terminal_value"])
    assert r["equity_value"] == pytest.approx(r["enterprise_value"] - base().net_debt)


def test_two_way_table_centre_equals_base():
    a = base()
    w = wacc(a)
    tw = two_way_table(a, "wacc", [w], "terminal_growth", [a.terminal_growth])
    assert tw.iloc[0, 0] == pytest.approx(value(a)["enterprise_value"], rel=1e-9)


def test_monte_carlo_is_reproducible():
    a = base()
    d = {"ebit_margin": ("normal", (a.ebit_margin, 0.01))}
    s1 = monte_carlo(a, d, n=200, seed=1)
    s2 = monte_carlo(a, d, n=200, seed=1)
    assert np.allclose(s1["enterprise_value"], s2["enterprise_value"])
