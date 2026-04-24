from __future__ import annotations

import importlib
import warnings
from pathlib import Path
from typing import Any

# Auto-discover providers from *.py files in this directory
PROVIDERS = {}
for f in Path(__file__).parent.glob("*.py"):
    if f.name.startswith("_") or f.stem == "base":
        continue
    try:
        mod = importlib.import_module(f".{f.stem}", package=__name__)
        name = getattr(mod, "PROVIDER_NAME", f.stem)
        PROVIDERS[name] = mod
    except ImportError as e:
        # Log warning but continue with other providers
        warnings.warn(f"Failed to load provider module {f.stem}: {e}")


def get_provider(name: str) -> Any:
    return PROVIDERS.get(name)
