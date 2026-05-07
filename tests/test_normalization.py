"""Tests for LLM output normalization in common.py.

Covers:
- normalize_issue_status_delta: wrapper key aliases, field aliases, passthrough keys
- normalize_file_change_delta: wrapper key aliases, file path aliases, linked_issues aliases
- _build_issue_edit_index: linked_issues alias handling
- _first_matching_str: generic key-lookup helper
- _ensure_dict: JSON array auto-wrapping
- _repair_json_string: markdown fence and trailing comma repair
- load_json: robustness for LLM output
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402


# ---------------------------------------------------------------------------
# _first_matching_str
# ---------------------------------------------------------------------------

class TestFirstMatchingStr:
    def test_first_key_wins(self):
        item = {"file": "a.c", "file_path": "b.c", "path": "c.c"}
        assert common._first_matching_str(item, common._KNOWN_FILE_PATH_KEYS) == "a.c"

    def test_fallback_to_second(self):
        item = {"file_path": "b.c", "path": "c.c"}
        assert common._first_matching_str(item, common._KNOWN_FILE_PATH_KEYS) == "b.c"

    def test_fallback_to_third(self):
        item = {"path": "c.c"}
        assert common._first_matching_str(item, common._KNOWN_FILE_PATH_KEYS) == "c.c"

    def test_empty_string_skipped(self):
        item = {"file": "  ", "file_path": "b.c"}
        assert common._first_matching_str(item, common._KNOWN_FILE_PATH_KEYS) == "b.c"

    def test_no_match_returns_default(self):
        item = {"other": "x"}
        assert common._first_matching_str(item, common._KNOWN_FILE_PATH_KEYS) == ""
        assert common._first_matching_str(item, common._KNOWN_FILE_PATH_KEYS, "fallback") == "fallback"


# ---------------------------------------------------------------------------
# normalize_issue_status_delta — wrapper key aliases
# ---------------------------------------------------------------------------

class TestStatusDeltaWrapperAliases:
    EMPTY_FCD = {"src/a.c": {"edits": []}}

    def test_status_changes_key(self):
        raw = {"status_changes": [
            {"issue_key": "a.c:1:nullPointer:abc", "new_status": "fixed"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert "a.c:1:nullPointer:abc" in result
        assert result["a.c:1:nullPointer:abc"]["status"] == "fixed"

    def test_issue_status_changes_key(self):
        raw = {"issue_status_changes": [
            {"issue_key": "a.c:1:nullPointer:abc", "new_status": "fixed"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert "a.c:1:nullPointer:abc" in result

    def test_issue_status_delta_key(self):
        """LLM often uses same key name as the artifact filename."""
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:nullPointer:abc", "new_status": "fixed"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert "a.c:1:nullPointer:abc" in result


# ---------------------------------------------------------------------------
# normalize_issue_status_delta — field aliases
# ---------------------------------------------------------------------------

class TestStatusDeltaFieldAliases:
    EMPTY_FCD = {"src/a.c": {"edits": []}}

    def test_review_required_after_fix_aliased(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
             "review_required_after_fix": True},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        patch = result["a.c:1:rule:abc"]
        assert patch["requires_review_after_fix"] is True
        assert "review_required_after_fix" not in patch

    def test_requires_review_aliased(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
             "requires_review": True},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        patch = result["a.c:1:rule:abc"]
        assert patch["requires_review_after_fix"] is True

    def test_fix_method_aliased_to_fix_summary(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
             "fix_method": "added const qualifier"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        patch = result["a.c:1:rule:abc"]
        assert patch["fix_summary"] == "added const qualifier"
        assert "fix_method" not in patch

    def test_fix_summary_passthrough(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
             "fix_summary": "added const qualifier"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert result["a.c:1:rule:abc"]["fix_summary"] == "added const qualifier"

    def test_status_after_aliased(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "status_after": "fixed"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert result["a.c:1:rule:abc"]["status"] == "fixed"

    def test_reason_aliases(self):
        for key in ("reason", "blocker_reason", "message"):
            raw = {"issue_status_delta": [
                {"issue_key": "a.c:1:rule:abc", "new_status": "blocked", key: "ISR path"},
            ]}
            result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
            assert result["a.c:1:rule:abc"]["reason"] == "ISR path", f"Failed for key={key}"

    def test_risk_level_risk_reason_passthrough(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
             "risk_level": "high", "risk_reason": "signature change"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        patch = result["a.c:1:rule:abc"]
        assert patch["risk_level"] == "high"
        assert patch["risk_reason"] == "signature change"

    def test_edit_ids_linked_from_file_change_delta(self):
        fcd = {"src/a.c": {"edits": [
            {"edit_id": "src/a.c#001", "related_issue_keys": ["a.c:1:rule:abc"]},
        ]}}
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed"},
        ]}
        result = common.normalize_issue_status_delta(raw, fcd, 0)
        assert result["a.c:1:rule:abc"]["edit_ids"] == ["src/a.c#001"]

    def test_single_issue_format(self):
        raw = {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
               "risk_level": "low"}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert "a.c:1:rule:abc" in result
        assert result["a.c:1:rule:abc"]["status"] == "fixed"
        assert result["a.c:1:rule:abc"]["risk_level"] == "low"

    def test_single_issue_format_with_fix_method_alias(self):
        raw = {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
               "fix_method": "added cast"}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert result["a.c:1:rule:abc"]["fix_summary"] == "added cast"
        assert "fix_method" not in result["a.c:1:rule:abc"]


# ---------------------------------------------------------------------------
# normalize_file_change_delta — wrapper key aliases
# ---------------------------------------------------------------------------

class TestFileChangeDeltaWrapperAliases:
    EMPTY_BASE = {}

    def _make_item(self, file_path="src/a.c", summary="fix"):
        return {"file": file_path, "summary": summary,
                "linked_issues": ["a.c:1:rule:abc"]}

    def test_file_changes_key(self):
        raw = {"file_changes": [self._make_item()]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result

    def test_files_changed_key(self):
        raw = {"files_changed": [self._make_item()]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result

    def test_files_touched_key(self):
        raw = {"files_touched": [self._make_item()]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result

    def test_file_edits_key(self):
        raw = {"file_edits": [self._make_item()]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result


# ---------------------------------------------------------------------------
# normalize_file_change_delta — file path field aliases
# ---------------------------------------------------------------------------

class TestFileChangeDeltaFilePathAliases:
    EMPTY_BASE = {}

    def test_file_key(self):
        raw = {"file_changes": [
            {"file": "src/a.c", "summary": "fix", "linked_issues": ["k:1"]},
        ]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result

    def test_file_path_key(self):
        raw = {"file_changes": [
            {"file_path": "src/a.c", "summary": "fix", "linked_issues": ["k:1"]},
        ]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result

    def test_path_key(self):
        raw = {"file_changes": [
            {"path": "src/a.c", "summary": "fix", "linked_issues": ["k:1"]},
        ]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/a.c" in result

    def test_files_inspected_path_aliases(self):
        raw = {"files_inspected": [
            {"file_path": "src/b.c", "change_summary": "no changes needed"},
        ]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/b.c" in result
        assert result["src/b.c"]["edits"] == []

    def test_single_file_path_aliases(self):
        raw = {"file_path": "src/c.c", "edits": [
            {"edit_id": "e1", "summary": "fix", "chunk_index": 0,
             "related_issue_keys": ["k:1"]},
        ]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "src/c.c" in result


# ---------------------------------------------------------------------------
# _build_issue_edit_index — linked_issues aliases
# ---------------------------------------------------------------------------

class TestBuildIssueEditIndex:
    def test_related_issue_keys(self):
        fcd = {"src/a.c": {"edits": [
            {"edit_id": "e1", "related_issue_keys": ["k:1", "k:2"]},
        ]}}
        result = common._build_issue_edit_index(fcd)
        assert result == {"k:1": ["e1"], "k:2": ["e1"]}

    def test_linked_issues_alias(self):
        fcd = {"src/a.c": {"edits": [
            {"edit_id": "e1", "linked_issues": ["k:1"]},
        ]}}
        result = common._build_issue_edit_index(fcd)
        assert result == {"k:1": ["e1"]}

    def test_linked_issue_keys_alias(self):
        fcd = {"src/a.c": {"edits": [
            {"edit_id": "e1", "linked_issue_keys": ["k:1"]},
        ]}}
        result = common._build_issue_edit_index(fcd)
        assert result == {"k:1": ["e1"]}

    def test_priority_related_over_linked(self):
        fcd = {"src/a.c": {"edits": [
            {"edit_id": "e1", "related_issue_keys": ["k:1"],
             "linked_issues": ["k:2"]},
        ]}}
        result = common._build_issue_edit_index(fcd)
        assert "k:1" in result
        assert "k:2" not in result


# ---------------------------------------------------------------------------
# Integration: full pasted LLM output from the issue
# ---------------------------------------------------------------------------

class TestRealWorldLLMOutput:
    """Test with the exact structure from the user's pasted issue_status_delta."""

    EMPTY_FCD = {"src/LIBS/PROENG/ProEng.c": {"edits": []},
                 "src/LIBS/PROENG/ProEng.h": {"edits": []},
                 "src/LIBS/SYS/apn_basic_type.h": {"edits": []}}

    def test_pasted_issue_status_delta_format(self):
        raw = {
            "issue_status_delta": [
                {
                    "issue_key": "src/LIBS/PROENG/ProEng.c:152:constParameterPointer:0f6f02ab",
                    "new_status": "fixed",
                    "risk_level": "high",
                    "risk_reason": "Changed function signature (added const)",
                    "review_required_after_fix": True,
                    "fix_summary": "Added const to astProcCTB_p parameter",
                },
                {
                    "issue_key": "src/LIBS/PROENG/ProEng.h:19:misra-c2012-21.1:88377c8f",
                    "new_status": "fixed",
                    "risk_level": "high",
                    "risk_reason": "Renamed include guard macro",
                    "review_required_after_fix": True,
                    "fix_summary": "Renamed include guard from _PROENGIN_H_ to PROENGIN_H",
                },
            ]
        }
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)

        key1 = "src/LIBS/PROENG/ProEng.c:152:constParameterPointer:0f6f02ab"
        assert key1 in result
        assert result[key1]["status"] == "fixed"
        assert result[key1]["risk_level"] == "high"
        assert result[key1]["requires_review_after_fix"] is True
        assert result[key1]["fix_summary"] == "Added const to astProcCTB_p parameter"

        key2 = "src/LIBS/PROENG/ProEng.h:19:misra-c2012-21.1:88377c8f"
        assert key2 in result
        assert result[key2]["requires_review_after_fix"] is True

    def test_fix_method_alias_in_real_output(self):
        raw = {"issue_status_delta": [
            {"issue_key": "a.c:1:rule:abc", "new_status": "fixed",
             "risk_level": "high", "fix_method": "added const"},
        ]}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert result["a.c:1:rule:abc"]["fix_summary"] == "added const"
        assert "fix_method" not in result["a.c:1:rule:abc"]


