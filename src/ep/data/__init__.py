"""Data layer.

Houses the abstract ``DataProvider`` interface and concrete provider
implementations (FMP first; Polygon / Alpaca SIP later via config swap).
Also contains pure derived calculations (ADR, average volume, VWAP, SMA,
gap %) used by every later layer. Strategy code must depend on this package,
never on a specific provider SDK.
"""
