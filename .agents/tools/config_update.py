"""Config update helper functions for pipeline.json."""

from pathlib import Path
from typing import Optional

# Import from common.py - will be used via sys.path in CLI


def load_pipeline_config(config_path: Path) -> dict:
    """Load pipeline.json configuration.

    Args:
        config_path: Path to pipeline.json file.

    Returns:
        Configuration dict, empty dict if file not found.
    """
    if not config_path.exists():
        return {}
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_pipeline_config(config_path: Path, config: dict) -> None:
    """Save pipeline.json configuration.

    Args:
        config_path: Path to pipeline.json file.
        config: Configuration dict to save.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_cppcheck_xml_from_config(config: dict) -> str:
    """Get input.cppcheck_xml value from config.

    Args:
        config: Pipeline configuration dict.

    Returns:
        cppcheck_xml path string, empty string if not set.
    """
    return str(config.get("input", {}).get("cppcheck_xml", "")).strip()


def update_cppcheck_xml_in_config(config_path: Path, new_xml_path: str) -> bool:
    """Update input.cppcheck_xml in pipeline.json.

    Args:
        config_path: Path to pipeline.json file.
        new_xml_path: New relative path for cppcheck_xml.

    Returns:
        True if updated, False if value unchanged.
    """
    config = load_pipeline_config(config_path)
    old_value = get_cppcheck_xml_from_config(config)

    if old_value == new_xml_path:
        return False

    config.setdefault("input", {})["cppcheck_xml"] = new_xml_path
    save_pipeline_config(config_path, config)
    return True


def resolve_relative_xml_path(xml_path: Path, project_root: Path) -> str:
    """Resolve XML path to relative path under project root.

    Args:
        xml_path: Absolute or relative XML path.
        project_root: Project root directory.

    Returns:
        Relative path string under project root.
    """
    try:
        if xml_path.is_absolute():
            return str(xml_path.relative_to(project_root))
        return str(xml_path)
    except ValueError:
        # xml_path not under project_root, return as-is
        return str(xml_path)