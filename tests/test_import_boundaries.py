from __future__ import annotations

import ast
import re
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
