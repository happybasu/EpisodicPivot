"""Event-driven backtest engine.

Replays the strategy on historical data day by day and bar by bar. Shares
its entry/exit code path with the live execution module — there is one
implementation, not two. Conservative fills (no fill on a touched-only
high; slippage always applied) and the full portfolio-limit logic live
here.
"""
