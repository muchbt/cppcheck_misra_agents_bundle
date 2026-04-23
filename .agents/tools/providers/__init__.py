from __future__ import annotations

from typing import Any

from . import codex


PROVIDERS = {
    "codex": codex,
}


def get_provider(name: str) -> Any:
    return PROVIDERS.get(name)
