"""Config loader for the Episodic Pivot system.

Loads ``config.yaml`` (strategy parameters and provider selection) and ``.env``
(secrets) into a typed ``Config`` object. Every tunable parameter from the
locked strategy table lives here — no magic numbers in code (see CLAUDE.md).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.yaml"
DEFAULT_ENV_PATH = REPO_ROOT / ".env"


class StrategyConfig(BaseModel):
    """Locked strategy parameters.

    Defaults match the table in ``EpisodicPivot.md`` §0. Every value is
    tunable but human-only — no learning loop is permitted to touch these.
    """

    # --- Scan / eligibility ---
    gap_threshold: float = 0.10
    adr_period: int = 20
    opening_volume_threshold: float = 0.10
    or_length_minutes: Literal[5, 15, 30, 60] = 15

    # --- Risk and sizing ---
    risk_per_trade: float = 0.01
    stop_atr_multiple: float = 1.0

    # --- Portfolio limits ---
    max_positions: int = 5
    max_new_per_day: int = 3
    max_per_sector: int = 2

    # --- Exits ---
    partial_fraction: float = 0.5
    profit_take_r_multiple: float = 2.0
    day_backstop: int = 5
    trail_sma_length: int = 10

    # --- Post-approval auto-cancel ---
    auto_cancel_threshold: float = 0.10

    # --- Backtest window ---
    backtest_lookback_years: int = 5


class DataConfig(BaseModel):
    """Data provider selection. v1 supports FMP only."""

    provider: Literal["fmp"] = "fmp"


class ExecutionConfig(BaseModel):
    """Execution mode. Must stay ``paper`` until the go-live gate (Phase 7.5) passes."""

    broker: Literal["alpaca"] = "alpaca"
    mode: Literal["paper", "live"] = "paper"


class ScoringConfig(BaseModel):
    """Optional deterministic scoring layer (Phase 5)."""

    enabled: bool = False


class Secrets(BaseSettings):
    """Secrets loaded from ``.env``.

    All optional at load time — features that actually need a key should fail
    loudly when invoked without it, not at config load.
    """

    fmp_api_key: str | None = None
    polygon_api_key: str | None = None
    fred_api_key: str | None = None
    alpaca_api_key: str | None = None
    alpaca_api_secret: str | None = None
    alpaca_base_url: str | None = None
    sec_user_agent: str | None = None
    openrouter_api_key: str | None = None
    openrouter_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class Config(BaseModel):
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    secrets: Secrets = Field(default_factory=Secrets)


def load_config(config_path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    """Load and validate ``config.yaml`` (if present) plus ``.env`` secrets.

    If ``config.yaml`` is missing, defaults from the model are used — those
    defaults *are* the locked strategy table values.
    """
    path = Path(config_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    return Config(**data)
