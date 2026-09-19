"""The deployed verification image must contain every advertised adapter."""
from pathlib import Path


def test_verification_image_installs_database_extra():
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / 'pyproject.toml').read_text())['project']
    extra = project['optional-dependencies']['verification']
    assert any(requirement.startswith('asyncpg>=') for requirement in extra)
    assert not any(requirement.startswith('asyncpg') for requirement in project['dependencies'])
    image = (root / 'Dockerfile.verification').read_text()
    assert 'wheel-dir /wheels .[verification]' in image
    assert '--find-links=/wheels flyto-core[verification]' in image
