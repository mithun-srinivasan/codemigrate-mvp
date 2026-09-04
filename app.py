"""
CodeMigrate MVP Backend (100% FREE VERSION - uses Ollama, runs locally)
------------------------------------------------------------------------
What this does (explain to your team like this):
1. Person picks source language + target language, pastes code.
2. We build a clear instruction (prompt) telling the AI exactly what to do.
3. We send that to a FREE AI model running on YOUR OWN laptop via Ollama
   (no API key, no cost, no internet needed after setup).
4. We get back the converted code and send it to the frontend.
5. We run a custom confidence layer (duplicate JSX attrs, undefined vars,
   mismatched tags, missing hook imports, duplicate object keys, unbalanced
   brackets, plus Python ast.parse when the target is Python).

SETUP (one time, free, ~10 min):
1. Download Ollama from https://ollama.com/download (Windows/Mac/Linux)
2. Install it, then open a terminal and run:
     ollama pull qwen2.5-coder:1.5b
   (This downloads a free ~1GB code-specialized model, sized for ~6GB RAM laptops)
3. Ollama runs a local server automatically at http://localhost:11434

Optional: on a machine with 16GB+ RAM you can pull qwen2.5-coder:7b and
change MODEL_NAME below to match. Do not use 7b as the default on this MVP.

Run backend with: python app.py
Needs: pip install flask flask-cors requests
"""

import ast
import json
import os
import re
import requests
import shutil
import subprocess
import tempfile
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_DIR = os.path.join(ROOT_DIR, "examples")

app = Flask(__name__)
CORS(app)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:1.5b"  # free, runs locally - sized for low-RAM laptops

# The prompt is the most important part of this MVP.
# We are VERY explicit so the model doesn't add explanations or markdown fences.
PROMPT_TEMPLATE = """You are an expert software engineer specializing in code migration.

Convert the following {source_lang} code into equivalent, idiomatic {target_lang} code.

Rules:
- Preserve the exact logic and behavior.
- Use idiomatic {target_lang} patterns and naming conventions, not a literal line-by-line translation.
- Do NOT include explanations, comments about the conversion, or markdown code fences.
- Output ONLY the converted {target_lang} code.
- If something cannot be directly translated, include a single-line comment in the
  target language starting with "MIGRATION_NOTE:" explaining what a human should check.

Source ({source_lang}):
{code}
"""


