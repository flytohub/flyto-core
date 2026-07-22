"""Regression tests for source-backed documentation generators."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    path = ROOT / "scripts" / "generate_reference.py"
    spec = importlib.util.spec_from_file_location("generate_reference", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section(document: str, heading: str) -> str:
    start = document.index(f"## `{heading}`")
    next_heading = document.find("\n## `", start + 1)
    return document[start:] if next_heading == -1 else document[start:next_heading]


def test_reused_template_parser_variable_keeps_argument_ownership():
    reference = _load_generator().cli_reference()

    export = _section(reference, "flyto template export")
    history = _section(reference, "flyto template history")

    assert "`template_id`" in export
    assert "| `template_id` | yes |" in export
    assert "`-o, --output`" in export
    assert "`file`" not in export
    assert "`template_id`" in history
    assert "| `template_id` | yes |" in history
    assert "`--limit`" in history
    assert "`-o, --output`" not in history


def test_recipe_reference_covers_every_packaged_recipe():
    reference = _load_generator().recipe_reference()
    recipe_names = sorted(path.stem for path in (ROOT / "src" / "recipes").glob("*.yaml"))

    assert f"**{len(recipe_names)} executable recipes**" in reference
    for name in recipe_names:
        assert f"| `{name}` |" in reference


def test_http_reference_detects_signature_dependencies():
    reference = _load_generator().http_reference()

    run_row = next(line for line in reference.splitlines() if "| `/run` |" in line)
    assert "| internal key |" in run_row
