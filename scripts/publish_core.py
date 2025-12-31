#!/usr/bin/env python3
"""
Flyto Core Publishing Script
Builds and publishes flyto-core to PyPI

Usage:
    python scripts/publish_core.py          # Build only (dry run)
    python scripts/publish_core.py --test   # Publish to TestPyPI
    python scripts/publish_core.py --prod   # Publish to PyPI (production)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory"""
    return Path(__file__).parent.parent


def get_version() -> str:
    """Read current version from pyproject.toml"""
    pyproject = get_project_root() / "pyproject.toml"
    content = pyproject.read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', content)
    if match:
        return match.group(1)
    raise ValueError("Could not find version in pyproject.toml")


def bump_version(version: str, bump_type: str = "patch") -> str:
    """Bump version number"""
    parts = version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:  # patch
        patch += 1

    return f"{major}.{minor}.{patch}"


def update_version(new_version: str) -> None:
    """Update version in pyproject.toml"""
    pyproject = get_project_root() / "pyproject.toml"
    content = pyproject.read_text()
    content = re.sub(
        r'version\s*=\s*"[^"]+"',
        f'version = "{new_version}"',
        content
    )
    pyproject.write_text(content)
    print(f"Updated version to {new_version}")


def clean_build() -> None:
    """Clean build artifacts"""
    root = get_project_root()
    dirs_to_clean = ["dist", "build", "*.egg-info"]

    for pattern in dirs_to_clean:
        for path in root.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
                print(f"Removed {path}")


def run_tests() -> bool:
    """Run tests before publishing"""
    print("\n=== Running Tests ===")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=get_project_root()
    )
    return result.returncode == 0


def validate_modules() -> bool:
    """Validate all modules can be imported"""
    print("\n=== Validating Modules ===")
    result = subprocess.run(
        [sys.executable, "scripts/validate_all_modules.py"],
        cwd=get_project_root()
    )
    return result.returncode == 0


def build_package() -> bool:
    """Build the package"""
    print("\n=== Building Package ===")
    clean_build()

    result = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=get_project_root()
    )

    if result.returncode == 0:
        dist_dir = get_project_root() / "dist"
        print(f"\nBuild artifacts:")
        for f in dist_dir.iterdir():
            print(f"  - {f.name} ({f.stat().st_size / 1024:.1f} KB)")

    return result.returncode == 0


def publish_to_pypi(test: bool = False) -> bool:
    """Publish to PyPI or TestPyPI"""
    print(f"\n=== Publishing to {'TestPyPI' if test else 'PyPI'} ===")

    cmd = [sys.executable, "-m", "twine", "upload"]

    if test:
        cmd.extend(["--repository", "testpypi"])

    cmd.append("dist/*")

    result = subprocess.run(cmd, cwd=get_project_root())
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Publish flyto-core to PyPI")
    parser.add_argument("--test", action="store_true", help="Publish to TestPyPI")
    parser.add_argument("--prod", action="store_true", help="Publish to PyPI")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], help="Bump version before publishing")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    parser.add_argument("--skip-validate", action="store_true", help="Skip module validation")
    args = parser.parse_args()

    os.chdir(get_project_root())

    # Get current version
    current_version = get_version()
    print(f"Current version: {current_version}")

    # Bump version if requested
    if args.bump:
        new_version = bump_version(current_version, args.bump)
        update_version(new_version)
        current_version = new_version

    # Run validation
    if not args.skip_validate:
        if not validate_modules():
            print("\n❌ Module validation failed!")
            return 1

    # Run tests
    if not args.skip_tests:
        if not run_tests():
            print("\n❌ Tests failed!")
            return 1

    # Build package
    if not build_package():
        print("\n❌ Build failed!")
        return 1

    # Publish if requested
    if args.test or args.prod:
        if not publish_to_pypi(test=args.test):
            print("\n❌ Publishing failed!")
            return 1
        print(f"\n✅ Successfully published flyto-core {current_version}!")
    else:
        print(f"\n✅ Build successful! (dry run - use --test or --prod to publish)")
        print(f"   Version: {current_version}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
