"""JSON utility stubs."""

import json
from typing import Any


def dumps(data: Any) -> str:
    return json.dumps(data, default=str)


def loads(raw: str) -> Any:
    return json.loads(raw)
