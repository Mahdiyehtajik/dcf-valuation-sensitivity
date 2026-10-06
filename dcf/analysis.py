"""
Sensitivity and Monte Carlo analysis on top of the base model.

Three questions a reviewer asks of any DCF:
1. Which single assumption moves the value the most?           -> tornado()
2. How does value react to the two riskiest assumptions jointly? -> two_way_table()
3. What is the distribution of value if assumptions are uncertain? -> monte_carlo()
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .model import Assumptions, value


# ---------------------------------------------------------------------------
# 1. One-at-a-time sensitivity (tornado)
# ---------------------------------------------------------------------------

def tornado(a: Assumptions, shocks: dict[str, tuple[float, float]], metric: str = "enterprise_value") -> pd.DataFrame:
    """
    For each assumption, re-run the model at a low and a high value and record
    the resulting metric. `shocks` maps field name -> (low, high) absolute values.

    Returns a frame sorted by swing (high - low), largest first, which is the
    conventional tornado ordering.
    """
    base = value(a)[metric]
    rows = []
    for field, (lo, hi) in shocks.items():
        v_lo = value(a.with_(**{field: lo}))[metric]
        v_hi = value(a.with_(**{field: hi}))[metric]
        rows.append(
            {
                "assumption": field,
                "low_input": lo,
                "high_input": hi,
                "value_at_low": v_lo,
                "value_at_high": v_hi,
                "swing": v_hi - v_lo,
                "swing_pct_of_base": (v_hi - v_lo) / base,
            }
        )
    out = pd.DataFrame(rows).set_index("assumption")
    return out.reindex(out["swing"].abs().sort_values(ascending=False).index)


# ---------------------------------------------------------------------------
# 2. Two-way sensitivity table
# ---------------------------------------------------------------------------

def two_way_table(
    a: Assumptions,
    row_field: str,
    row_values: list[float],
    col_field: str,
    col_values: list[float],
    metric: str = "enterprise_value",
) -> pd.DataFrame:
    """
    Grid of the metric over two assumptions. Cells where the model is invalid
    (e.g. WACC <= g) are NaN rather than raising, so the table always renders.

    Note: when `row_field` or `col_field` is "wacc" the override is applied by
    scaling the cost-of-capital inputs, since WACC is derived, not stored.
    """
    grid = np.full((len(row_values), len(col_values)), np.nan)
    for i, rv in enumerate(row_values):
        for j, cv in enumerate(col_values):
            try:
                grid[i, j] = value(_override(a, {row_field: rv, col_field: cv}))[metric]
            except ValueError:
                pass
    return pd.DataFrame(grid, index=pd.Index(row_values, name=row_field), columns=pd.Index(col_values, name=col_field))


def _override(a: Assumptions, changes: dict[str, float]) -> Assumptions:
    """Apply overrides; treat 'wacc' as a target by shifting risk_free to hit it."""
    from .model import wacc as _wacc

    changes = dict(changes)
    target_wacc = changes.pop("wacc", None)
    a2 = a.with_(**changes)
    if target_wacc is not None:
        # WACC is linear in risk_free with slope (1 - debt_weight); solve exactly.
        current = _wacc(a2)
        shift = (target_wacc - current) / (1 - a2.debt_weight)
        a2 = a2.with_(risk_free=a2.risk_free + shift)
    return a2


# ---------------------------------------------------------------------------
# 3. Monte Carlo
# ---------------------------------------------------------------------------

def monte_carlo(
    a: Assumptions,
    distributions: dict[str, tuple[str, tuple]],
    n: int = 10_000,
    seed: int = 42,
    metric: str = "enterprise_value",
) -> pd.DataFrame:
    """
    Sample assumptions independently and re-run the model n times.

    `distributions` maps field -> (kind, params):
        ("normal",     (mean, sd))
        ("triangular", (low, mode, high))
        ("uniform",    (low, high))

    Returns one row per simulation with the sampled inputs and the metric.
    Invalid draws (WACC <= g) are dropped and reported via the attrs.
    """
    rng = np.random.default_rng(seed)
    samples = {}
    for field, (kind, params) in distributions.items():
        if kind == "normal":
            samples[field] = rng.normal(*params, size=n)
        elif kind == "triangular":
            samples[field] = rng.triangular(*params, size=n)
        elif kind == "uniform":
            samples[field] = rng.uniform(*params, size=n)
        else:
            raise ValueError(f"unknown distribution kind {kind!r}")

    results = []
    dropped = 0
    for k in range(n):
        draw = {f: float(samples[f][k]) for f in samples}
        try:
            results.append({**draw, metric: value(a.with_(**draw))[metric]})
        except ValueError:
            dropped += 1
    out = pd.DataFrame(results)
    out.attrs["dropped_invalid"] = dropped
    return out


def summarise(sim: pd.DataFrame, metric: str = "enterprise_value") -> pd.Series:
    s = sim[metric]
    return pd.Series(
        {
            "mean": s.mean(),
            "median": s.median(),
            "std": s.std(),
            "p5": s.quantile(0.05),
            "p25": s.quantile(0.25),
            "p75": s.quantile(0.75),
            "p95": s.quantile(0.95),
            "n": len(s),
            "dropped_invalid": sim.attrs.get("dropped_invalid", 0),
        }
    )
