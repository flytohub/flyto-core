"""Public runtime versions must follow package metadata."""

from importlib.metadata import version


def test_core_and_cli_versions_match_installed_package():
    import cli
    import core

    package_version = version("flyto-core")
    assert core.__version__ == package_version
    assert cli.__version__ == package_version
