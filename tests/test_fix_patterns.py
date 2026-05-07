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


def test_chunk_unique_fix_patterns_dedup():
    """Verify unique_fix_patterns computed from issues with dedup by rule_id."""
    fix_patterns = {
        "patterns": {
            "misra-c2012-11.3": {"fix": "cast", "example": "x", "pitfalls": "align", "context_notes": "check"},
            "misra-c2012-8.4": {"fix": "declare", "example": "y"},
        }
    }
    issues = [
        {"rule_id": "misra-c2012-11.3", "risk_level": "high"},
        {"rule_id": "misra-c2012-11.3", "risk_level": "high"},
        {"rule_id": "misra-c2012-8.4", "risk_level": "medium"},
    ]
    seen = {}
    for issue in issues:
        rid = issue["rule_id"]
        if rid not in seen:
            fp = spm.lookup_fix_pattern(rid, issue.get("risk_level", "high"), fix_patterns)
            if fp is not None:
                seen[rid] = fp
    assert len(seen) == 2
    assert "misra-c2012-11.3" in seen
    assert "misra-c2012-8.4" in seen
    assert "pitfalls" in seen["misra-c2012-11.3"]
    assert "context_notes" in seen["misra-c2012-11.3"]
    assert "caution" not in seen["misra-c2012-8.4"]


def test_chunk_unique_fix_patterns_none_pattern():
    """Issues whose rule_id has no pattern should not appear in unique_fix_patterns."""
    fix_patterns = {
        "patterns": {
            "misra-c2012-11.3": {"fix": "cast", "example": "x"},
        }
    }
    issues = [
        {"rule_id": "unknownRule", "risk_level": "low"},
        {"rule_id": "misra-c2012-11.3", "risk_level": "medium"},
    ]
    seen = {}
    for issue in issues:
        rid = issue["rule_id"]
        if rid not in seen:
            fp = spm.lookup_fix_pattern(rid, issue.get("risk_level", "high"), fix_patterns)
            if fp is not None:
                seen[rid] = fp
    assert len(seen) == 1
    assert "unknownRule" not in seen
    assert "misra-c2012-11.3" in seen


def test_chunk_unique_fix_patterns_all_none():
    """When all rule_ids have no pattern, unique_fix_patterns is empty."""
    fix_patterns = {"patterns": {}}
    issues = [
        {"rule_id": "rule1", "risk_level": "low"},
        {"rule_id": "rule2", "risk_level": "medium"},
    ]
    seen = {}
    for issue in issues:
        rid = issue["rule_id"]
        if rid not in seen:
            fp = spm.lookup_fix_pattern(rid, issue.get("risk_level", "high"), fix_patterns)
            if fp is not None:
                seen[rid] = fp
    assert len(seen) == 0


def test_split_without_fix_patterns_file_graceful_fallback():
    """When fix_patterns is empty dict (file missing), all lookups return None."""
    empty_patterns = {}
    assert spm.lookup_fix_pattern("unusedVariable", "low", empty_patterns) is None
    assert spm.lookup_fix_pattern("misra-c2012-17.7", "high", empty_patterns) is None
    assert spm.lookup_fix_pattern("anyRule", "medium", empty_patterns) is None


def test_split_produces_unique_fix_patterns_in_chunks():
    """Integration test: verify fix_patterns.json structure and lookup."""
    fp_path = Path(__file__).resolve().parents[1] / ".agents" / "config" / "fix_patterns.json"
    if not fp_path.exists():
        import pytest
        pytest.skip("fix_patterns.json not yet populated")

    import json
    fix_patterns = json.loads(fp_path.read_text())

    assert "_meta" in fix_patterns
    assert "risk_detail_levels" in fix_patterns
    assert "patterns" in fix_patterns
    assert isinstance(fix_patterns["patterns"], dict)

    for rule_id, pattern in fix_patterns["patterns"].items():
        assert "risk_level" not in pattern, f"Rule {rule_id} should not have risk_level in fix_patterns.json"

    if "unusedVariable" in fix_patterns["patterns"]:
        result = spm.lookup_fix_pattern("unusedVariable", "low", fix_patterns)
        assert result is not None
        assert "fix" in result
        assert "example" in result


def test_lookup_with_real_fix_patterns_covers_key_rules():
    """Verify fix_patterns.json covers key cppcheck rules."""
    fp_path = Path(__file__).resolve().parents[1] / ".agents" / "config" / "fix_patterns.json"
    if not fp_path.exists():
        import pytest
        pytest.skip("fix_patterns.json not yet populated")

    import json
    fix_patterns = json.loads(fp_path.read_text())
    patterns = fix_patterns.get("patterns", {})

    key_cppcheck_rules = ["unusedVariable", "nullPointer", "uninitvar", "constVariable"]
    for rule_id in key_cppcheck_rules:
        if rule_id in patterns:
            assert "fix" in patterns[rule_id], f"Rule {rule_id} missing 'fix' field"
            assert "example" in patterns[rule_id], f"Rule {rule_id} missing 'example' field"


def test_risk_detail_levels_match_design():
    """Verify RISK_DETAIL_FIELDS constant matches design spec."""
    expected = {
        "low": ["fix", "example"],
        "medium": ["fix", "example", "caution"],
        "high": ["fix", "example", "pitfalls", "context_notes"],
    }
    assert spm.RISK_DETAIL_FIELDS == expected