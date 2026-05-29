"""Small file cache for market data calls."""

from __future__ import annotations

import pickle
import time
from pathlib import Path
from typing import Any

try:
    from config import CACHE_DIR
except ImportError:
    from ..config import CACHE_DIR


class FileCache:
    def __init__(self, cache_dir: Path = CACHE_DIR) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in key)
        return self.cache_dir / f"{safe_key}.pkl"

    def get(self, key: str, ttl_seconds: int) -> Any | None:
        path = self._path(key)
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > ttl_seconds:
            return None
        try:
            with path.open("rb") as file:
                return pickle.load(file)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        try:
            with path.open("wb") as file:
                pickle.dump(value, file)
        except Exception:
            path.unlink(missing_ok=True)
