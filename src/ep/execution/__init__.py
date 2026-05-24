"""Live execution.

Broker abstraction (Alpaca first, paper before live) and the autonomous
loop that places buy-stops at the OR breakout, attaches the 1×ADR stop on
fill, manages the +2R / day-5 partial, the breakeven move, and the
10-day-SMA trail. The go-live gate (≥ 2 months paper + ≥ 30 trades +
backtest-consistent results) is enforced here.
"""
