from pathlib import Path

import pytest

from core.recipe_bundles import (
    RecipeBundleError,
    build_recipe_bundle_plan,
    load_bundle_manifest,
)


def _bundle_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "recipe_bundles"
        / "flyto2-warroom-smoke.yaml"
    )


def test_build_recipe_bundle_plan_places_assets_under_project_folders():
    manifest = load_bundle_manifest(_bundle_path())

    plan = build_recipe_bundle_plan(
        manifest,
        {"project_slug": "acme", "base_url": "http://localhost:8443"},
    )

    assert plan["root_folder"] == "Warroom"
    assert plan["project_folder"] == ["Warroom", "acme"]
    assert {"path": ["Warroom", "acme", "UI Smoke"]} in plan["folders"]
    assert {"path": ["Warroom", "acme", "Authenticated UI Smoke"]} in plan["folders"]

    footprint = next(
        asset for asset in plan["recipe_assets"] if asset["scenario_id"] == "footprint"
    )
    assert footprint["recipe_id"] == "flyto2-ui-smoke"
    assert footprint["folder_path"] == ["Warroom", "acme", "UI Smoke"]
    assert footprint["default_args"]["path"] == "/footprint"

    authenticated = next(
        asset
        for asset in plan["recipe_assets"]
        if asset["scenario_id"] == "authenticated-pentest"
    )
    assert authenticated["default_args"]["page_url"] == "http://localhost:8443/pentest"


def test_build_recipe_bundle_plan_requires_declared_args():
    manifest = load_bundle_manifest(_bundle_path())

    with pytest.raises(RecipeBundleError, match="base_url"):
        build_recipe_bundle_plan(manifest, {"project_slug": "acme"})


def test_build_recipe_bundle_plan_rejects_stored_secret_fields():
    manifest = {
        "bundle_id": "unsafe",
        "cloud_target": {
            "root_folder": "Warroom",
            "default_folder_path": ["Warroom", "{{project_slug}}"],
        },
        "security": {"forbidden_stored_fields": ["password", "token", "pat"]},
        "required_args": ["project_slug"],
        "recipes": [
            {
                "recipe_id": "unsafe-login",
                "source": "../recipes/flyto2-ui-login-smoke.yaml",
                "folder_path": ["Warroom", "{{project_slug}}", "Unsafe"],
                "scenarios": [
                    {
                        "scenario_id": "stores-password",
                        "password": "do-not-store",
                    }
                ],
            }
        ],
    }

    with pytest.raises(RecipeBundleError, match="password"):
        build_recipe_bundle_plan(manifest, {"project_slug": "acme"})
