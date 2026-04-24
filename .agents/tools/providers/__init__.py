from __future__ import annotations

from typing import Any

from . import claude
from . import codex


PROVIDERS = {
    "claude": claude,
    "codex": codex,
}


def get_provider(name: str) -> Any:
    return PROVIDERS.get(name)
