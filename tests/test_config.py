"""Phase 0.2 verification — config.yaml defaults match the locked strategy table.

The defaults asserted here come from EpisodicPivot.md §0 and CLAUDE.md.
Changing any of them is a deliberate human decision; if a default moves,
update both documents and this test together.
"""

from ep.config import Config, load_config


def test_load_config_returns_config_instance():
    cfg = load_config()
    assert isinstance(cfg, Config)


def test_strategy_defaults_match_locked_table():
    s = load_config().strategy

    # Scan / eligibility
    assert s.gap_threshold == 0.10
    assert s.adr_period == 20
    assert s.opening_volume_threshold == 0.10
    assert s.or_length_minutes == 15

    # Risk and sizing
    assert s.risk_per_trade == 0.01
    assert s.stop_atr_multiple == 1.0

    # Portfolio limits
    assert s.max_positions == 5
    assert s.max_new_per_day == 3
    assert s.max_per_sector == 2

    # Exits
    assert s.partial_fraction == 0.5
    assert s.profit_take_r_multiple == 2.0
    assert s.day_backstop == 5
    assert s.trail_sma_length == 10

    # Post-approval auto-cancel
    assert s.auto_cancel_threshold == 0.10

    # Backtest window
    assert s.backtest_lookback_years == 5


def test_data_provider_default_is_fmp():
    assert load_config().data.provider == "fmp"


def test_execution_defaults_paper_alpaca():
    e = load_config().execution
    assert e.broker == "alpaca"
    assert e.mode == "paper"


def test_scoring_disabled_by_default():
    assert load_config().scoring.enabled is False
