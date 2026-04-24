"""Unit tests for policy_init.py module."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import policy_init  # type: ignore  # noqa: E402


class PolicyInitTests(unittest.TestCase):
    """Tests for policy_init module."""

    def test_available_templates_defined(self) -> None:
        """Test that AVAILABLE_TEMPLATES contains expected templates."""
        expected_templates = [
            "misra_c2012_conservative",
            "misra_c2012_relaxed",
            "autosar_baseline",
            "cppcheck_common",
        ]
        for template in expected_templates:
            self.assertIn(template, policy_init.AVAILABLE_TEMPLATES)
            self.assertTrue(policy_init.AVAILABLE_TEMPLATES[template])

    def test_templates_dir_exists(self) -> None:
        """Test that the templates directory exists."""
        self.assertTrue(policy_init.TEMPLATES_DIR.exists())
        self.assertTrue(policy_init.TEMPLATES_DIR.is_dir())

    def test_all_template_files_exist(self) -> None:
        """Test that all template files exist on disk."""
        for template_name in policy_init.AVAILABLE_TEMPLATES:
            template_file = policy_init.TEMPLATES_DIR / f"{template_name}.json"
            self.assertTrue(
                template_file.exists(),
                f"Template file missing: {template_file}",
            )

    def test_list_templates_output(self) -> None:
        """Test that list_templates prints all available templates."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            policy_init.list_templates()

        output = mock_stdout.getvalue()
        self.assertIn("Available templates:", output)
        for template_name in policy_init.AVAILABLE_TEMPLATES:
            self.assertIn(template_name, output)

    def test_policy_list_flag(self) -> None:
        """Test 'policy --list' command."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(["--list"])

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Available templates:", output)

    def test_policy_list_subcommand(self) -> None:
        """Test 'policy list' subcommand."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(["list"])

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Available templates:", output)

    def test_policy_init_success(self) -> None:
        """Test 'policy init --template <name> --output <path>' success case."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "output" / "rule_policy.json"

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = policy_init.main(
                    ["init", "--template", "misra_c2012_conservative", "--output", str(output_path)]
                )

            self.assertEqual(result, 0)
            self.assertTrue(output_path.exists())

            output = mock_stdout.getvalue()
            self.assertIn("Policy initialized", output)
            self.assertIn("misra_c2012_conservative", output)
            self.assertIn(str(output_path), output)

    def test_policy_init_default_output_path(self) -> None:
        """Test 'policy init' with default output path."""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            expected_output = cwd / ".agents" / "config" / "rule_policy.json"

            with patch("sys.stdout", new_callable=StringIO):
                with patch.object(policy_init.Path, "cwd", return_value=cwd):
                    result = policy_init.main(
                        ["init", "--template", "cppcheck_common"]
                    )

            self.assertEqual(result, 0)
            self.assertTrue(expected_output.exists())

    def test_policy_init_creates_parent_directories(self) -> None:
        """Test that init_policy creates parent directories if they don't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "deep" / "nested" / "dir" / "policy.json"

            result = policy_init.init_policy(
                "misra_c2012_relaxed", output_path, force=False
            )

            self.assertEqual(result, 0)
            self.assertTrue(output_path.exists())
            self.assertTrue(output_path.parent.is_dir())

    def test_policy_init_force_overwrites_existing(self) -> None:
        """Test 'policy init --force' overwrites existing file."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            # First create the file with one template
            result1 = policy_init.init_policy(
                "misra_c2012_conservative", output_path, force=False
            )
            self.assertEqual(result1, 0)

            # Read the content
            with open(output_path, "r", encoding="utf-8") as f:
                content1 = json.load(f)

            # Overwrite with a different template using force
            result2 = policy_init.init_policy(
                "misra_c2012_relaxed", output_path, force=True
            )
            self.assertEqual(result2, 0)

            # Read the content again
            with open(output_path, "r", encoding="utf-8") as f:
                content2 = json.load(f)

            # The templates should have different defaults
            self.assertNotEqual(
                content1.get("default"),
                content2.get("default"),
            )

    def test_policy_init_rejects_existing_without_force(self) -> None:
        """Test that 'policy init' rejects existing file without --force."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            # Create the file first
            output_path.write_text("{}", encoding="utf-8")

            with patch("sys.stderr", new_callable=StringIO):
                result = policy_init.init_policy(
                    "misra_c2012_conservative", output_path, force=False
                )

            self.assertEqual(result, 1)
            # File should still contain original content
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}")

    def test_policy_init_rejects_invalid_template(self) -> None:
        """Test that 'policy init' rejects invalid template name."""
        with self.assertRaises(SystemExit):
            policy_init.parse_args(["init", "--template", "nonexistent_template"])

    def test_policy_init_template_file_not_found(self) -> None:
        """Test init_policy behavior when template file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            # Patch TEMPLATES_DIR to point to empty directory
            with patch.object(policy_init, "TEMPLATES_DIR", Path(tmp)):
                with patch("sys.stderr", new_callable=StringIO):
                    result = policy_init.init_policy(
                        "misra_c2012_conservative", output_path, force=False
                    )

            self.assertEqual(result, 1)

    def test_policy_init_valid_json_output(self) -> None:
        """Test that copied template is valid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            result = policy_init.init_policy(
                "misra_c2012_conservative", output_path, force=False
            )

            self.assertEqual(result, 0)

            # Verify JSON is valid
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertIn("default", data)
            self.assertIn("actions", data)

    def test_policy_init_output_shows_rule_count(self) -> None:
        """Test that init_policy output shows rule count."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = policy_init.init_policy(
                    "misra_c2012_conservative", output_path, force=False
                )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Rules configured:", output)
            self.assertIn("Patterns configured:", output)

    def test_policy_init_preserves_template_structure(self) -> None:
        """Test that template structure is preserved after copy."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            # Initialize from template
            result = policy_init.init_policy(
                "misra_c2012_conservative", output_path, force=False
            )
            self.assertEqual(result, 0)

            # Load original template
            template_file = policy_init.TEMPLATES_DIR / "misra_c2012_conservative.json"
            with open(template_file, "r", encoding="utf-8") as f:
                original = json.load(f)

            # Load copied policy
            with open(output_path, "r", encoding="utf-8") as f:
                copied = json.load(f)

            # Compare key structure
            self.assertEqual(original.get("default"), copied.get("default"))
            self.assertEqual(
                original.get("actions", {}).keys(),
                copied.get("actions", {}).keys(),
            )

    def test_policy_init_all_templates_valid_json(self) -> None:
        """Test that all available templates are valid JSON."""
        for template_name in policy_init.AVAILABLE_TEMPLATES:
            template_file = policy_init.TEMPLATES_DIR / f"{template_name}.json"
            with open(template_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    self.fail(f"Template {template_name} has invalid JSON: {e}")

            # Verify required fields
            self.assertIn("default", data, f"{template_name}: missing 'default'")
            self.assertIn("actions", data, f"{template_name}: missing 'actions'")

    def test_policy_init_with_force_flag_cli(self) -> None:
        """Test 'policy init --force' via CLI parsing."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"
            output_path.write_text("{}", encoding="utf-8")

            with patch("sys.stdout", new_callable=StringIO):
                with patch("sys.stderr", new_callable=StringIO):
                    result = policy_init.main(
                        [
                            "init",
                            "--template",
                            "cppcheck_common",
                            "--output",
                            str(output_path),
                            "--force",
                        ]
                    )

            self.assertEqual(result, 0)

    def test_parse_args_list_subcommand(self) -> None:
        """Test parse_args for 'list' subcommand."""
        args = policy_init.parse_args(["list"])
        self.assertEqual(args.subcommand, "list")

    def test_parse_args_init_subcommand(self) -> None:
        """Test parse_args for 'init' subcommand."""
        args = policy_init.parse_args(
            ["init", "--template", "misra_c2012_conservative"]
        )
        self.assertEqual(args.subcommand, "init")
        self.assertEqual(args.template, "misra_c2012_conservative")
        self.assertFalse(args.force)

    def test_parse_args_init_with_options(self) -> None:
        """Test parse_args for 'init' subcommand with all options."""
        args = policy_init.parse_args(
            [
                "init",
                "--template",
                "misra_c2012_relaxed",
                "--output",
                "/custom/path/policy.json",
                "--force",
            ]
        )
        self.assertEqual(args.subcommand, "init")
        self.assertEqual(args.template, "misra_c2012_relaxed")
        self.assertEqual(args.output, "/custom/path/policy.json")
        self.assertTrue(args.force)

    def test_parse_args_init_force_short_flag(self) -> None:
        """Test parse_args for 'init' with -f short flag."""
        args = policy_init.parse_args(
            ["init", "--template", "autosar_baseline", "-f"]
        )
        self.assertTrue(args.force)

    def test_parse_args_list_short_flag(self) -> None:
        """Test parse_args for --list short flag -l."""
        args = policy_init.parse_args(["-l"])
        self.assertTrue(args.list)

    def test_no_subcommand_shows_list(self) -> None:
        """Test that no subcommand shows template list."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main([])

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Available templates:", output)


if __name__ == "__main__":
    unittest.main()