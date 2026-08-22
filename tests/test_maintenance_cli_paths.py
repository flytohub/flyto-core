"""Focused tests for maintenance CLI filesystem boundaries."""

import json
import sys
from pathlib import Path

import pytest

from scripts import export_i18n_baseline, lint_modules, migrate_module


def _module_info(action: str = "chat") -> migrate_module.ModuleInfo:
    return migrate_module.ModuleInfo(
        module_id=f"llm.{action}",
        category="llm",
        action=action,
        class_name="Chat",
        file_path="chat.py",
        label="Chat",
        description="Chat safely",
        params_schema={},
        output_schema={},
        permissions=[],
        icon="MessageSquare",
        color="#000000",
        cost_class="standard",
        cost_points=1,
    )


def test_export_cli_canonicalizes_relative_symlink_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "external"
    destination.mkdir()
    link = tmp_path / "output-link"
    link.symlink_to(destination, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        export_i18n_baseline,
        "load_all_modules",
        lambda: {"llm.chat": {"label": "Chat", "description": "Chat"}},
    )
    monkeypatch.setattr(
        sys, "argv", ["export_i18n_baseline.py", "--output-dir", "output-link"]
    )

    export_i18n_baseline.main()

    output = destination / "modules.llm.json"
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["llm.chat"]["label"] == "llm.chat"


def test_lint_cli_passes_canonical_external_path_to_write_sink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "external"
    destination.mkdir()
    link = tmp_path / "baseline-link"
    link.symlink_to(destination, target_is_directory=True)
    captured = []
    results = {
        "modules": [],
        "import_failures": [],
        "summary": {"is_valid": True},
    }
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lint_modules, "load_all_modules", lambda: ({"one": {}}, []))
    monkeypatch.setattr(lint_modules, "validate_modules", lambda *args, **kwargs: results)
    monkeypatch.setattr(
        lint_modules, "save_baseline", lambda path, data: captured.append(path)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["lint_modules.py", "--baseline-create", "baseline-link/current.json"],
    )

    with pytest.raises(SystemExit) as exit_info:
        lint_modules.main()

    assert exit_info.value.code == 0
    assert captured == [destination / "current.json"]
    assert captured[0].is_absolute()


