from __future__ import annotations

import json
from dataclasses import asdict

from ..models import CardPayload


class TextRenderer:
    def render(self, payload: CardPayload) -> str:
        return json.dumps(asdict(payload), ensure_ascii=False, indent=2, default=str)
