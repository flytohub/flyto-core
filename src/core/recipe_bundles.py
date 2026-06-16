"""Recipe bundle planning for Cloud and MCP consumers.

This module deliberately avoids any database or Firebase dependency. It turns a
portable bundle manifest into an import plan that another service can persist.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


class RecipeBundleError(ValueError):
    """Raised when a recipe bundle cannot be safely planned."""


_TEMPLATE_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
_SCENARIO_METADATA_KEYS = {"scenario_id", "display_name", "runtime_required_args"}


def load_bundle_manifest(path: str | Path) -> dict[str, Any]:
    """Load a bundle manifest from YAML."""

    with Path(path).open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)
    if not isinstance(manifest, dict):
        raise RecipeBundleError("Recipe bundle manifest must be a mapping")
    return manifest


def build_recipe_bundle_plan(
    manifest: dict[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic folder and recipe-asset import plan."""

    _require_keys(manifest, ["bundle_id", "cloud_target", "recipes"])
    _validate_required_args(manifest, args)
    forbidden = _forbidden_fields(manifest)
    _assert_no_stored_secrets(manifest.get("recipes"), forbidden, path=("recipes",))

    cloud_target = manifest["cloud_target"]
    root_folder = _render(cloud_target.get("root_folder", "Warroom"), args)
    project_folder = _render_list(
        cloud_target.get("default_folder_path", [root_folder, "{{project_slug}}"]),
        args,
    )

    folders: list[dict[str, Any]] = [{"path": project_folder}]
    assets: list[dict[str, Any]] = []

    for recipe in manifest.get("recipes", []):
        if not isinstance(recipe, dict):
            raise RecipeBundleError("Recipe bundle recipes must be mappings")
        _require_keys(recipe, ["recipe_id", "source", "folder_path"])

        folder_path = _render_list(recipe["folder_path"], args)
        folders.append({"path": folder_path})
        for scenario in recipe.get("scenarios", []):
            if not isinstance(scenario, dict):
                raise RecipeBundleError("Recipe bundle scenarios must be mappings")
            _require_keys(scenario, ["scenario_id"])
            default_args = {
                key: _render(value, args)
                for key, value in scenario.items()
                if key not in _SCENARIO_METADATA_KEYS
            }
            runtime_required_args = scenario.get(
                "runtime_required_args",
                recipe.get("runtime_required_args", []),
            )
            _assert_no_stored_secrets(
                default_args,
                forbidden,
                path=("recipes", recipe["recipe_id"], "scenarios", scenario["scenario_id"]),
            )
            folders.append({"path": folder_path})
            assets.append(
                {
                    "recipe_id": recipe["recipe_id"],
                    "scenario_id": scenario["scenario_id"],
                    "display_name": scenario.get("display_name", scenario["scenario_id"]),
                    "source": recipe["source"],
                    "folder_path": folder_path,
                    "default_args": default_args,
                    "runtime_required_args": list(runtime_required_args),
                }
            )

    return {
        "bundle_id": manifest["bundle_id"],
        "display_name": manifest.get("display_name", manifest["bundle_id"]),
        "root_folder": root_folder,
        "project_folder": project_folder,
        "folders": _unique_folders(folders),
        "recipe_assets": assets,
        "security": manifest.get("security", {}),
        "export_contract": manifest.get("export_contract", {}),
    }


def _require_keys(value: dict[str, Any], keys: list[str]) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        raise RecipeBundleError(f"Recipe bundle is missing required keys: {', '.join(missing)}")


def _validate_required_args(manifest: dict[str, Any], args: dict[str, Any]) -> None:
    required = manifest.get("required_args", [])
    missing = [key for key in required if args.get(key) in (None, "")]
    if missing:
        raise RecipeBundleError(f"Recipe bundle args are missing: {', '.join(missing)}")


def _forbidden_fields(manifest: dict[str, Any]) -> set[str]:
    fields = manifest.get("security", {}).get("forbidden_stored_fields", [])
    if not isinstance(fields, list):
        raise RecipeBundleError("security.forbidden_stored_fields must be a list")
    return {str(field).lower().replace("-", "_") for field in fields}


def _assert_no_stored_secrets(
    value: Any,
    forbidden: set[str],
    path: tuple[str, ...],
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            next_path = (*path, key_text)
            if _is_forbidden_key(key_text, forbidden) and nested not in (None, "", [], {}):
                raise RecipeBundleError(
                    f"Recipe bundle stores a forbidden field at {'.'.join(next_path)}"
                )
            _assert_no_stored_secrets(nested, forbidden, next_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_stored_secrets(item, forbidden, (*path, str(index)))


def _is_forbidden_key(key: str, forbidden: set[str]) -> bool:
    normalized = key.lower().replace("-", "_")
    for field in forbidden:
        if field == "pat":
            if normalized in {"pat", "personal_access_token"}:
                return True
            continue
        if field and field in normalized:
            return True
    return False


def _render(value: Any, args: dict[str, Any]) -> Any:
    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in args:
                raise RecipeBundleError(f"Recipe bundle template arg is missing: {key}")
            return str(args[key])

        return _TEMPLATE_RE.sub(replace, value)
    if isinstance(value, list):
        return [_render(item, args) for item in value]
    if isinstance(value, dict):
        return {key: _render(nested, args) for key, nested in value.items()}
    return value


def _render_list(value: Any, args: dict[str, Any]) -> list[str]:
    rendered = _render(value, args)
    if not isinstance(rendered, list) or not all(isinstance(item, str) for item in rendered):
        raise RecipeBundleError("Recipe bundle folder paths must be string lists")
    return rendered


def _unique_folders(folders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, Any]] = []
    for folder in folders:
        path = tuple(folder["path"])
        if path in seen:
            continue
        seen.add(path)
        unique.append(folder)
    return unique
