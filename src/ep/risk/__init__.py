"""Risk and position sizing.

Risk-based sizing (1.0% per trade, derived from the 1×ADR stop) and the
portfolio-limit enforcement (max 5 concurrent, 3 new per day, 2 per
sector). These parameters are human-only; no learning loop is permitted
to touch them.
"""
