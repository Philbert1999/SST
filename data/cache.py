"""Small file cache for market data calls."""

from __future__ import annotations

import pickle
import logging
import os
import tempfile
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
        try:
            if time.time() - path.stat().st_mtime > ttl_seconds:
                return None
            with path.open("rb") as file:
                return pickle.load(file)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as file:
                temporary = Path(file.name)
                pickle.dump(value, file)
            os.replace(temporary, path)
        except Exception:
            logging.getLogger(__name__).warning("Unable to save cache %s", key, exc_info=True)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
