from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

# Auto-discover providers from *.py files in this directory
PROVIDERS = {}
for f in Path(__file__).parent.glob("*.py"):
    if f.name.startswith("_"):
        continue
    mod = importlib.import_module(f".{f.stem}", package=__name__)
    name = getattr(mod, "PROVIDER_NAME", f.stem)
    PROVIDERS[name] = mod


def get_provider(name: str) -> Any:
    return PROVIDERS.get(name)
