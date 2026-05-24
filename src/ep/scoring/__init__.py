"""Optional AI scoring layer.

A deterministic, human-readable rubric for ranking candidates on the review
list. Same input always yields the same score. Hard rule: never a hard
filter, never a trade trigger — the system trades fully with scoring
disabled. The rubric is produced by a one-time calibration run and can
only be replaced by explicit human action.
"""
