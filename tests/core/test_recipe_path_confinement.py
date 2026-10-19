"""A recipe name reaches the file system only through its confinement (GHSA-mxcc).

``run_recipe`` is an MCP tool, so the name is caller-controlled. The one
function that turns a name into a path, ``confined_recipe_path``, keeps it
inside the bundled recipes directory; it is also what the indexer's taint
rules know as the path-traversal sanitizer (``.flyto-rules.yaml``).
"""

from __future__ import annotations

import pytest

from cli.recipe import RECIPES_DIR, confined_recipe_path, load_recipe


@pytest.mark.parametrize("name", ["../secrets", "../../etc/passwd", "/etc/passwd", "a/../../b"])
def test_a_name_that_leaves_the_recipes_directory_has_no_path(name):
    assert confined_recipe_path(name) is None
    assert load_recipe(name) is None


def test_a_bundled_recipe_name_resolves_inside_the_directory():
    bundled = next(RECIPES_DIR.glob("*.yaml"), None)
    if bundled is None:
        pytest.skip("no bundled recipe in this checkout")
    path = confined_recipe_path(bundled.stem)
    assert path is not None and RECIPES_DIR.resolve() in path.parents