@pytest.mark.parametrize(
    "value",
    ["", ".", "..", "/absolute", "../escape", "nested/name", "nested\\name", "bad name"],
)
def test_migration_rejects_unsafe_category_before_discovery(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", tmp_path / "plugins")
    discovered = []
    monkeypatch.setattr(migrator, "discover_modules", lambda category: discovered.append(category))

    with pytest.raises(ValueError, match="single safe segment"):
        migrator.migrate_category(value)

    assert discovered == []


@pytest.mark.parametrize(
    "module_id",
    ["llm", "llm.", ".chat", "llm...chat", "../llm.chat", "llm../chat", "llm.bad name"],
)
def test_migration_rejects_unsafe_module_id_before_discovery(
    module_id: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", tmp_path / "plugins")
    discovered = []
    monkeypatch.setattr(migrator, "discover_modules", lambda category: discovered.append(category))

    with pytest.raises(ValueError):
        migrator.migrate_category("llm", [module_id])

    assert discovered == []


def test_migration_uses_canonical_roots_and_keeps_valid_module_ids(
    tmp_path: Path,
) -> None:
    source = tmp_path / "external-source"
    category_dir = source / "core" / "modules" / "atomic" / "llm"
    category_dir.mkdir(parents=True)
    (category_dir / "chat.py").write_text(
        "class Chat:\n"
        "    module_name = 'Chat'\n"
        "    module_description = 'Chat safely'\n"
        "    def execute(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    plugins = tmp_path / "external-plugins"
    plugins.mkdir()
    source_link = tmp_path / "source-link"
    plugins_link = tmp_path / "plugins-link"
    source_link.symlink_to(source, target_is_directory=True)
    plugins_link.symlink_to(plugins, target_is_directory=True)

    migrator = migrate_module.ModuleMigrator(source_link, plugins_link)
    result = migrator.migrate_category("llm", ["llm.chat"])

    expected = plugins / "flyto-official_llm"
    assert migrator.src_path == source
    assert migrator.plugins_path == plugins
    assert result == expected
    assert (expected / "plugin.manifest.json").is_file()
    assert (expected / "steps" / "chat.py").is_file()


def test_traversal_cannot_create_plugin_outside_canonical_root(tmp_path: Path) -> None:
    plugins = tmp_path / "plugins"
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", plugins)
    outside = tmp_path / "flyto-official_escape"

    with pytest.raises(ValueError):
        migrator.migrate_category("../escape")

    assert not outside.exists()
    assert not plugins.exists()


def test_migration_rejects_plugin_directory_symlink_outside_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (plugins / "flyto-official_llm").symlink_to(outside, target_is_directory=True)
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", plugins)
    monkeypatch.setattr(migrator, "discover_modules", lambda _category: [_module_info()])

    with pytest.raises(ValueError, match="escapes the selected plugins root"):
        migrator.migrate_category("llm")

    assert list(outside.iterdir()) == []


def test_migration_rejects_steps_symlink_outside_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "plugins"
    plugin_dir = plugins / "flyto-official_llm"
    plugin_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (plugin_dir / "steps").symlink_to(outside, target_is_directory=True)
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", plugins)
    monkeypatch.setattr(migrator, "discover_modules", lambda _category: [_module_info()])

    with pytest.raises(ValueError, match="escapes the selected plugins root"):
        migrator.migrate_category("llm")

    assert list(outside.iterdir()) == []
    assert sorted(path.name for path in plugin_dir.iterdir()) == ["steps"]


def test_migration_rejects_output_file_symlink_outside_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "plugins"
    plugin_dir = plugins / "flyto-official_llm"
    (plugin_dir / "steps").mkdir(parents=True)
    outside = tmp_path / "outside.py"
    outside.write_text("unchanged", encoding="utf-8")
    (plugin_dir / "main.py").symlink_to(outside)
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", plugins)
    monkeypatch.setattr(migrator, "discover_modules", lambda _category: [_module_info()])

    with pytest.raises(ValueError, match="escapes the selected plugins root"):
        migrator.migrate_category("llm")

    assert outside.read_text(encoding="utf-8") == "unchanged"
    assert sorted(path.name for path in plugin_dir.iterdir()) == ["main.py", "steps"]


def test_migration_rejects_unsafe_discovered_action_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "plugins"
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", plugins)
    monkeypatch.setattr(
        migrator, "discover_modules", lambda _category: [_module_info("../outside")]
    )

    with pytest.raises(ValueError, match="action must be a single safe segment"):
        migrator.migrate_category("llm")

    assert not plugins.exists()
    assert not (tmp_path / "outside.py").exists()


def test_migration_preflights_late_requirements_escape_before_any_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugins = tmp_path / "plugins"
    plugin_dir = plugins / "flyto-official_llm"
    steps_dir = plugin_dir / "steps"
    steps_dir.mkdir(parents=True)
    outside = tmp_path / "outside-requirements.txt"
    outside.write_text("unchanged", encoding="utf-8")
    (plugin_dir / "requirements.txt").symlink_to(outside)
    migrator = migrate_module.ModuleMigrator(tmp_path / "src", plugins)
    monkeypatch.setattr(migrator, "discover_modules", lambda _category: [_module_info()])

    with pytest.raises(ValueError, match="escapes the selected plugins root"):
        migrator.migrate_category("llm")

    assert outside.read_text(encoding="utf-8") == "unchanged"
    assert not (plugin_dir / "plugin.manifest.json").exists()
    assert not (plugin_dir / "main.py").exists()
    assert not (steps_dir / "chat.py").exists()
    assert not (steps_dir / "__init__.py").exists()
