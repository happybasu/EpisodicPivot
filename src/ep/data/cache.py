"""Generic on-disk DataFrame cache.

Used by data providers to avoid re-hitting the API for previously-fetched
data. One parquet file per ``(namespace, key)`` pair under the configured
cache root. Namespaces partition data by kind (e.g. ``daily``,
``intraday_15min``, ``universe``).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_CACHE_ROOT = Path("data/cache")


class DataFrameCache:
    """File-backed DataFrame cache. Parquet engine: ``pyarrow``."""

    def __init__(self, root: Path | str = DEFAULT_CACHE_ROOT) -> None:
        self.root = Path(root)

    def path(self, namespace: str, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.root / namespace / f"{safe}.parquet"

    def has(self, namespace: str, key: str) -> bool:
        return self.path(namespace, key).exists()

    def get(self, namespace: str, key: str) -> pd.DataFrame | None:
        p = self.path(namespace, key)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def put(self, namespace: str, key: str, df: pd.DataFrame) -> None:
        p = self.path(namespace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(p, engine="pyarrow")