def strip_markdown_fences(text: str) -> str:
    """LLMs sometimes add ```lang ... ``` even when told not to. Clean it up."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"```$", "", text)
    return text.strip()


def find_duplicate_jsx_attributes(code: str) -> list:
    """
    Catches bugs like: <div className="a" className="b">
    The second one silently wins in JSX and the first is dead code - a real
    bug the model can produce, and one plain 'balanced brackets' checks miss.
    """
    issues = []
    # Look at each JSX-looking opening tag: <TagName attr="x" attr2={y} ...>
    for tag_match in re.finditer(r"<([A-Za-z][\w.]*)\s+([^>]*?)/?>", code):
        tag_name = tag_match.group(1)
        attrs_str = tag_match.group(2)
        attr_names = re.findall(r"([A-Za-z_][\w-]*)\s*=", attrs_str)
        seen = set()
        dupes = set()
        for name in attr_names:
            if name in seen:
                dupes.add(name)
            seen.add(name)
        for d in dupes:
            issues.append(f"Duplicate '{d}' attribute on <{tag_name}> tag")
    return issues


def find_likely_undefined_vars(code: str) -> list:
    """
    Very rough heuristic for JS/JSX/TS: flags identifiers used with dot-access
    (e.g. `toggle.emit(...)`) that never appear as a declared const/let/var,
    a function parameter, or a destructured prop in the snippet.
    This will miss real cases and flag some false positives - it's a
    lightweight smell-check for the demo, not a real linter/compiler.
    """
    issues = []
    # only run this heuristic on JS-family code
    if not re.search(r"\b(const|let|function|=>|import)\b", code):
        return issues

    declared = set()
    declared.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_]\w*)", code))
    declared.update(re.findall(r"\bfunction\s+\w+\s*\(([^)]*)\)", code) and [])
    # function/arrow params, including destructured object params like ({ a, b })
    for params in re.findall(r"\(([^()]*)\)\s*=>", code) + re.findall(r"function\s*\w*\s*\(([^()]*)\)", code):
        for name in re.findall(r"[A-Za-z_]\w*", params):
            declared.add(name)
    # destructured object patterns: const { a, b } = props
    for block in re.findall(r"\{([^{}]*)\}\s*=", code):
        for name in re.findall(r"[A-Za-z_]\w*", block):
            declared.add(name)

    known_globals = {"React", "console", "Math", "JSON", "Object", "Array",
                      "Error", "Promise", "window", "document", "String",
                      "Number", "Boolean", "this", "props", "useState",
                      "useEffect", "useCallback", "useMemo", "useRef",
                      "Map", "Set", "Date", "parseInt", "parseFloat",
                      "setTimeout", "setInterval", "Intl"}

    used_with_dot = set(re.findall(r"\b([A-Za-z_]\w*)\.\w+\s*\(", code))
    # ignore `this.x(...)` calls - those are class members, not free variables
    code_no_this_calls = re.sub(r"\bthis\.\w+\s*\(", "", code)
    used_with_dot = set(re.findall(r"\b([A-Za-z_]\w*)\.\w+\s*\(", code_no_this_calls))
    # anything assigned as this.<name> = ... counts as declared (class field)
    declared.update(re.findall(r"\bthis\.([A-Za-z_]\w*)\s*=", code))
    for name in used_with_dot:
        if name not in declared and name not in known_globals:
            issues.append(f"'{name}' is used but never defined/imported/destructured")
    return issues


def find_mismatched_jsx_tags(code: str) -> list:
    """
    Catches unclosed/mismatched JSX tags, e.g. <div>...</span> or a <div>
    that's opened but never closed. Common when the model 'restructures'
    a template and loses track of tag nesting.
    Skips self-closing tags (<input />, <br/>) and HTML void elements.
    """
    issues = []
    void_elements = {"input", "br", "img", "hr", "meta", "link"}
    stack = []
    # match opening <Tag ...>, closing </Tag>, and self-closing <Tag ... />
    for m in re.finditer(r"<(/?)([A-Za-z][\w.]*)([^>]*?)(/?)>", code):
        closing_slash, tag, attrs, self_close = m.groups()
        if tag.lower() in void_elements or self_close == "/":
            continue
        if closing_slash:
            if not stack:
                issues.append(f"Closing tag </{tag}> has no matching opening tag")
            elif stack[-1] != tag:
                issues.append(f"Tag mismatch: expected </{stack[-1]}> but found </{tag}>")
                stack.pop()
            else:
                stack.pop()
        else:
            stack.append(tag)
    for unclosed in stack:
        issues.append(f"<{unclosed}> tag is never closed")
    return issues


def find_missing_hook_imports(code: str) -> list:
    """
    Catches React hooks (useState, useEffect, etc.) used in the code but
    never brought in via `import ... from 'react'` - a common miss when
    the model converts a class component to hooks but forgets the import.
    """
    issues = []
    hooks_used = set(re.findall(r"\b(use[A-Z]\w*)\s*\(", code))
    if not hooks_used:
        return issues
    import_match = re.search(r"import\s+[^{}\n]*\{([^}]*)\}\s*from\s*['\"]react['\"]", code)
    imported = set()
    if import_match:
        imported = {n.strip() for n in import_match.group(1).split(",")}
    missing = hooks_used - imported
    for h in sorted(missing):
        issues.append(f"'{h}' is used but not imported from 'react'")
    return issues


def find_duplicate_object_keys(code: str) -> list:
    """
    Catches duplicate keys in the same object literal, e.g. { name: 'a', name: 'b' }
    - the first is silently overwritten, easy for a model to introduce
    when merging/restructuring fields.
    """
    issues = []
    for obj_match in re.finditer(r"\{([^{}]*)\}", code):
        body = obj_match.group(1)
        # only look at things that look like key: value pairs, not JSX/destructuring
        keys = re.findall(r"(?:^|,)\s*([A-Za-z_]\w*)\s*:", body)
        seen = set()
        dupes = set()
        for k in keys:
            if k in seen:
                dupes.add(k)
            seen.add(k)
        for d in dupes:
            issues.append(f"Duplicate key '{d}' in object literal")
    return issues


def is_js_family(lang: str) -> bool:
    t = (lang or "").lower()
    return any(k in t for k in ("javascript", "typescript", "react", "jsx", "tsx"))


def is_python_family(lang: str) -> bool:
    t = (lang or "").lower()
    return t in ("python", "py") or t.startswith("python")


def find_python_syntax_errors(code: str) -> list:
    """Real parse when the target is Python — cheap and local, no extra tools."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        loc = f" (line {e.lineno})" if e.lineno else ""
        return [f"Python syntax error{loc}: {e.msg}"]
    return []


