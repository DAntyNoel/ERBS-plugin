from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class _Entry[T]:
    value: T
    expires_at: float


class AsyncTTLCache[T]:
    def __init__(self) -> None:
        self._items: dict[str, _Entry[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        async with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                self._items.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: T, ttl: float) -> None:
        async with self._lock:
            self._items[key] = _Entry(value=value, expires_at=time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._items.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()
