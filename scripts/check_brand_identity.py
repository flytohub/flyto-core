#!/usr/bin/env python3
"""Enforce Flyto2 public naming and email-domain policy."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVED_EMAILS = {
    f"{local}@flyto2.com"
    for local in (
        "admin",
        "alerts",
        "conduct",
        "dev",
        "dmarc",
        "hello",
        "info",
        "noreply",
        "oncall",
        "pentest",
        "privacy",
        "reports",
        "sales",
        "security",
        "support",
        "team",
    )
}
EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
BARE_PRODUCT = re.compile(r"(?<![-\w])Flyto(?!2|[-\w])")
TEXT_SUFFIXES = {".md", ".py", ".toml", ".json", ".yaml", ".yml", ".txt"}
TEXT_FILENAMES = {"Dockerfile", "Dockerfile.verification", "LICENSE", "NOTICE"}


def repository_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def main() -> int:
    violations = []
    checked = 0
    for relative in repository_files():
        path = ROOT / relative
        if not path.is_file() or (
            path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_FILENAMES
        ):
            continue
        if relative == "scripts/check_brand_identity.py":
            continue
        if relative.startswith(("audit_report/", "docs/reference/", "tests/")):
            continue
        checked += 1
        content = path.read_text(encoding="utf-8", errors="ignore")
        lowered = content.lower()
        for domain in ("flyto.ai", "flyto.com", "flyto.io"):
            if domain in lowered:
                violations.append(f"{relative}: forbidden public domain {domain}")
        for line_number, line in enumerate(content.splitlines(), start=1):
            if path.suffix.lower() == ".md" and BARE_PRODUCT.search(line):
                violations.append(f"{relative}:{line_number}: bare Flyto product name")
            for email in EMAIL.findall(line):
                normalized = email.lower()
                if normalized.endswith("@flyto2.com") and normalized not in APPROVED_EMAILS:
                    violations.append(
                        f"{relative}:{line_number}: unregistered public mailbox {email}"
                    )
                elif not normalized.endswith("@flyto2.com"):
                    violations.append(
                        f"{relative}:{line_number}: non-flyto2.com public mailbox {email}"
                    )
    if violations:
        raise RuntimeError("brand identity violations:\n" + "\n".join(violations))
    print(
        f"brand identity passed: {checked} files, Flyto2 naming, "
        "@flyto2.com public email policy"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
