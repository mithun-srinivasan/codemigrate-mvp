# Contributing to CodeMigrate

This MVP is small on purpose. Read `README.md` first, then pick a task from
**Open work for collaborators** there. Do not start Phase 2 (AST / Groq /
fine-tuning) unless the team agrees — keep PRs small. By contributing you
agree to license your work under the MIT License (`LICENSE`).

## Setup

```
ollama pull qwen2.5-coder:1.5b
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** (Flask serves `index.html`). Do not rely on
double-clicking the HTML file.

Default model is `qwen2.5-coder:1.5b`. Do not switch `MODEL_NAME` to 7b
unless the machine has 16GB+ RAM.

## Tests (no Ollama required)

```
pytest -q
```

These lock the confidence engine. If you change a detector, update or add a
test in `tests/test_confidence.py`. Conversion quality of the SLM is **not**
asserted in CI (too slow / non-deterministic).

## Where to change what

| You want to… | Touch |
|---|---|
| Add a demo snippet | File in `examples/` + row in `examples/manifest.json` |
| Add a bug detector | Function in `app.py`, call it from `basic_confidence_check`, test in `tests/test_confidence.py`, one row in the README table |
| Change the conversion prompt | `PROMPT_TEMPLATE` in `app.py` only |
| Change the UI | `index.html` (no frontend framework) |
| Change the model | `MODEL_NAME` in `app.py` (keep 1.5b as default) |

## Rules

- Keep the stack: Flask + one HTML file + local Ollama. No new paid APIs.
- Heuristics must be target-aware (JSX checks only for JS/React targets).
- Do not commit `.venv`, `__pycache__`, `.env`, or zip dumps.
- Match existing code style. No drive-by refactors.
