from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402


class AgentStagingConfigTests(unittest.TestCase):
    def test_validate_pipeline_config_requires_agent_staging_dir(self) -> None:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))
        config["agent"].pop("staging_dir")

        errors, warnings = common.validate_pipeline_config(config)

        self.assertIn("agent.staging_dir must be a non-empty string", errors)
        self.assertEqual(warnings, [])

    def test_resolve_agent_staging_dir_accepts_relative_path_under_project_root(self) -> None:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config["agent"]["staging_dir"] = ".agents/staging"

            staging_dir = common.resolve_agent_staging_dir(config, root=root)

        self.assertEqual(staging_dir, root / ".agents" / "staging")
        self.assertTrue(staging_dir.is_absolute())

    def test_resolve_agent_staging_dir_rejects_path_outside_project_root(self) -> None:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config["agent"]["staging_dir"] = "../outside"

            with self.assertRaisesRegex(ValueError, "project root"):
                common.resolve_agent_staging_dir(config, root=root)


if __name__ == "__main__":
    unittest.main()
