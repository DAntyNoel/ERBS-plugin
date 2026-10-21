"""Read server-supplied character analysis JSON without executing page scripts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any


def _object(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[tuple[str | None, str]] = []
        self._id: str | None = None
        self._parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "script":
            self._id = dict(attrs).get("id")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._parts is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._parts is not None:
            self.scripts.append((self._id, "".join(self._parts)))
            self._parts = None


def extract_character_analysis(html: str) -> Mapping[str, Any]:
    parser = _Scripts()
    parser.feed(html)
    candidates = sorted(parser.scripts, key=lambda pair: pair[0] != "__NEXT_DATA__")
    for identifier, body in candidates:
        if identifier != "__NEXT_DATA__" and "characterDetailStatSnapshot" not in body:
            continue
        try:
            document = json.loads(body)
        except (ValueError, TypeError):
            continue
        if not isinstance(document, Mapping):
            continue
        props = _object(document.get("props")).get("pageProps", {})
        if not isinstance(props, Mapping):
            continue
        queries = _object(props.get("dehydratedState")).get("queries", [])
        if not isinstance(queries, list):
            continue
        for query in queries:
            if not isinstance(query, Mapping):
                continue
            data = _object(query.get("state")).get("data")
            if isinstance(data, Mapping) and "characterDetailStatSnapshot" in data:
                return {
                    **data,
                    "character": props.get("character", {}),
                    "characterTitle": props.get("characterTitle", ""),
                }
    raise ValueError("DAK.GG 角色详情页缺少可解析的统计快照")
