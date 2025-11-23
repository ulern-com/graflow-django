import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from django.utils import timezone
from langgraph.cache.base import BaseCache, FullKey, Namespace, ValueT
from langgraph.checkpoint.serde.base import SerializerProtocol


def _get_cache_entry_model():
    """Lazy import to avoid circular dependencies."""
    from graflow.models import CacheEntry

    return CacheEntry


class DjangoCache(BaseCache[ValueT]):
    """
    Django-based cache implementation for LangGraph.

    This cache stores values in a PostgreSQL database using Django ORM,
    providing persistence and the ability to share cache across multiple instances.
    """

    def __init__(self, *, serde: SerializerProtocol | None = None):
        super().__init__(serde=serde)
        self._lock = threading.RLock()

    def _namespace_to_str(self, namespace: Namespace) -> str:
        """Convert namespace tuple to string for storage."""
        return json.dumps(list(namespace))

    def _str_to_namespace(self, namespace_str: str) -> Namespace:
        """Convert string back to namespace tuple."""
        return tuple(json.loads(namespace_str))

    def _cleanup_expired(self):
        """Remove expired cache entries."""
        CacheEntry = _get_cache_entry_model()
        CacheEntry.objects.filter(expires_at__lte=timezone.now()).delete()

    def get(self, keys: Sequence[FullKey]) -> dict[FullKey, ValueT]:
        """Get the cached values for the given keys."""
        with self._lock:
            if not keys:
                return {}

            # Clean up expired entries
            self._cleanup_expired()

            values: dict[FullKey, ValueT] = {}

            for ns_tuple, key in keys:
                ns = Namespace(ns_tuple)
                namespace_str = self._namespace_to_str(ns)

                try:
                    # Try to find a non-expired entry
                    CacheEntry = _get_cache_entry_model()
                    entry = CacheEntry.objects.get(namespace=namespace_str, key=key)

                    # Check if the entry is expired
                    if entry.expires_at is not None and entry.expires_at <= timezone.now():
                        continue

                    # Deserialize the value
                    value = self.serde.loads_typed((entry.value_encoding, entry.value_data))
                    values[(ns, key)] = value

                except CacheEntry.DoesNotExist:
                    # Key not found
                    continue

            return values

    async def aget(self, keys: Sequence[FullKey]) -> dict[FullKey, ValueT]:
        """Asynchronously get the cached values for the given keys."""
        return self.get(keys)

    def set(self, pairs: Mapping[FullKey, tuple[ValueT, int | None]]) -> None:
        """Set the cached values for the given keys and TTLs."""
        with self._lock:
            for (ns, key), (value, ttl) in pairs.items():
                namespace_str = self._namespace_to_str(ns)

                # Serialize the value
                encoding, data = self.serde.dumps_typed(value)

                # Calculate expiry time
                expires_at = None
                if ttl is not None:
                    expires_at = timezone.now() + timedelta(seconds=ttl)

                # Create or update the cache entry
                CacheEntry = _get_cache_entry_model()
                CacheEntry.objects.update_or_create(
                    namespace=namespace_str,
                    key=key,
                    defaults={
                        "value_encoding": encoding,
                        "value_data": data,
                        "expires_at": expires_at,
                    },
                )

    async def aset(self, pairs: Mapping[FullKey, tuple[ValueT, int | None]]) -> None:
        """Asynchronously set the cached values for the given keys and TTLs."""
        self.set(pairs)

    def clear(self, namespaces: Sequence[Namespace] | None = None) -> None:
        """Delete the cached values for the given namespaces.
        If no namespaces are provided, clear all cached values."""
        with self._lock:
            if namespaces is None:
                # Clear all cache entries
                CacheEntry = _get_cache_entry_model()
                CacheEntry.objects.all().delete()
            else:
                # Clear specific namespaces
                for ns in namespaces:
                    namespace_str = self._namespace_to_str(ns)
                    CacheEntry = _get_cache_entry_model()
                    CacheEntry.objects.filter(namespace=namespace_str).delete()

    async def aclear(self, namespaces: Sequence[Namespace] | None = None) -> None:
        """Asynchronously delete the cached values for the given namespaces.
        If no namespaces are provided, clear all cached values."""
        self.clear(namespaces)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        CacheEntry = _get_cache_entry_model()
        total_entries = CacheEntry.objects.count()
        expired_entries = CacheEntry.objects.filter(expires_at__lte=timezone.now()).count()
        active_entries = total_entries - expired_entries

        return {
            "total_entries": total_entries,
            "active_entries": active_entries,
            "expired_entries": expired_entries,
        }

    def cleanup(self):
        """Manually clean up expired entries."""
        with self._lock:
            self._cleanup_expired()


def create_cache_key(prefix: str, data: dict[str, Any] | None = None) -> str:
    """
    Create a hashed cache key for any optional Python map.

    Args:
        prefix: A string prefix for the cache key (e.g., "outline", "content")
        data: Optional dictionary of key-value pairs to include in the hash

    Returns:
        A cache key string in format: {prefix}_{hash}

    Example:
        >>> create_cache_key("outline", {"data": "example", "user_id": 123})
        "outline_a1b2c3d4e5f6..."
    """
    if data is None:
        data = {}

    # Sort keys for consistent hashing
    sorted_data = dict(sorted(data.items()))

    # Create a deterministic string representation
    data_str = json.dumps(sorted_data, sort_keys=True, default=str)

    # Create a SHA-256 hash (32 bytes = 64 hex characters)
    hash_obj = hashlib.sha256(data_str.encode("utf-8"))
    hash_hex = hash_obj.hexdigest()

    return f"{prefix}_{hash_hex}"


def create_cache_key_from_fields(prefix: str, obj: Any, fields: list[str]) -> str:
    """
    Create a cache key by extracting specific fields from an object (Pydantic model or dict).

    Args:
        prefix: A string prefix for the cache key (e.g., "outline", "content")
        obj: The object to extract fields from (Pydantic model or dictionary)
        fields: List of field names to extract for the cache key

    Returns:
        A cache key string in format: {prefix}_{hash}

    Example:
        >>> create_cache_key_from_fields("outline", state, ["data_title", "user_preferences"])
        "outline_a1b2c3d4e5f6..."
    """
    data = {}

    for field in fields:
        if hasattr(obj, field):
            # It's a Pydantic model or object with attributes
            data[field] = getattr(obj, field, None)
        elif isinstance(obj, dict):
            # It's a dictionary
            data[field] = obj.get(field, None)
        else:
            # Unknown type, try to get as attribute first, then as dict key
            if hasattr(obj, field):
                data[field] = getattr(obj, field, None)
            else:
                data[field] = None

    return create_cache_key(prefix, data)
