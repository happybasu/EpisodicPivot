"""Phase 0.3 verification — the DataProvider abstraction."""

from datetime import date

import pytest

from ep.data import FMPProvider, get_provider
from ep.data.provider import DataProvider


def test_get_provider_returns_fmp_provider():
    p = get_provider()
    assert isinstance(p, FMPProvider)


def test_fmp_provider_is_data_provider_subclass():
    assert issubclass(FMPProvider, DataProvider)


def test_data_provider_is_abstract():
    """Cannot instantiate the abstract base directly."""
    with pytest.raises(TypeError):
        DataProvider()  # type: ignore[abstract]


def test_unknown_provider_raises():
    """Factory rejects an unrecognised provider name with a clear error."""
    from ep.config import Config

    # data.provider's Literal type makes this impossible at the type level,
    # so we go around model validation to exercise the factory branch.
    cfg = Config()
    object.__setattr__(cfg.data, "provider", "polygon")
    with pytest.raises(ValueError, match="Unknown data provider"):
        get_provider(cfg)


def test_fmp_stub_methods_raise_not_implemented():
    """Every abstract method is stubbed; real impl lands in Phase 1."""
    p = get_provider()
    with pytest.raises(NotImplementedError):
        p.get_universe(date(2024, 1, 2))
    with pytest.raises(NotImplementedError):
        p.get_company_profile("AAPL")
