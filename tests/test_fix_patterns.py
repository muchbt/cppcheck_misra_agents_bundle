"""Tests for fix pattern lookup and chunk dedup logic."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import split_cppcheck_xml as spm


def test_lookup_fix_pattern_low_risk():
    patterns = {"patterns": {"unusedVariable": {"fix": "Remove.", "example": "/* fix */", "caution": "Be careful."}}}
    result = spm.lookup_fix_pattern("unusedVariable", "low", patterns)
    assert result is not None
    assert "fix" in result
    assert "example" in result
    assert "caution" not in result
    assert "pitfalls" not in result


def test_lookup_fix_pattern_medium_risk():
    patterns = {"patterns": {"misra-c2012-8.9": {"fix": "Add static.", "example": "static int x;", "caution": "Verify scope."}}}
    result = spm.lookup_fix_pattern("misra-c2012-8.9", "medium", patterns)
    assert result is not None
    assert "fix" in result
    assert "example" in result
    assert "caution" in result
    assert "pitfalls" not in result


def test_lookup_fix_pattern_high_risk():
    patterns = {"patterns": {"nullPointer": {"fix": "Add NULL guard.", "example": "if (p == NULL)", "pitfalls": "All paths.", "context_notes": "Safety-critical."}}}
    result = spm.lookup_fix_pattern("nullPointer", "high", patterns)
    assert result is not None
    assert "fix" in result
    assert "example" in result
    assert "pitfalls" in result
    assert "context_notes" in result


def test_lookup_fix_pattern_high_risk_with_all_fields():
    patterns = {"patterns": {"nullPointer": {"fix": "Add NULL guard.", "example": "if (p == NULL)", "caution": "Check.", "pitfalls": "All paths.", "context_notes": "Safety."}}}
    result = spm.lookup_fix_pattern("nullPointer", "high", patterns)
    assert "fix" in result
    assert "example" in result
    assert "pitfalls" in result
    assert "context_notes" in result
    assert "caution" not in result


def test_lookup_fix_pattern_missing_rule_returns_none():
    patterns = {"patterns": {"unusedVariable": {"fix": "Remove.", "example": "/* fix */"}}}
    result = spm.lookup_fix_pattern("nonexistentRule", "low", patterns)
    assert result is None


def test_lookup_fix_pattern_none_patterns_returns_none():
    result = spm.lookup_fix_pattern("unusedVariable", "low", None)
    assert result is None


def test_lookup_fix_pattern_empty_patterns_returns_none():
    result = spm.lookup_fix_pattern("unusedVariable", "low", {})
    assert result is None


def test_lookup_fix_pattern_unknown_risk_level_defaults_high():
    patterns = {"patterns": {"testRule": {"fix": "Fix it.", "example": "/* fix */", "pitfalls": "Danger.", "context_notes": "Note."}}}
    result = spm.lookup_fix_pattern("testRule", "unknown_level", patterns)
    assert result is not None
    assert "pitfalls" in result
    assert "context_notes" in result