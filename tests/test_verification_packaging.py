from fnmatch import fnmatch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _dockerignore_ignores(path: str) -> bool:
    ignored = False
    normalized = path.lstrip("/")
    for raw in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        pattern = line[1:] if negated else line
        root_pattern = pattern.startswith("/")
        pattern = pattern.lstrip("/")
        matches = (
            normalized == pattern
            if root_pattern
            else fnmatch(normalized, pattern) or fnmatch(Path(normalized).name, pattern)
        )
        if matches:
            ignored = not negated
    return ignored


def test_verification_image_keeps_python_package_metadata_in_context() -> None:
    dockerfile = (ROOT / "Dockerfile.verification").read_text(encoding="utf-8")

    assert "COPY pyproject.toml README.md ./" in dockerfile
    assert not _dockerignore_ignores("pyproject.toml")
    assert not _dockerignore_ignores("README.md")


def test_verification_image_forces_headless_worker_browser_runtime() -> None:
    dockerfile = (ROOT / "Dockerfile.verification").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers" in dockerfile
    assert "HEADLESS=true" in dockerfile
    assert "DEPLOYMENT_MODE=worker" in dockerfile


def test_verification_image_still_excludes_markdown_bulk() -> None:
    assert _dockerignore_ignores("docs/README.md")
    assert _dockerignore_ignores("handoffs/2026-06-23-example.md")
