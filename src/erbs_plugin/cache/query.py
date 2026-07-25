from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Mapping
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..models import CardPayload

_SCHEMA_VERSION = 1
_CACHE_NOTICE = "缓存命中，数据可能不是最新"


def query_cache_spec(
    operation: str,
    arguments: tuple[str, ...],
    *,
    api_base_url: str,
    language: str,
    count: int,
    page: int,
    season: str | None,
    weapon: str | None,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "arguments": list(arguments),
        "count": count,
        "page": page,
        "season": season,
        "weapon": weapon,
        "apiBaseUrl": api_base_url,
        "language": language,
    }


def _cache_key(spec: Mapping[str, Any]) -> str:
    serialized = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _iso_timestamp(value: str | float | None = None) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC).isoformat(timespec="seconds")
    return datetime.fromtimestamp(time.time(), tz=UTC).isoformat(timespec="seconds")


def annotate_query_payload(
    payload: CardPayload,
    *,
    cached: bool | None = None,
    updated_at: str | float | None = None,
) -> CardPayload:
    footer = dict(payload.footer)
    cache_hit = bool(footer.get("cached")) if cached is None else cached
    footer["cached"] = cache_hit
    footer["updatedAt"] = _iso_timestamp(updated_at or footer.get("updatedAt"))
    if cache_hit:
        footer["notice"] = _CACHE_NOTICE
    else:
        footer.pop("notice", None)
    return CardPayload(
        kind=payload.kind,
        title=payload.title,
        subtitle=payload.subtitle,
        sections=payload.sections,
        footer=footer,
    )


def _card_payload(
    value: object,
    *,
    cached: bool,
    updated_at: str | float | None = None,
) -> CardPayload | None:
    if not isinstance(value, Mapping):
        return None
    kind = value.get("kind")
    title = value.get("title")
    subtitle = value.get("subtitle", "")
    sections = value.get("sections", ())
    footer = value.get("footer", {})
    if not isinstance(kind, str) or not isinstance(title, str) or not isinstance(subtitle, str):
        return None
    if not isinstance(sections, (list, tuple)) or not all(
        isinstance(section, Mapping) for section in sections
    ):
        return None
    if not isinstance(footer, Mapping):
        return None
    payload = CardPayload(
        kind=kind,
        title=title,
        subtitle=subtitle,
        sections=tuple(dict(section) for section in sections),
        footer=dict(footer),
    )
    return annotate_query_payload(payload, cached=cached, updated_at=updated_at)


class QueryCacheDatabase:
    """Private, process-safe SQLite cache for high-level query payloads."""

    def __init__(self, path: str | Path, *, max_entries: int = 512) -> None:
        self.path = Path(path).expanduser()
        self.max_entries = max(1, max_entries)

    async def get(self, spec: Mapping[str, Any]) -> CardPayload | None:
        try:
            return await asyncio.to_thread(self._get, dict(spec), time.time())
        except (OSError, sqlite3.Error, ValueError):
            return None

    async def set(self, spec: Mapping[str, Any], payload: CardPayload, *, ttl: int) -> None:
        if ttl <= 0:
            return
        try:
            await asyncio.to_thread(self._set, dict(spec), payload, ttl, time.time())
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS query_cache (
                cache_key TEXT PRIMARY KEY,
                operation TEXT NOT NULL,
                request_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                last_accessed_at REAL NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS query_cache_expiry ON query_cache(expires_at)"
        )
        connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
        connection.commit()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        return connection

    def _get(self, spec: dict[str, Any], now: float) -> CardPayload | None:
        key = _cache_key(spec)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                """
                SELECT request_json, payload_json, created_at, expires_at
                FROM query_cache
                WHERE cache_key = ?
                """,
                (key,),
            ).fetchone()
            if row is None:
                return None
            request_json, payload_json, created_at, expires_at = row
            if float(expires_at) <= now:
                connection.execute("DELETE FROM query_cache WHERE cache_key = ?", (key,))
                return None
            if json.loads(request_json) != spec:
                connection.execute("DELETE FROM query_cache WHERE cache_key = ?", (key,))
                return None
            payload = _card_payload(
                json.loads(payload_json),
                cached=True,
                updated_at=float(created_at),
            )
            if payload is None:
                connection.execute("DELETE FROM query_cache WHERE cache_key = ?", (key,))
                return None
            connection.execute(
                "UPDATE query_cache SET last_accessed_at = ? WHERE cache_key = ?",
                (now, key),
            )
            return payload

    def _set(
        self,
        spec: dict[str, Any],
        payload: CardPayload,
        ttl: int,
        now: float,
    ) -> None:
        key = _cache_key(spec)
        request_json = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_json = json.dumps(
            asdict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM query_cache WHERE expires_at <= ?", (now,))
            connection.execute(
                """
                INSERT INTO query_cache (
                    cache_key, operation, request_json, payload_json,
                    created_at, expires_at, last_accessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    operation = excluded.operation,
                    request_json = excluded.request_json,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at,
                    last_accessed_at = excluded.last_accessed_at
                """,
                (
                    key,
                    str(spec["operation"]),
                    request_json,
                    payload_json,
                    now,
                    now + ttl,
                    now,
                ),
            )
            count = int(connection.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0])
            overflow = count - self.max_entries
            if overflow > 0:
                connection.execute(
                    """
                    DELETE FROM query_cache
                    WHERE cache_key IN (
                        SELECT cache_key FROM query_cache
                        ORDER BY last_accessed_at ASC
                        LIMIT ?
                    )
                    """,
                    (overflow,),
                )


__all__ = ["QueryCacheDatabase", "annotate_query_payload", "query_cache_spec"]
