"""Unit tests for the confidence engine. No Ollama / network required."""

import shutil

import pytest

from app import (
    basic_confidence_check,
    find_duplicate_jsx_attributes,
    find_duplicate_object_keys,
    find_javascript_syntax_errors,
    find_likely_undefined_vars,
    find_mismatched_jsx_tags,
    find_missing_hook_imports,
    find_python_syntax_errors,
    strip_markdown_fences,
)


CLEAN_JS = """
function greet(name) {
  if (!name) {
    return "Hello, guest";
  }
  return `Hello, ${name}`;
}
"""

BUGGY_REACT = """
function TodoItem({ todo }) {
  return (
    <div className="todo-item" className="done">
      <span>{todo.title}</span>
    </div>
  );
}
"""


def test_strip_markdown_fences():
    raw = "```javascript\nconst x = 1;\n```"
    assert strip_markdown_fences(raw) == "const x = 1;"


def test_clean_js_is_high_confidence():
    result = basic_confidence_check(CLEAN_JS, "JavaScript")
    assert result["status"] == "high_confidence"
    assert result["issues"] == []


def test_duplicate_jsx_attribute():
    issues = find_duplicate_jsx_attributes(BUGGY_REACT)
    assert any("className" in i for i in issues)


def test_undefined_var_toggle_emit():
    code = """
function TodoItem({ todo }) {
  return <button onClick={() => toggle.emit(todo)}>x</button>;
}
"""
    issues = find_likely_undefined_vars(code)
    assert any("toggle" in i for i in issues)


def test_mismatched_jsx_tags():
    code = "<div><span>hi</div>"
    issues = find_mismatched_jsx_tags(code)
    assert issues


def test_missing_hook_import():
    code = """
function Counter() {
  const [n, setN] = useState(0);
  return n;
}
"""
    issues = find_missing_hook_imports(code)
    assert any("useState" in i for i in issues)


def test_hook_imported_is_clean():
    code = """
import { useState } from 'react';
function Counter() {
  const [n, setN] = useState(0);
  return n;
}
"""
    assert find_missing_hook_imports(code) == []


def test_duplicate_object_keys():
    issues = find_duplicate_object_keys("{ name: 'a', name: 'b' }")
    assert any("name" in i for i in issues)


def test_python_syntax_error():
    issues = find_python_syntax_errors("def foo(\n")
    assert issues


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_javascript_syntax_is_clean():
    assert find_javascript_syntax_errors("const answer = 42;") == []


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
def test_javascript_syntax_error_is_low_confidence():
  result = basic_confidence_check("const answer = ;", "JavaScript")
  assert result["status"] == "low_confidence"
  assert any("JavaScript syntax error" in issue for issue in result["issues"])


def test_jsx_checks_skipped_for_python_target():
    result = basic_confidence_check(BUGGY_REACT, "Python")
    joined = " ".join(result["issues"])
    assert "className" not in joined


def test_buggy_react_is_low_confidence():
    code = """
function TodoItem({ todo }) {
  return (
    <div className="a" className="b">
      <button onClick={() => toggle.emit(todo)}>x</button>
    </div>
  );
}
"""
    result = basic_confidence_check(code, "React")
    assert result["status"] == "low_confidence"
    joined = " ".join(result["issues"])
    assert "className" in joined
    assert "toggle" in joined


def test_migration_note_is_medium_when_no_structural_bugs():
    code = CLEAN_JS + "\n// MIGRATION_NOTE: check locale"
    result = basic_confidence_check(code, "JavaScript")
    assert result["status"] == "medium_confidence"


def test_example_files_listed_in_manifest_exist():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "examples" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest, "examples/manifest.json is empty"
    for row in manifest:
        path = root / "examples" / row["file"]
        assert path.is_file(), f"missing {path}"
        assert path.read_text(encoding="utf-8").strip()
