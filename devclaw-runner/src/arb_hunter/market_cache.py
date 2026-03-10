"""Simple file-based cache for raw API responses (audit trail)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .market_normalization_error import MarketNormalizationError


class MarketCache:
    """File-based cache for raw API responses.

    Provides:
    - Audit trail for all API responses
    - Replay capability for debugging
    - TTL-based expiration
    - Organized directory structure
    """

    DEFAULT_CACHE_DIR = ".cache/openclaw"
    DEFAULT_TTL_SECONDS = 3600  # 1 hour

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        enabled: bool = True,
    ) -> None:
        """Initialize the cache.

        Args:
            cache_dir: Directory for cache files (default: .cache/openclaw)
            ttl_seconds: Time-to-live for cache entries
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir or self.DEFAULT_CACHE_DIR)
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self._lock = asyncio.Lock()

        # Create cache directory
        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(self, identifier: str) -> str:
        """Create a safe filename from identifier.

        Args:
            identifier: Cache key

        Returns:
            Safe filename
        """
        # Hash long identifiers
        if len(identifier) > 100:
            hash_suffix = hashlib.md5(identifier.encode()).hexdigest()[:12]
            identifier = identifier[:80] + "_" + hash_suffix

        # Replace unsafe characters
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in identifier)
        return safe

    def _get_cache_path(self, key: str, source: str | None = None) -> Path:
        """Get the file path for a cache entry.

        Args:
            key: Cache key
            source: Optional source subdirectory

        Returns:
            Path to cache file
        """
        if source:
            source_dir = self.cache_dir / source
            source_dir.mkdir(exist_ok=True)
        else:
            source_dir = self.cache_dir

        safe_key = self._make_key(key)
        return source_dir / f"{safe_key}.json"

    def _get_metadata_path(self, cache_path: Path) -> Path:
        """Get metadata file path.

        Args:
            cache_path: Cache file path

        Returns:
            Metadata file path
        """
        return cache_path.with_suffix(".meta.json")

    async def store(
        self,
        key: str,
        data: Any,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Store data in cache.

        Args:
            key: Cache key
            data: Data to store (JSON serializable)
            source: Optional source subdirectory
            metadata: Optional metadata

        Returns:
            Path to cached file

        Raises:
            MarketNormalizationError: If storage fails
        """
        if not self.enabled:
            raise MarketNormalizationError("Cache is disabled")

        async with self._lock:
            cache_path = self._get_cache_path(key, source)

            try:
                # Store data
                with open(cache_path, "w") as f:
                    json.dump(data, f, indent=2, default=str)

                # Store metadata
                meta = {
                    "key": key,
                    "stored_at": datetime.now(timezone.utc).isoformat(),
                    "ttl_seconds": self.ttl_seconds,
                    "source": source,
                    **(metadata or {}),
                }

                meta_path = self._get_metadata_path(cache_path)
                with open(meta_path, "w") as f:
                    json.dump(meta, f, indent=2)

                return cache_path

            except (IOError, OSError, TypeError) as e:
                raise MarketNormalizationError(
                    f"Failed to cache data: {e}",
                    source="cache",
                ) from e

    async def get(
        self,
        key: str,
        source: str | None = None,
        check_ttl: bool = True,
    ) -> Any | None:
        """Retrieve data from cache.

        Args:
            key: Cache key
            source: Optional source subdirectory
            check_ttl: Whether to check TTL

        Returns:
            Cached data or None if not found/expired
        """
        if not self.enabled:
            return None

        cache_path = self._get_cache_path(key, source)

        if not cache_path.exists():
            return None

        # Check TTL
        if check_ttl:
            meta_path = self._get_metadata_path(cache_path)
            if meta_path.exists():
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)

                    stored_at = datetime.fromisoformat(meta["stored_at"])
                    age = (datetime.now(timezone.utc) - stored_at).total_seconds()

                    if age > meta.get("ttl_seconds", self.ttl_seconds):
                        return None  # Expired

                except (IOError, json.JSONDecodeError, KeyError, ValueError):
                    pass  # Continue even if metadata is corrupt

        try:
            with open(cache_path) as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            return None

    async def get_with_metadata(
        self,
        key: str,
        source: str | None = None,
    ) -> tuple[Any | None, dict[str, Any] | None]:
        """Retrieve data and metadata from cache.

        Args:
            key: Cache key
            source: Optional source subdirectory

        Returns:
            Tuple of (data, metadata)
        """
        data = await self.get(key, source, check_ttl=False)

        cache_path = self._get_cache_path(key, source)
        meta_path = self._get_metadata_path(cache_path)

        metadata = None
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    metadata = json.load(f)
            except (IOError, json.JSONDecodeError):
                pass

        return data, metadata

    async def invalidate(self, key: str, source: str | None = None) -> bool:
        """Remove a cache entry.

        Args:
            key: Cache key
            source: Optional source subdirectory

        Returns:
            True if entry was removed
        """
        cache_path = self._get_cache_path(key, source)
        meta_path = self._get_metadata_path(cache_path)

        removed = False

        try:
            if cache_path.exists():
                cache_path.unlink()
                removed = True
            if meta_path.exists():
                meta_path.unlink()
        except (IOError, OSError):
            pass

        return removed

    async def clear(self, source: str | None = None) -> int:
        """Clear all cache entries.

        Args:
            source: Clear only specific source, or all if None

        Returns:
            Number of entries removed
        """
        async with self._lock:
            target_dir = self.cache_dir / source if source else self.cache_dir

            if not target_dir.exists():
                return 0

            count = 0
            try:
                for item in target_dir.iterdir():
                    if item.suffix in (".json", ".meta.json"):
                        item.unlink()
                        count += 1
            except (IOError, OSError):
                pass

            return count

    async def cleanup_expired(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            count = 0
            now = datetime.now(timezone.utc)

            try:
                for meta_file in self.cache_dir.rglob("*.meta.json"):
                    try:
                        with open(meta_file) as f:
                            meta = json.load(f)

                        stored_at = datetime.fromisoformat(meta["stored_at"])
                        age = (now - stored_at).total_seconds()

                        if age > meta.get("ttl_seconds", self.ttl_seconds):
                            # Remove data and metadata
                            data_file = meta_file.with_suffix("").with_suffix(".json")
                            meta_file.unlink()
                            if data_file.exists():
                                data_file.unlink()
                            count += 1

                    except (IOError, json.JSONDecodeError, KeyError, ValueError):
                        continue

            except (IOError, OSError):
                pass

            return count

    def list_entries(
        self,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all cache entries.

        Args:
            source: Filter by source

        Returns:
            List of entry metadata
        """
        entries: list[dict[str, Any]] = []
        target_dir = self.cache_dir / source if source else self.cache_dir

        if not target_dir.exists():
            return entries

        for meta_file in target_dir.rglob("*.meta.json"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)

                # Check if expired
                stored_at = datetime.fromisoformat(meta["stored_at"])
                age = (datetime.now(timezone.utc) - stored_at).total_seconds()
                meta["is_expired"] = age > meta.get("ttl_seconds", self.ttl_seconds)
                meta["age_seconds"] = age

                entries.append(meta)

            except (IOError, json.JSONDecodeError, KeyError, ValueError):
                continue

        return sorted(entries, key=lambda x: x.get("stored_at", ""), reverse=True)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Statistics dict
        """
        entries = self.list_entries()
        total_size = 0

        for entry in entries:
            try:
                key = entry["key"]
                source = entry.get("source")
                cache_path = self._get_cache_path(key, source)
                if cache_path.exists():
                    total_size += cache_path.stat().st_size
            except (OSError, IOError):
                pass

        expired_count = sum(1 for e in entries if e.get("is_expired"))

        return {
            "enabled": self.enabled,
            "cache_dir": str(self.cache_dir),
            "total_entries": len(entries),
            "expired_entries": expired_count,
            "total_size_bytes": total_size,
            "ttl_seconds": self.ttl_seconds,
        }


class CacheReplay:
    """Replay cached API responses for debugging/testing."""

    def __init__(self, cache: MarketCache) -> None:
        """Initialize replay.

        Args:
            cache: Market cache instance
        """
        self.cache = cache

    async def replay_by_source(
        self,
        source: str,
        transform_func: Any | None = None,
    ) -> list[Any]:
        """Replay all cached responses for a source.

        Args:
            source: Source name (e.g., 'polymarket', 'oddsapi')
            transform_func: Optional function to apply to each entry

        Returns:
            List of cached data
        """
        entries = self.cache.list_entries(source=source)
        results: list[Any] = []

        for entry in entries:
            key = entry["key"]
            data = await self.cache.get(key, source, check_ttl=False)

            if data is not None:
                if transform_func:
                    data = transform_func(data)
                results.append(data)

        return results

    async def replay_by_time_range(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[str, Any, dict[str, Any]]]:
        """Replay cached responses within a time range.

        Args:
            start: Start time
            end: End time

        Returns:
            List of (key, data, metadata) tuples
        """
        entries = self.cache.list_entries()
        results: list[tuple[str, Any, dict[str, Any]]] = []

        for entry in entries:
            stored_at = datetime.fromisoformat(entry["stored_at"])
            if start <= stored_at <= end:
                key = entry["key"]
                source = entry.get("source")
                data = await self.cache.get(key, source, check_ttl=False)
                if data is not None:
                    results.append((key, data, entry))

        return results


# Utility functions for common caching patterns


def create_cache_key(
    source: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Create a standardized cache key.

    Args:
        source: Data source
        endpoint: API endpoint
        params: Query parameters

    Returns:
        Cache key string
    """
    key = f"{source}:{endpoint}"
    if params:
        param_str = ":".join(f"{k}={v}" for k, v in sorted(params.items()))
        key = f"{key}:{param_str}"
    return key
