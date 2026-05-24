"""Premarket scanner.

Two-stage screen that produces the daily Episodic Pivot watchlist: the
9:00 AM review list for human approval, and the 9:28 AM auto-confirmation
that drops any name whose gap has faded below threshold. Built from
independently testable components — catalyst classification, hard filters,
and non-gating soft signals.
"""