def find_javascript_syntax_errors(code: str) -> list:
    """Use Node's parser when it is installed; skip silently otherwise."""
    node = shutil.which("node")
    if not node:
        return []

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8", delete=False) as source_file:
            source_file.write(code)
            source_path = source_file.name
        result = subprocess.run(
            [node, "--check", source_path],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    finally:
        if "source_path" in locals():
            try:
                os.unlink(source_path)
            except OSError:
                pass

    if result.returncode == 0:
        return []
    detail = (result.stderr or result.stdout).strip().splitlines()
    message = detail[-1] if detail else "Invalid JavaScript syntax"
    return [f"JavaScript syntax error: {message}"]


def basic_confidence_check(converted_code: str, target_lang: str = "") -> dict:
    """
    Heuristic confidence badge. JSX/React checks run only for JS-family
    targets. Python targets also get ast.parse.
    """
    issues = []

    if not converted_code.strip():
        issues.append("Output is empty")

    for open_c, close_c, name in [("{", "}", "curly braces"),
                                   ("(", ")", "parentheses"),
                                   ("[", "]", "square brackets")]:
        if converted_code.count(open_c) != converted_code.count(close_c):
            issues.append(f"Unbalanced {name}")

    js = is_js_family(target_lang) or not target_lang
    if js:
        issues.extend(find_duplicate_jsx_attributes(converted_code))
        issues.extend(find_likely_undefined_vars(converted_code))
        issues.extend(find_mismatched_jsx_tags(converted_code))
        issues.extend(find_missing_hook_imports(converted_code))
        issues.extend(find_duplicate_object_keys(converted_code))

    if is_python_family(target_lang):
        issues.extend(find_python_syntax_errors(converted_code))
    elif (target_lang or "").lower() == "javascript":
        issues.extend(find_javascript_syntax_errors(converted_code))

    migration_notes = converted_code.count("MIGRATION_NOTE")
    if migration_notes:
        issues.append(f"{migration_notes} section(s) flagged for manual review")

    if not issues:
        return {"status": "high_confidence", "issues": []}
    elif any(k in " ".join(issues) for k in ["Unbalanced", "empty", "Duplicate",
                                               "never defined", "mismatch",
                                               "never closed", "no matching",
                                               "not imported", "syntax error"]):
        return {"status": "low_confidence", "issues": issues}
    else:
        return {"status": "medium_confidence", "issues": issues}


@app.route("/convert", methods=["POST"])
def convert():
    data = request.get_json(silent=True) or {}
    source_lang = data.get("source_lang", "")
    target_lang = data.get("target_lang", "")
    code = data.get("code", "")

    if not code.strip():
        return jsonify({"status": "error", "message": "No code provided"}), 400

    prompt = PROMPT_TEMPLATE.format(
        source_lang=source_lang,
        target_lang=target_lang,
        code=code
    )

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2}
        }, timeout=120)
        response.raise_for_status()
        raw_output = response.json()["response"]
        converted_code = strip_markdown_fences(raw_output)
        confidence = basic_confidence_check(converted_code, target_lang)

        return jsonify({
            "status": "success",
            "converted_code": converted_code,
            "confidence": confidence
        })
    except requests.exceptions.Timeout:
        return jsonify({
            "status": "error",
            "message": "Ollama timed out after 120s. First load is slow; close other apps and retry.",
            "hint": f"ollama pull {MODEL_NAME}"
        }), 504
    except requests.exceptions.ConnectionError:
        return jsonify({
            "status": "error",
            "message": "Can't reach Ollama. Install it, then run: ollama serve",
            "hint": f"Then pull the model: ollama pull {MODEL_NAME}"
        }), 500
    except requests.exceptions.HTTPError as e:
        hint = f"ollama pull {MODEL_NAME}"
        return jsonify({
            "status": "error",
            "message": f"Ollama HTTP error: {e}. If the model is missing, run: {hint}",
            "hint": hint
        }), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "model": MODEL_NAME})


def _examples_manifest():
    path = os.path.join(EXAMPLES_DIR, "manifest.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.route("/examples", methods=["GET"])
def list_examples():
    items = []
    for row in _examples_manifest():
        items.append({k: row[k] for k in ("id", "label", "source_lang", "target_lang", "note")})
    return jsonify({"status": "ok", "examples": items})


@app.route("/examples/<example_id>", methods=["GET"])
def get_example(example_id):
    for row in _examples_manifest():
        if row["id"] == example_id:
            file_path = os.path.join(EXAMPLES_DIR, row["file"])
            with open(file_path, encoding="utf-8") as f:
                code = f.read()
            return jsonify({
                "status": "ok",
                "id": row["id"],
                "label": row["label"],
                "source_lang": row["source_lang"],
                "target_lang": row["target_lang"],
                "note": row.get("note", ""),
                "code": code
            })
    return jsonify({"status": "error", "message": f"Unknown example: {example_id}"}), 404


@app.route("/")
def index():
    return send_from_directory(ROOT_DIR, "index.html")


if __name__ == "__main__":
    # Collaborators: FLASK_DEBUG=1 python app.py  — leave off for demos.
    app.run(port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