# ---------------------------------------------------------------------------
# _ensure_dict
# ---------------------------------------------------------------------------

class TestEnsureDict:
    def test_dict_passthrough(self):
        assert common._ensure_dict({"a": 1}) == {"a": 1}

    def test_list_wraps_as_status_changes(self):
        result = common._ensure_dict([{"issue_key": "k1"}])
        assert result == {"status_changes": [{"issue_key": "k1"}]}

    def test_empty_list_returns_empty_dict(self):
        assert common._ensure_dict([]) == {"status_changes": []}

    def test_non_dict_non_list_returns_empty_dict(self):
        assert common._ensure_dict("hello") == {}


# ---------------------------------------------------------------------------
# _repair_json_string
# ---------------------------------------------------------------------------

class TestRepairJsonString:
    def test_valid_json_dict(self):
        assert common._repair_json_string('{"a": 1}', {}) == {"a": 1}

    def test_json_with_markdown_fences(self):
        raw = '```json\n{"a": 1}\n```'
        assert common._repair_json_string(raw, {}) == {"a": 1}

    def test_json_with_generic_fences(self):
        raw = '```\n{"a": 1}\n```'
        assert common._repair_json_string(raw, {}) == {"a": 1}

    def test_trailing_comma_dict(self):
        raw = '{"a": 1,}'
        assert common._repair_json_string(raw, {}) == {"a": 1}

    def test_trailing_comma_list(self):
        raw = '[1, 2,]'
        assert common._repair_json_string(raw, []) == [1, 2]

    def test_completely_invalid_returns_default(self):
        assert common._repair_json_string("not json at all", {"default": True}) == {"default": True}


# ---------------------------------------------------------------------------
# load_json robustness
# ---------------------------------------------------------------------------

class TestLoadJsonRobust:
    def test_load_json_array(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('[{"issue_key": "k1", "new_status": "fixed"}]', encoding="utf-8")
        data = common.load_json(p, {})
        assert isinstance(data, list)
        assert len(data) == 1

    def test_load_required_json_object_coerces_array(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('[{"issue_key": "k1"}]', encoding="utf-8")
        data = common._load_required_json_object(p)
        assert "status_changes" in data
        assert data["status_changes"][0]["issue_key"] == "k1"

    def test_load_required_json_object_plain_dict(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        data = common._load_required_json_object(p)
        assert data == {"a": 1}

    def test_load_json_markdown_fenced(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('```json\n{"a": 1}\n```', encoding="utf-8")
        data = common.load_json(p, {})
        assert data == {"a": 1}