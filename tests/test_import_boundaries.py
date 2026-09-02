from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_IMPORT = re.compile(r"^\s*(?:from|import)\s+src\.core(?:\.|\s|$)", re.MULTILINE)
SECURITY_ENV_KEYS = {
    "FLYTO_ALLOW_PRIVATE_NETWORK",
    "FLYTO_HTTP_DISABLE_SSRF_GUARD",
    "FLYTO_RUNNER_SECRET",
    "FLYTO_VERIFICATION_API_KEY",
    "FLYTO_VERIFICATION_SECRET",
    "FLYTO_VSCODE_LOCAL_MODE",
}


def test_core_uses_one_canonical_package_identity():
    offenders = []
    for source_root in (ROOT / "src", ROOT / "tests"):
        for path in source_root.rglob("*.py"):
            if path == Path(__file__):
                continue
            if LEGACY_IMPORT.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], f"legacy src.core imports create duplicate module state: {offenders}"


def test_security_overrides_are_not_enabled_during_test_collection():
    """Security exceptions belong in fixtures so pytest always restores them."""
    offenders = []
    for path in (ROOT / "tests").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for statement in tree.body:
            targets = statement.targets if isinstance(statement, ast.Assign) else []
            for target in targets:
                if not isinstance(target, ast.Subscript):
                    continue
                owner = target.value
                if not (
                    isinstance(owner, ast.Attribute)
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "os"
                    and owner.attr == "environ"
                ):
                    continue
                if isinstance(target.slice, ast.Constant) and target.slice.value in SECURITY_ENV_KEYS:
                    offenders.append(f"{path.relative_to(ROOT)}:{statement.lineno}")

    assert offenders == [], f"collection-time security environment overrides: {offenders}"


#: Packages that are OPTIONAL extras, not base dependencies. A base install has
#: none of them, so nothing on the module-registry import path may name one at
#: module level.
_OPTIONAL_AT_IMPORT_TIME = {
    "playwright",
}

#: The packages whose own module level is allowed to name them: they ARE the
#: optional surface, and nothing imports them unless a caller asked for that
#: capability.
_MAY_IMPORT_OPTIONALS = {
    "src/core/browser",
    "src/core/modules/atomic/browser/_playwright",
}


def _module_level_imports(tree: ast.AST) -> set[str]:
    """Top-level import names only. A deferred import inside a function is the
    established way to reach an optional dependency and is not the subject."""
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_importing_the_module_registry_needs_no_optional_extra():
    """`import core.modules` must work in a base install.

    This is the failure the release pipeline caught and the whole test suite
    missed, because every local run has the extras installed. A module-level
    `from ....browser.driver import BrowserWaitTimeout` in `browser/wait.py`
    reached `core/browser/__init__.py`, which imports the driver, which imports
    playwright — so the built wheel could not import its own registry:

        core/modules/atomic/browser/wait.py -> core/browser/__init__.py
        -> core/browser/driver.py
        -> ModuleNotFoundError: No module named 'playwright'

    Every module under `core/modules/` is imported by `register_all`, so one
    module-level import of an optional package breaks the base install for all
    483 of them.

    IT RUNS THE IMPORT RATHER THAN READING THE IMPORTS, and the first draft of
    this test is why. That draft scanned each file for a module-level
    `playwright` and passed with the bad import restored — because `wait.py`
    named `core.browser.driver`, a FIRST-PARTY module, and the optional
    dependency was two hops further on. A static check has to model transitive
    reach to see that; a subprocess with the package blocked simply cannot miss
    it, whatever route is taken.
    """
    blocker = textwrap.dedent(
        """
        import sys

        class _Blocked:
            def find_module(self, name, path=None):
                return self.find_spec(name, path)

            def find_spec(self, name, path=None, target=None):
                root = name.split(".")[0]
                if root in %(blocked)r:
                    raise ModuleNotFoundError("No module named %%r" %% root, name=root)
                return None

        sys.meta_path.insert(0, _Blocked())
        import core.modules  # noqa: F401
        print("OK")
        """
        % {"blocked": sorted(_OPTIONAL_AT_IMPORT_TIME)}
    )

    completed = subprocess.run(
        [sys.executable, "-c", blocker],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )

    assert completed.returncode == 0, (
        "importing the module registry reached an optional extra:\n"
        + completed.stderr[-2000:]
    )
    assert "OK" in completed.stdout


def test_the_browser_wait_timeout_type_stays_reachable_without_playwright():
    """The specific rehoming, pinned so it is not quietly undone.

    `BrowserWaitTimeout` has to be nameable by a module that must import in a
    base install AND by the driver that raises it. It therefore lives in
    `engine/exceptions.py`, which imports nothing outside the standard library.
    Moving it back beside the driver reintroduces the wheel failure above.
    """
    source = (ROOT / "src" / "core" / "engine" / "exceptions.py").read_text(
        encoding="utf-8"
    )
    assert "class BrowserWaitTimeout(RuntimeError):" in source

    named = _module_level_imports(ast.parse(source))
    third_party = named - {
        "__future__", "typing", "dataclasses", "enum", "abc", "types",
    }
    assert not (third_party & _OPTIONAL_AT_IMPORT_TIME), (
        f"engine/exceptions.py must stay importable everywhere: {sorted(third_party)}"
    )
