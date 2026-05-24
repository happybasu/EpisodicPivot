"""Backtest validation.

Core KPIs, regime split (bull / bear / chop via SPY vs 200-day SMA),
walk-forward optimisation with out-of-sample degradation reporting,
Monte Carlo bootstrap of the trade sequence, and parameter-perturbation
robustness. Emits the master ``validation_report.md`` with explicit
pass/fail deployment criteria.
"""
