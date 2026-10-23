"""The pack feature x flyto-core version matrix is generated from ``compatibility.FEATURES``, never written by hand.

``docs/reference/pack-compatibility-matrix.json`` (machine-readable) and
``.md`` are outputs of ``scripts/generate_reference.py``; this test fails
when either is stale. Certified packs enter the matrix only from
certification records that verify against a certifier key.
"""

import importlib.util
import json

import pytest
from devkit_helpers import ROOT, cli

from core.pack.compatibility import (
    FEATURES,
    MATRIX_SCHEMA,
    compatibility_matrix,
    render_matrix_markdown,
    version_key,
)

JSON_PATH = ROOT / "docs" / "reference" / "pack-compatibility-matrix.json"
MD_PATH = ROOT / "docs" / "reference" / "pack-compatibility-matrix.md"


def generator():
    spec = importlib.util.spec_from_file_location("generate_reference", ROOT / "scripts" / "generate_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_feature_is_a_row_and_every_release_a_column():
    matrix = compatibility_matrix()
    assert matrix["schema"] == MATRIX_SCHEMA
    assert [row["feature"] for row in matrix["features"]] == [feature.feature_id for feature in FEATURES]
    versions = matrix["core_versions"]
    assert versions == sorted({feature.since for feature in FEATURES}, key=version_key)
    for feature, row in zip(FEATURES, matrix["features"], strict=True):
        for version in versions:
            assert row["accepted"][version] is (version_key(version) >= version_key(feature.since))
    assert matrix["certified"] == []


def test_the_committed_matrix_is_the_generated_one():
    outputs = generator().outputs()
    for path in (JSON_PATH, MD_PATH):
        assert path in outputs, f"generate_reference.py does not write {path.name}"
        assert path.read_text(encoding="utf-8") == outputs[path], \
            f"{path.name} is stale: run scripts/generate_reference.py"
    assert json.loads(JSON_PATH.read_text(encoding="utf-8")) == compatibility_matrix()


def test_the_markdown_renders_the_same_matrix():
    text = render_matrix_markdown(compatibility_matrix())
    for feature in FEATURES:
        assert f"`{feature.feature_id}`" in text


def test_the_spec_page_points_at_the_generated_matrix():
    spec = (ROOT / "docs" / "specs" / "ADAPTER_COMPATIBILITY_MATRIX.md").read_text(encoding="utf-8")
    assert "../reference/pack-compatibility-matrix.md" in spec
    assert "../reference/pack-compatibility-matrix.json" in spec


@pytest.mark.parametrize("as_json", [True, False])
def test_flyto_pack_matrix_prints_it(capsys, as_json):
    assert cli("matrix", *(["--json"] if as_json else [])) == 0
    out = capsys.readouterr().out
    if as_json:
        assert json.loads(out) == compatibility_matrix()
    else:
        assert "pack.standalone" in out
