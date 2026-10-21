from __future__ import annotations

from typing import Protocol

from ..models import CardPayload


class CardRenderer(Protocol):
    async def render(self, payload: CardPayload) -> bytes: ...

    async def close(self) -> None: ...
