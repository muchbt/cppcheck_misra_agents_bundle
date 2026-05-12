"""Unit tests for policy_init.py module."""

from __future__ import annotations

import json
import shutil
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
                ["misra_c2012_relaxed"], output_path, force=False
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
                ["misra_c2012_conservative"], output_path, force=False
            )
            self.assertEqual(result1, 0)

            # Read the content
            with open(output_path, "r", encoding="utf-8") as f:
                content1 = json.load(f)

            # Overwrite with a different template using force
            result2 = policy_init.init_policy(
                ["misra_c2012_relaxed"], output_path, force=True
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

    def test_policy_init_rejects_existing_without_force_non_tty(self) -> None:
        """Test that 'policy init' rejects existing file without --force in non-TTY mode."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            # Create the file first
            output_path.write_text("{}", encoding="utf-8")

            with patch("sys.stderr", new_callable=StringIO):
                with patch.object(policy_init.sys.stdin, "isatty", return_value=False):
                    result = policy_init.init_policy(
                        "misra_c2012_conservative", output_path, force=False
                    )

            self.assertEqual(result, 1)
            # File should still contain original content
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}")

    def test_policy_init_prompt_overwrite_existing_tty_yes(self) -> None:
        """Test that 'policy init' prompts and overwrites when user says yes in TTY."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"
            output_path.write_text("{}", encoding="utf-8")

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch.object(policy_init.sys.stdin, "isatty", return_value=True):
                    with patch("builtins.input", return_value="y"):
                        result = policy_init.init_policy(
                            ["misra_c2012_conservative"], output_path, force=False
                        )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Policy initialized", output)
            # File should now contain valid policy
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("actions", data)

    def test_policy_init_prompt_overwrite_existing_tty_no(self) -> None:
        """Test that 'policy init' prompts and aborts when user says no in TTY."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"
            output_path.write_text("{}", encoding="utf-8")

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch.object(policy_init.sys.stdin, "isatty", return_value=True):
                    with patch("builtins.input", return_value="n"):
                        result = policy_init.init_policy(
                            "misra_c2012_conservative", output_path, force=False
                        )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Aborted", output)
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
                ["misra_c2012_conservative"], output_path, force=False
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
                    ["misra_c2012_conservative"], output_path, force=False
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
                ["misra_c2012_conservative"], output_path, force=False
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

    def test_policy_init_rule_conflicts_tty_keep_existing(self) -> None:
        """Test that init_policy shows rule conflicts and user can keep existing rules."""
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy.json"

            # First, create a policy with one template
            result1 = policy_init.init_policy(
                ["misra_c2012_conservative"], output_path, force=False
            )
            self.assertEqual(result1, 0)

            # Now try to init with a different template that has conflicting rules
            # User says "y" to file overwrite, then "n" to keep existing rules for conflicts
            with patch("sys.stdout", new_callable=StringIO):
                with patch.object(policy_init.sys.stdin, "isatty", return_value=True):
                    with patch("builtins.input", side_effect=["y", "n"]):
                        result2 = policy_init.init_policy(
                            ["misra_c2012_relaxed"], output_path, force=False
                        )

            self.assertEqual(result2, 0)

            # Read the result - conflicts should have been kept from original
            with open(output_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
            # The description should reflect the new merge
            self.assertIn("misra_c2012_relaxed", result_data.get("_description", ""))
            # But rules that existed in conservative should have been kept
            # (since user said no to overwriting conflicts)

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
        self.assertEqual(args.templates, ["misra_c2012_conservative"])
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
        self.assertEqual(args.templates, ["misra_c2012_relaxed"])
        self.assertEqual(args.output, "/custom/path/policy.json")
        self.assertTrue(args.force)

    def test_parse_args_init_multiple_templates(self) -> None:
        """Test parse_args for 'init' with multiple --template args."""
        args = policy_init.parse_args(
            ["init", "--template", "misra_c2012_relaxed", "--template", "cppcheck_common"]
        )
        self.assertEqual(args.subcommand, "init")
        self.assertEqual(args.templates, ["misra_c2012_relaxed", "cppcheck_common"])
        self.assertFalse(args.force)

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

    # New tests for policy list --rule-id subcommand

    def test_policy_list_rule_id_pattern(self) -> None:
        """Test 'policy list --rule-id' with pattern matching."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(["list", "--rule-id", "misra*"])

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Default Policy:", output)
        self.assertIn("misra-c2012-2.2:", output)
        self.assertIn("misra-c2012-8.9:", output)
        self.assertIn("misra-c2012-17.7:", output)
        self.assertIn("Patterns", output)

    def test_policy_list_rule_id_no_match(self) -> None:
        """Test 'policy list --rule-id' with no matching rules."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(["list", "--rule-id", "nonexistent*"])

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Default Policy:", output)
        # No rules section when no matching
        self.assertNotIn("Rules (", output)

    def test_policy_list_rule_id_contains_match(self) -> None:
        """Test 'policy list --rule-id' with substring matching."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(["list", "--rule-id", "variable"])

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("unusedVariable:", output)
        self.assertIn("unreadVariable:", output)
        self.assertIn("constVariable:", output)

    # New tests for policy test subcommand

    def test_policy_test_action_match(self) -> None:
        """Test 'policy test' with exact rule ID match."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(
                ["test", "--rule-id", "unusedVariable", "--file", "/src/test.c"]
            )

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Match source: actions", output)
        self.assertIn("Matched rule ID: unusedVariable", output)
        self.assertIn("action: auto_fix", output)

    def test_policy_test_pattern_match(self) -> None:
        """Test 'policy test' with pattern matching."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(
                ["test", "--rule-id", "unknownRule", "--file", "/src/volatile.c"]
            )

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Match source: patterns", output)
        self.assertIn("Matched pattern: 'volatile'", output)
        self.assertIn("action: needs_manual_review", output)

    def test_policy_test_default_fallback(self) -> None:
        """Test 'policy test' with default fallback."""
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = policy_init.main(
                ["test", "--rule-id", "unknownRule", "--file", "/src/normal.c"]
            )

        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Match source: default", output)
        self.assertIn("action: needs_manual_review", output)

    def test_policy_test_missing_policy_file(self) -> None:
        """Test 'policy test' with missing policy file."""
        with tempfile.TemporaryDirectory() as tmp:
            nonexistent = Path(tmp) / "nonexistent.json"
            with patch("sys.stderr", new_callable=StringIO):
                result = policy_init.main(
                    [
                        "-p",
                        str(nonexistent),
                        "test",
                        "--rule-id",
                        "unusedVariable",
                        "--file",
                        "/src/test.c",
                    ]
                )
            self.assertEqual(result, 1)

    # New tests for policy add subcommand

    def test_policy_add_new_rule(self) -> None:
        """Test 'policy add' with a new rule."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            # Copy existing policy
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = policy_init.main(
                    [
                        "-p",
                        str(policy_path),
                        "add",
                        "--rule-id",
                        "newTestRule",
                        "--action",
                        "auto_fix",
                    ]
                )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Added rule 'newTestRule'", output)
            self.assertIn("action: auto_fix", output)

            # Verify rule was added
            with open(policy_path) as f:
                data = json.load(f)
            self.assertIn("newTestRule", data["actions"])
            self.assertEqual(data["actions"]["newTestRule"]["action"], "auto_fix")

    def test_policy_add_existing_rule_without_force(self) -> None:
        """Test 'policy add' rejects existing rule without --force in non-TTY mode."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            with patch("sys.stderr", new_callable=StringIO):
                with patch.object(policy_init.sys.stdin, "isatty", return_value=False):
                    result = policy_init.main(
                        [
                            "-p",
                            str(policy_path),
                            "add",
                            "--rule-id",
                            "unusedVariable",
                            "--action",
                            "skip",
                        ]
                    )

            self.assertEqual(result, 1)

    def test_policy_add_existing_rule_tty_prompt_yes(self) -> None:
        """Test 'policy add' prompts and overwrites when user confirms in TTY."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch.object(policy_init.sys.stdin, "isatty", return_value=True):
                    with patch("builtins.input", return_value="y"):
                        result = policy_init.main(
                            [
                                "-p",
                                str(policy_path),
                                "add",
                                "--rule-id",
                                "unusedVariable",
                                "--action",
                                "skip",
                            ]
                        )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Updated rule 'unusedVariable'", output)
            with open(policy_path) as f:
                data = json.load(f)
            self.assertEqual(data["actions"]["unusedVariable"]["action"], "skip")

    def test_policy_add_existing_rule_tty_prompt_no(self) -> None:
        """Test 'policy add' prompts and aborts when user declines in TTY."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch.object(policy_init.sys.stdin, "isatty", return_value=True):
                    with patch("builtins.input", return_value="n"):
                        result = policy_init.main(
                            [
                                "-p",
                                str(policy_path),
                                "add",
                                "--rule-id",
                                "unusedVariable",
                                "--action",
                                "skip",
                            ]
                        )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Aborted", output)
            with open(policy_path) as f:
                data = json.load(f)
            # Original rule should be unchanged
            self.assertNotEqual(data["actions"]["unusedVariable"]["action"], "skip")

    def test_policy_add_existing_rule_with_force(self) -> None:
        """Test 'policy add' with --force overwrites existing rule."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = policy_init.main(
                    [
                        "-p",
                        str(policy_path),
                        "add",
                        "--rule-id",
                        "unusedVariable",
                        "--action",
                        "skip",
                        "--force",
                    ]
                )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Updated rule 'unusedVariable'", output)

            # Verify rule was updated
            with open(policy_path) as f:
                data = json.load(f)
            self.assertEqual(data["actions"]["unusedVariable"]["action"], "skip")

    def test_policy_add_with_all_options(self) -> None:
        """Test 'policy add' with all optional parameters."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                result = policy_init.main(
                    [
                        "-p",
                        str(policy_path),
                        "add",
                        "--rule-id",
                        "testRule",
                        "--action",
                        "careful_fix",
                        "--risk-level",
                        "medium",
                        "--risk-tags",
                        "testing,experimental",
                        "--risk-reason",
                        "Test reason",
                    ]
                )

            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("risk_level: medium", output)
            self.assertIn("risk_tags: testing, experimental", output)
            self.assertIn("risk_reason: Test reason", output)

    def test_policy_add_auto_risk_level(self) -> None:
        """Test 'policy add' auto-assigns risk_level based on action."""
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.json"
            shutil.copy2(policy_init.DEFAULT_POLICY_PATH, policy_path)

            # auto_fix should get low
            policy_init.main(
                ["-p", str(policy_path), "add", "--rule-id", "testAuto", "--action", "auto_fix"]
            )
            with open(policy_path) as f:
                data = json.load(f)
            self.assertEqual(data["actions"]["testAuto"]["risk_level"], "low")

            # careful_fix should get medium
            policy_init.main(
                ["-p", str(policy_path), "add", "--rule-id", "testCareful", "--action", "careful_fix", "--force"]
            )
            with open(policy_path) as f:
                data = json.load(f)
            self.assertEqual(data["actions"]["testCareful"]["risk_level"], "medium")

            # skip should get high
            policy_init.main(
                ["-p", str(policy_path), "add", "--rule-id", "testSkip", "--action", "skip"]
            )
            with open(policy_path) as f:
                data = json.load(f)
            self.assertEqual(data["actions"]["testSkip"]["risk_level"], "high")

    def test_parse_args_test_subcommand(self) -> None:
        """Test parse_args for 'test' subcommand."""
        args = policy_init.parse_args(
            ["test", "--rule-id", "unusedVariable", "--file", "/src/test.c"]
        )
        self.assertEqual(args.subcommand, "test")
        self.assertEqual(args.rule_id, "unusedVariable")
        self.assertEqual(args.file, "/src/test.c")

    def test_parse_args_add_subcommand(self) -> None:
        """Test parse_args for 'add' subcommand."""
        args = policy_init.parse_args(
            ["add", "--rule-id", "testRule", "--action", "auto_fix"]
        )
        self.assertEqual(args.subcommand, "add")
        self.assertEqual(args.rule_id, "testRule")
        self.assertEqual(args.action, "auto_fix")

    def test_parse_args_add_with_options(self) -> None:
        """Test parse_args for 'add' subcommand with all options."""
        args = policy_init.parse_args(
            [
                "add",
                "--rule-id",
                "testRule",
                "--action",
                "careful_fix",
                "--risk-level",
                "medium",
                "--risk-tags",
                "tag1,tag2",
                "--risk-reason",
                "test reason",
                "--force",
            ]
        )
        self.assertEqual(args.risk_level, "medium")
        self.assertEqual(args.risk_tags, "tag1,tag2")
        self.assertEqual(args.risk_reason, "test reason")
        self.assertTrue(args.force)

    def test_parse_args_policy_file(self) -> None:
        """Test parse_args for --policy-file option."""
        args = policy_init.parse_args(
            ["-p", "/custom/policy.json", "list", "--rule-id", "misra*"]
        )
        self.assertEqual(args.policy_file, "/custom/policy.json")


if __name__ == "__main__":
    unittest.main()