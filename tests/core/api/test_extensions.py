# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""
Tests for generic Core extension management (/v1/extensions + PluginLoader).

Nothing in this suite touches the network or the real package manager: every
pip invocation is intercepted at ``subprocess.run`` and every entry-point read
is served from a fake group. What is pinned here is the behaviour a real
install cannot be trusted to demonstrate on demand — a hostile version string,
a package that installs but is not an extension, an upgrade of code already
imported into this interpreter.

The properties under test:

  * only ``flyto-modules-*`` and ``flyto-plugin-*`` are managed, and both are
    managed by the same code path — ``flyto-modules-robotics`` works with no
    line of Core naming it;
  * pip is always invoked as an argv list with a scrubbed environment;
  * failures return a stable ``code``, and never package-manager stderr;
  * entry-point proof gates success, and a *new* install that fails proof is
    rolled back while an *upgrade* that fails proof is not;
  * an upgrade reports ``restart_required``;
  * install/uninstall refresh the loader's manifests and the module registry,
    and a refresh that fails is reported as ``refresh_failed`` plus
    ``restart_required`` rather than swallowed into an unqualified success;
  * the two mutating operations hold the loader lock for the whole pip run —
    proved from a second real thread, because the lock is reentrant and a
    same-thread probe would re-acquire it rather than block — and records are
    keyed *and named* by the PEP 503 normalised name, so one id identifies a
    package across install, listing and uninstall;
  * the routes hand the blocking loader to a worker thread instead of the
    event loop;
  * every route requires auth, and the mutating routes require an operator
    opt-in on top of it.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from starlette.testclient import TestClient

from core.api.routes import extensions as ext_routes
from core.api.server import create_app
from core.plugin import loader as loader_mod
from core.plugin.loader import (
    EXTENSION_KINDS,
    MODULES_KIND,
    PLUGINS_KIND,
    ExtensionErrorCode,
    PluginLoader,
    classify_extension,
    normalize_extension_name,
)

MODULE_PACK = "flyto-modules-robotics"
PLUGIN_PACK = "flyto-plugin-slack"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEntryPoint:
    """Minimal stand-in for importlib.metadata.EntryPoint."""

    def __init__(self, name, value, dist_name):
        self.name = name
        self.value = value
        self.dist = FakeDist(dist_name)


class FakeDist:
    def __init__(self, name):
        self.metadata = {"Name": name}


class FakePip:
    """Records every argv/env pair and replays a scripted sequence of results."""

    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": list(cmd), "kwargs": kwargs})
        outcome = self.results.pop(0) if self.results else {"returncode": 0}
        if outcome.get("timeout"):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))
        return subprocess.CompletedProcess(
            cmd,
            outcome.get("returncode", 0),
            outcome.get("stdout", ""),
            outcome.get("stderr", ""),
        )

    @property
    def subcommands(self):
        # cmd is [python, -m, pip, <subcommand>, ...]
        return [c["cmd"][3] for c in self.calls]


@pytest.fixture
def loader(tmp_path):
    """A loader with an isolated state dir and no discovery side effects."""
    inst = PluginLoader(plugins_dir=tmp_path / "plugins")
    with patch.object(PluginLoader, "discover_plugins", return_value={}):
        yield inst


@pytest.fixture
def fake_pip():
    pip = FakePip()
    with patch.object(loader_mod.subprocess, "run", pip):
        yield pip


@pytest.fixture
def registry_refresh():
    with patch("core.modules.registry.ModuleRegistry.refresh") as refresh:
        yield refresh


def with_entry_points(eps):
    """Patch the loader's entry-point reader to return ``eps`` for any group."""
    return patch.object(loader_mod, "_iter_entry_points", lambda group: list(eps))


def module_pack_eps(dist_name=MODULE_PACK):
    return [FakeEntryPoint("robotics", "flyto_modules_robotics.register:register_all", dist_name)]


class FakeMetadataDist:
    """Stand-in for importlib.metadata.Distribution with dict-ish metadata."""

    def __init__(self, name, version="1.0.0"):
        self._data = {
            "Name": name,
            "Version": version,
            "Summary": f"{name} summary",
            "Author": "",
            "License": "",
        }
        self.files = []

    @property
    def metadata(self):
        return self

    def get(self, key, default=None):
        return self._data.get(key, default)

    def get_all(self, key):
        return []


def acquire_from_another_thread(lock, timeout=0.25):
    """True if a thread *other than this one* can take ``lock`` within ``timeout``.

    The loader lock is reentrant, so ``lock.acquire(blocking=False)`` on the
    thread that already holds it succeeds and proves nothing. Every assertion
    about the lock being held — or released — has to come from a second thread.
    """
    got = []

    def attempt():
        acquired = lock.acquire(timeout=timeout)
        got.append(acquired)
        if acquired:
            lock.release()

    probe = threading.Thread(target=attempt)
    probe.start()
    probe.join(timeout + 5)
    assert not probe.is_alive(), "lock probe thread never finished"
    return got == [True]


# ---------------------------------------------------------------------------
# Kind classification — the whole supported surface, and nothing else
# ---------------------------------------------------------------------------


class TestExtensionKinds:

    def test_only_two_kinds_are_supported(self):
        assert {k.kind for k in EXTENSION_KINDS} == {"modules", "plugins"}
        assert MODULES_KIND.entry_point_group == "flyto.modules"
        assert PLUGINS_KIND.entry_point_group == "flyto.plugins"

    @pytest.mark.parametrize("name,kind", [
        (MODULE_PACK, "modules"),
        ("flyto-modules-vision", "modules"),
        (PLUGIN_PACK, "plugins"),
        ("flyto-plugin-anything", "plugins"),
    ])
    def test_supported_names_classify(self, name, kind):
        assert classify_extension(name).kind == kind

    @pytest.mark.parametrize("name", [
        "flyto-core",
        "requests",
        "robotics",                 # bare name is ambiguous, never guessed
        "flyto-modules-",           # prefix with no project part
        "flyto-plugin-",
        "notflyto-modules-x",
        "",
    ])
    def test_unsupported_names_are_refused(self, name):
        assert classify_extension(name) is None

    def test_classification_uses_pep503_normalisation(self):
        # pip treats these as one project; a gate that disagreed would have a
        # bypass rather than a gate.
        assert classify_extension("Flyto_Modules_Robotics").kind == "modules"
        assert normalize_extension_name("Flyto__Modules.Robotics") == "flyto-modules-robotics"

    @pytest.mark.parametrize("project", [
        "robotics",                 # the pack this work was motivated by
        "vision",
        "not-published-yet",
        "z",
    ])
    def test_any_module_pack_is_handled_identically(self, project, tmp_path,
                                                    fake_pip, registry_refresh):
        """No extension is special-cased: Core has never heard of any of these.

        Robotics is in the list only to prove it takes the same path as a name
        invented in this test. If any branch in Core named a pack, the invented
        names would behave differently from the real one — and they do not.
        """
        name = f"{MODULES_KIND.prefix}{project}"
        eps = [FakeEntryPoint(project, f"pack_{project.replace('-', '_')}:register_all", name)]
        inst = PluginLoader(plugins_dir=tmp_path / "plugins")

        with patch.object(PluginLoader, "discover_plugins", return_value={}), \
                patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(eps):
            result = inst.install_extension(name)

        assert result.ok is True
        assert result.kind == MODULES_KIND.kind
        assert result.entry_points == [project]
        assert name in fake_pip.calls[0]["cmd"]


# ---------------------------------------------------------------------------
# Argv / environment safety
# ---------------------------------------------------------------------------


class TestSafeInvocation:

    def test_pip_is_invoked_as_argv_without_a_shell(self, loader, fake_pip, registry_refresh):
        with with_entry_points(module_pack_eps()):
            loader.install_extension(MODULE_PACK, version="1.2.3")

        call = fake_pip.calls[0]
        assert call["cmd"][:4] == [sys.executable, "-m", "pip", "install"]
        assert f"{MODULE_PACK}==1.2.3" in call["cmd"]
        assert "--no-input" in call["cmd"]
        assert "--disable-pip-version-check" in call["cmd"]
        # No shell: nothing in the vector can be word-split or redirected.
        assert call["kwargs"].get("shell", False) is False
        assert all(isinstance(part, str) for part in call["cmd"])

    def test_environment_is_scrubbed(self, loader, fake_pip, registry_refresh, monkeypatch):
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-leak")
        monkeypatch.setenv("PIP_INDEX_URL", "https://mirror.example/simple")
        monkeypatch.delenv("FLYTO_SANDBOX_INHERIT_ENV", raising=False)

        with with_entry_points(module_pack_eps()):
            loader.install_extension(MODULE_PACK)

        env = fake_pip.calls[0]["kwargs"]["env"]
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert env.get("PIP_INDEX_URL") == "https://mirror.example/simple"

    def test_install_is_bounded_by_a_timeout(self, loader, fake_pip, registry_refresh):
        with with_entry_points(module_pack_eps()):
            loader.install_extension(MODULE_PACK)
        assert fake_pip.calls[0]["kwargs"]["timeout"] == PluginLoader.INSTALL_TIMEOUT

    @pytest.mark.parametrize("version", [
        "1.0; rm -rf /",
        "1.0 --extra-index-url=http://evil.example",
        "$(whoami)",
        "../../etc/passwd",
    ])
    def test_hostile_version_never_reaches_pip(self, loader, fake_pip, version):
        result = loader.install_extension(MODULE_PACK, version=version)
        assert result.ok is False
        assert result.code == ExtensionErrorCode.INVALID_VERSION
        assert fake_pip.calls == []

    def test_unsupported_name_never_reaches_pip(self, loader, fake_pip):
        result = loader.install_extension("requests")
        assert result.code == ExtensionErrorCode.UNSUPPORTED_EXTENSION
        assert fake_pip.calls == []


# ---------------------------------------------------------------------------
# Entry-point proof, rollback, restart_required
# ---------------------------------------------------------------------------


class TestInstallContract:

    def test_module_pack_installs_generically(self, loader, fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()):
            result = loader.install_extension(MODULE_PACK)

        assert result.ok is True
        assert result.kind == "modules"
        assert result.version == "1.0.0"
        assert result.entry_points == ["robotics"]
        # A first install has nothing already imported.
        assert result.restart_required is False
        assert result.rolled_back is False

    def test_install_refreshes_manifests_and_registry(self, tmp_path, fake_pip, registry_refresh):
        inst = PluginLoader(plugins_dir=tmp_path / "plugins")
        with patch.object(PluginLoader, "discover_plugins", return_value={}) as discover, \
                patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()):
            result = inst.install_extension(MODULE_PACK)

        assert result.ok is True
        assert result.refresh_failed is False
        discover.assert_called_with(force=True)
        registry_refresh.assert_called_once()

        # A refresh that raises must not turn a completed install into a
        # reported failure — the package is on disk either way. It must not be
        # silent either: this process cannot see what it just installed, and an
        # unqualified success sends the operator hunting for a module that is
        # present but unreachable.
        registry_refresh.side_effect = RuntimeError("registry rebuild failed")
        with patch.object(PluginLoader, "discover_plugins", return_value={}), \
                patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()):
            degraded = inst.install_extension(MODULE_PACK)

        assert degraded.ok is True
        assert degraded.refresh_failed is True
        assert degraded.restart_required is True
        assert "restart" in degraded.message.lower()

    def test_manifest_rescan_failure_is_degraded_not_raised(self, tmp_path, fake_pip,
                                                            registry_refresh):
        """A manifest rescan that raises must not lose the caller its result.

        By the time the refresh runs, pip has already changed the environment.
        An exception escaping here would abandon a completed install
        half-reported — a 500 for a package that is on disk, with no
        ``restart_required`` telling the operator how to recover.
        """
        inst = PluginLoader(plugins_dir=tmp_path / "plugins")
        with patch.object(PluginLoader, "discover_plugins",
                          side_effect=OSError("unreadable distribution metadata")), \
                patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()):
            result = inst.install_extension(MODULE_PACK)

        assert result.ok is True
        assert result.refresh_failed is True
        assert result.restart_required is True
        assert "restart" in result.message.lower()

    def test_uninstall_survives_a_failing_rescan(self, loader, fake_pip, registry_refresh):
        """Same contract on the way out: the package is gone either way."""
        with patch.object(PluginLoader, "installed_version", return_value="1.0.0"), \
                patch.object(PluginLoader, "discover_plugins",
                             side_effect=OSError("unreadable distribution metadata")):
            result = loader.uninstall_extension(MODULE_PACK)

        assert result.ok is True
        assert result.refresh_failed is True
        assert result.restart_required is True

    def test_a_failed_rescan_leaves_previous_records_intact(self, tmp_path):
        """Stale but coherent beats truncated.

        A scan that dies part-way must not leave the loader reporting the half
        of the environment it managed to read before it fell over.
        """
        inst = PluginLoader(plugins_dir=tmp_path / "plugins")
        with patch.object(loader_mod, "distributions",
                          lambda: [FakeMetadataDist("Flyto_Modules_Robotics")]):
            inst.discover_plugins(force=True)
        assert set(inst._plugins) == {MODULE_PACK}

        def exploding():
            raise OSError("distribution metadata unreadable")

        with patch.object(loader_mod, "distributions", exploding), pytest.raises(OSError):
            inst.discover_plugins(force=True)

        assert set(inst._plugins) == {MODULE_PACK}

    def test_plugin_kind_does_not_refresh_module_registry(self, loader, fake_pip, registry_refresh):
        eps = [FakeEntryPoint("slack", "flyto_plugin_slack:register", PLUGIN_PACK)]
        with patch.object(PluginLoader, "installed_version", side_effect=[None, "2.0.0"]), \
                with_entry_points(eps):
            result = loader.install_extension(PLUGIN_PACK)

        assert result.ok is True and result.kind == "plugins"
        # flyto.plugins is not the group the module registry loads from.
        registry_refresh.assert_not_called()

    def test_upgrade_reports_restart_required(self, loader, fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", side_effect=["1.0.0", "2.0.0"]), \
                with_entry_points(module_pack_eps()):
            result = loader.install_extension(MODULE_PACK, upgrade=True)

        assert result.ok is True
        assert result.previous_version == "1.0.0"
        assert result.version == "2.0.0"
        assert result.restart_required is True
        assert "--upgrade" in fake_pip.calls[0]["cmd"]

    def test_failed_new_install_is_rolled_back(self, loader, fake_pip, registry_refresh):
        """Installed, but declares no entry point: not an extension. Undo it."""
        with patch.object(PluginLoader, "installed_version", return_value=None), \
                with_entry_points([]):
            result = loader.install_extension(MODULE_PACK)

        assert result.ok is False
        assert result.code == ExtensionErrorCode.ENTRYPOINT_MISSING
        assert result.rolled_back is True
        assert fake_pip.subcommands == ["install", "uninstall"]
        assert "-y" in fake_pip.calls[1]["cmd"]

    def test_failed_upgrade_is_not_rolled_back(self, loader, fake_pip, registry_refresh):
        """Rolling back an upgrade would remove the working version too."""
        with patch.object(PluginLoader, "installed_version", return_value="1.0.0"), \
                with_entry_points([]):
            result = loader.install_extension(MODULE_PACK, upgrade=True)

        assert result.ok is False
        assert result.code == ExtensionErrorCode.ENTRYPOINT_MISSING
        assert result.rolled_back is False
        assert result.restart_required is True
        assert fake_pip.subcommands == ["install"]

    def test_rollback_failure_has_its_own_code(self, loader, registry_refresh):
        pip = FakePip([{"returncode": 0}, {"returncode": 1, "stderr": "boom"}])
        with patch.object(loader_mod.subprocess, "run", pip), \
                patch.object(PluginLoader, "installed_version", return_value=None), \
                with_entry_points([]):
            result = loader.install_extension(MODULE_PACK)

        assert result.code == ExtensionErrorCode.ROLLBACK_FAILED
        assert result.rolled_back is False

    def test_entry_point_proof_ignores_other_distributions(self, loader, fake_pip, registry_refresh):
        """A group full of *someone else's* entry points is not proof."""
        other = [FakeEntryPoint("vision", "flyto_modules_vision:register", "flyto-modules-vision")]
        with patch.object(PluginLoader, "installed_version", return_value=None), \
                with_entry_points(other):
            result = loader.install_extension(MODULE_PACK)

        assert result.code == ExtensionErrorCode.ENTRYPOINT_MISSING

    def test_pip_failure_returns_stable_code_without_stderr(self, loader, registry_refresh):
        secret = "https://user:hunter2@index.internal/simple"
        pip = FakePip([{"returncode": 1, "stderr": f"could not reach {secret}"}])
        with patch.object(loader_mod.subprocess, "run", pip):
            result = loader.install_extension(MODULE_PACK)

        assert result.ok is False
        assert result.code == ExtensionErrorCode.INSTALL_FAILED
        assert secret not in result.message
        assert "hunter2" not in str(result.to_dict())

    def test_timeout_has_its_own_code(self, loader, registry_refresh):
        pip = FakePip([{"timeout": True}])
        with patch.object(loader_mod.subprocess, "run", pip):
            result = loader.install_extension(MODULE_PACK)
        assert result.code == ExtensionErrorCode.TIMEOUT


class TestUninstallContract:

    def test_uninstall_removes_and_requires_restart(self, loader, fake_pip, registry_refresh):
        # Records are keyed by the PEP 503 normalised name, so an alias spelling
        # from the caller reaches the record pip actually wrote. Keyed on the raw
        # spelling instead, this pop would miss and /v1/extensions would keep
        # reporting a pack that is no longer installed.
        key = normalize_extension_name(MODULE_PACK)
        loader._plugins[key] = "record"
        with patch.object(PluginLoader, "installed_version", return_value="1.0.0"), \
                patch.object(PluginLoader, "unload_plugin", return_value=True) as unload:
            result = loader.uninstall_extension("Flyto_Modules_Robotics")

        assert result.ok is True
        assert result.previous_version == "1.0.0"
        assert result.refresh_failed is False
        # Already-imported modules do not leave sys.modules when files do.
        assert result.restart_required is True
        assert fake_pip.subcommands == ["uninstall"]
        registry_refresh.assert_called_once()
        unload.assert_called_once_with(key)
        assert key not in loader._plugins

    def test_uninstall_missing_extension_is_404_shaped(self, loader, fake_pip):
        with patch.object(PluginLoader, "installed_version", return_value=None):
            result = loader.uninstall_extension(MODULE_PACK)
        assert result.code == ExtensionErrorCode.NOT_INSTALLED
        assert fake_pip.calls == []

    def test_uninstall_unsupported_name_is_refused(self, loader, fake_pip):
        result = loader.uninstall_extension("flyto-core")
        assert result.code == ExtensionErrorCode.UNSUPPORTED_EXTENSION
        assert fake_pip.calls == []


class TestNormalisedIds:
    """One id per package, across every surface.

    pip treats ``Flyto_Modules_Robotics`` and ``flyto-modules-robotics`` as one
    project. So must Core: an id a client reads off an install result has to be
    the id the listing shows and the id uninstall matches on, or a caller that
    round-trips what Core gave it is talking about a package Core cannot find.
    """

    ALIAS = "Flyto_Modules_Robotics"

    def test_install_result_id_is_normalised(self, loader, fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()):
            result = loader.install_extension(self.ALIAS)

        assert result.ok is True
        assert result.name == MODULE_PACK

    def test_uninstall_result_id_is_normalised(self, loader, fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", return_value="1.0.0"):
            result = loader.uninstall_extension(self.ALIAS)

        assert result.ok is True
        assert result.name == MODULE_PACK

    def test_failure_ids_are_normalised_too(self, loader, fake_pip):
        result = loader.install_extension(self.ALIAS, version="1.0; rm -rf /")
        assert result.code == ExtensionErrorCode.INVALID_VERSION
        assert result.name == MODULE_PACK
        assert fake_pip.calls == []

    def test_discovered_records_are_keyed_and_named_by_the_normalised_id(self, tmp_path):
        """The stored name is the id, not the spelling the distribution declares.

        Named on the raw metadata spelling, ``list_extensions`` would hand a
        client an id that ``uninstall_extension`` then fails to match.
        """
        inst = PluginLoader(plugins_dir=tmp_path / "plugins")
        with patch.object(loader_mod, "distributions",
                          lambda: [FakeMetadataDist(self.ALIAS)]):
            plugins = inst.discover_plugins(force=True)

        assert set(plugins) == {MODULE_PACK}
        assert plugins[MODULE_PACK].name == MODULE_PACK
        assert plugins[MODULE_PACK].kind == "modules"

    def test_an_aliased_install_is_uninstallable_by_the_id_it_reported(
        self, loader, fake_pip, registry_refresh
    ):
        """The round trip the normalisation exists for."""
        with patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()):
            installed = loader.install_extension(self.ALIAS)

        loader._plugins[installed.name] = "record"
        with patch.object(PluginLoader, "installed_version", return_value="1.0.0"), \
                patch.object(PluginLoader, "unload_plugin", return_value=True) as unload:
            removed = loader.uninstall_extension(installed.name)

        assert removed.ok is True
        unload.assert_called_once_with(MODULE_PACK)
        assert installed.name not in loader._plugins


class TestLoaderLock:
    """The loader lock, exercised from real threads.

    A same-thread probe cannot test any of this. The lock is an ``RLock``, so
    the thread already holding it re-acquires it trivially — a probe taken from
    inside the pip call reports "free" no matter how well the lock works.
    Blocking is only observable from a *second* thread, so that is what these
    tests use.
    """

    def test_lock_is_reentrant_for_the_holding_thread(self, loader, fake_pip,
                                                      registry_refresh):
        """Reentrancy is load-bearing, not a convenience.

        A mutation holds the lock and then calls the public reads under it:
        ``_refresh_after_change`` calls ``discover_plugins``, and an uninstall
        calls ``unload_plugin``. With a plain ``Lock`` the very first install
        would deadlock against itself.
        """
        reacquired = []

        def probe(*a, **k):
            got = loader._lock.acquire(blocking=False)
            reacquired.append(got)
            if got:
                loader._lock.release()
            return fake_pip(*a, **k)

        with patch.object(loader_mod.subprocess, "run", probe), \
                with_entry_points(module_pack_eps()):
            result = loader.install_extension(MODULE_PACK)

        assert result.ok is True
        assert reacquired == [True]
        # And fully released when the operation is over — checked from another
        # thread, which is the only place a leaked recursion count would show.
        assert acquire_from_another_thread(loader._lock) is True

    def test_a_second_thread_blocks_for_the_whole_pip_run(self, loader, fake_pip,
                                                          registry_refresh):
        """A second caller waits out the first install's pip, proof and refresh.

        Each of those steps reads the environment pip just wrote, so a second
        install admitted between any two of them would have the first one
        drawing conclusions about the second one's files.
        """
        in_pip = threading.Event()
        release_pip = threading.Event()
        results = {}

        def parked_pip(*a, **k):
            in_pip.set()
            assert release_pip.wait(5), "test never released the parked pip run"
            return fake_pip(*a, **k)

        def install():
            results["install"] = loader.install_extension(MODULE_PACK)

        # Both patches are installed from this thread, before any worker starts:
        # unittest.mock patching is not itself thread-safe.
        with patch.object(loader_mod.subprocess, "run", parked_pip), \
                with_entry_points(module_pack_eps()):
            worker = threading.Thread(target=install)
            worker.start()
            try:
                assert in_pip.wait(5), "install never reached pip"
                # The worker is parked inside pip holding the lock. This is
                # a different thread, so it must not get in.
                blocked = not acquire_from_another_thread(loader._lock)
            finally:
                release_pip.set()
                worker.join(10)

        assert not worker.is_alive()
        assert blocked is True, "a second thread entered while pip was running"
        assert results["install"].ok is True
        # Released once the operation is over.
        assert acquire_from_another_thread(loader._lock) is True

    def test_concurrent_installs_never_run_pip_at_the_same_time(self, loader,
                                                                registry_refresh):
        """pip is not safe to run twice against one environment.

        Two installs interleaving can leave a half-written distribution, and the
        entry-point proof of one can read the other's files. Four threads race
        here; the lock must flatten them into four sequential pip runs.
        """
        pip = FakePip()
        counter_lock = threading.Lock()
        state = {"active": 0, "max_active": 0}

        def counting_pip(*a, **k):
            with counter_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            # Widen the window a real race would slip through.
            time.sleep(0.05)
            with counter_lock:
                state["active"] -= 1
            return pip(*a, **k)

        # return_value, not side_effect: a side_effect list is itself unsafe to
        # pop from four threads at once, and would fail this test for a reason
        # that has nothing to do with the lock.
        with patch.object(loader_mod.subprocess, "run", counting_pip), \
                patch.object(PluginLoader, "installed_version", return_value=None), \
                with_entry_points(module_pack_eps()):
            workers = [
                threading.Thread(target=loader.install_extension, args=(MODULE_PACK,))
                for _ in range(4)
            ]
            for w in workers:
                w.start()
            for w in workers:
                w.join(20)

        assert not any(w.is_alive() for w in workers)
        assert len(pip.calls) == 4
        assert state["max_active"] == 1, "two pip runs overlapped"

    def test_a_read_blocks_while_a_mutation_holds_the_lock(self, loader, fake_pip,
                                                           registry_refresh):
        """Reads take the lock too, not just mutations.

        A listing taken while an install sits between pip and its refresh
        describes neither the old state nor the new one, and one taken during
        the refresh would iterate a mapping another thread is rebuilding.
        """
        in_pip = threading.Event()
        release_pip = threading.Event()
        reader_ready = threading.Event()
        listing_returned = threading.Event()

        def parked_pip(*a, **k):
            in_pip.set()
            assert release_pip.wait(5), "test never released the parked pip run"
            return fake_pip(*a, **k)

        def read():
            # Signalled immediately before the call, so the wait below measures
            # the lock rather than how long this thread took to get scheduled.
            reader_ready.set()
            loader.list_extensions()
            listing_returned.set()

        with patch.object(loader_mod.subprocess, "run", parked_pip), \
                with_entry_points(module_pack_eps()):
            writer = threading.Thread(
                target=loader.install_extension, args=(MODULE_PACK,)
            )
            writer.start()
            reader = threading.Thread(target=read)
            try:
                assert in_pip.wait(5), "install never reached pip"
                reader.start()
                assert reader_ready.wait(5), "reader thread never started"
                # The reader has called in and must still be waiting.
                blocked = not listing_returned.wait(0.25)
            finally:
                release_pip.set()
                writer.join(10)
                reader.join(10)

        assert blocked is True, "a read slipped through mid-mutation"
        # ...and it completes once the mutation lets go.
        assert listing_returned.is_set()


class TestPreservedPluginApi:

    def test_install_plugin_still_takes_a_bare_name_and_returns_bool(
        self, loader, fake_pip, registry_refresh
    ):
        eps = [FakeEntryPoint("slack", "flyto_plugin_slack:register", PLUGIN_PACK)]
        with patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(eps):
            assert loader.install_plugin("slack") is True
        assert f"{PLUGINS_KIND.prefix}slack" in fake_pip.calls[0]["cmd"]

    def test_uninstall_plugin_still_returns_bool(self, loader, fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", return_value="1.0.0"):
            assert loader.uninstall_plugin("slack") is True


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(app):
    from core.api import security as sec
    return {"Authorization": f"Bearer {sec._active_token}"}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv(ext_routes.INSTALL_ENABLED_ENV, "1")


@pytest.fixture
def disabled(monkeypatch):
    monkeypatch.delenv(ext_routes.INSTALL_ENABLED_ENV, raising=False)


class TestExtensionRoutesAuth:

    @pytest.mark.parametrize("method,path,body", [
        ("get", "/v1/extensions", None),
        ("get", "/v1/extensions/kinds", None),
        ("post", "/v1/extensions/install", {"name": MODULE_PACK}),
        ("post", "/v1/extensions/uninstall", {"name": MODULE_PACK}),
    ])
    def test_every_route_requires_auth(self, client, method, path, body):
        resp = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
        assert resp.status_code in (401, 403)

    def test_wrong_token_is_rejected(self, client):
        resp = client.get("/v1/extensions", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    def test_install_is_not_attempted_when_unauthenticated(self, client):
        with patch.object(PluginLoader, "install_extension") as install:
            client.post("/v1/extensions/install", json={"name": MODULE_PACK})
        install.assert_not_called()


class TestExtensionRoutes:

    def test_list_reports_both_kinds(self, client, auth):
        listing = [
            {"name": MODULE_PACK, "kind": "modules", "version": "1.0.0",
             "loaded": True, "load_error": None, "status": "installed",
             "description": "", "module_count": 3, "entry_points": ["robotics"]},
            {"name": PLUGIN_PACK, "kind": "plugins", "version": "2.0.0",
             "loaded": False, "load_error": None, "status": "installed",
             "description": "", "module_count": 1, "entry_points": ["slack"]},
        ]
        with patch.object(ext_routes, "run_in_threadpool",
                          wraps=ext_routes.run_in_threadpool) as offload, \
                patch.object(PluginLoader, "list_extensions", return_value=listing):
            resp = client.get("/v1/extensions", headers=auth)

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert {e["kind"] for e in body["extensions"]} == {"modules", "plugins"}
        # Listing walks installed distributions, which is blocking work.
        assert offload.call_count == 1

    def test_kinds_endpoint_mirrors_the_installer_table(self, client, auth):
        resp = client.get("/v1/extensions/kinds", headers=auth)
        assert resp.status_code == 200
        kinds = resp.json()["kinds"]
        assert [k["prefix"] for k in kinds] == [k.prefix for k in EXTENSION_KINDS]
        assert [k["entry_point_group"] for k in kinds] == [
            k.entry_point_group for k in EXTENSION_KINDS
        ]

    def test_install_is_disabled_without_operator_opt_in(self, client, auth, disabled):
        with patch.object(PluginLoader, "install_extension") as install:
            resp = client.post("/v1/extensions/install",
                               json={"name": MODULE_PACK}, headers=auth)

        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == ext_routes.MANAGEMENT_DISABLED
        install.assert_not_called()

    def test_uninstall_is_disabled_without_operator_opt_in(self, client, auth, disabled):
        with patch.object(PluginLoader, "uninstall_extension") as uninstall:
            resp = client.post("/v1/extensions/uninstall",
                               json={"name": MODULE_PACK}, headers=auth)
        assert resp.status_code == 403
        uninstall.assert_not_called()

    @pytest.mark.parametrize("path", ["install", "uninstall"])
    def test_disabled_refusal_returns_a_normalised_id(self, client, auth, disabled, path):
        """A refusal is still an answer about a package.

        This is the response an operator is most likely to script against, so
        echoing back the caller's raw spelling here would make it the one
        surface where an extension id is unstable.
        """
        resp = client.post(f"/v1/extensions/{path}",
                           json={"name": "Flyto_Modules_Robotics"}, headers=auth)

        assert resp.status_code == 403
        error = resp.json()["error"]
        assert error["code"] == ext_routes.MANAGEMENT_DISABLED
        assert error["name"] == MODULE_PACK

    def test_install_module_pack_end_to_end(self, client, auth, enabled,
                                            fake_pip, registry_refresh):
        with patch.object(ext_routes, "run_in_threadpool",
                          wraps=ext_routes.run_in_threadpool) as offload, \
                patch.object(PluginLoader, "installed_version", side_effect=[None, "1.0.0"]), \
                with_entry_points(module_pack_eps()), \
                patch.object(PluginLoader, "discover_plugins", return_value={}):
            resp = client.post("/v1/extensions/install",
                               json={"name": MODULE_PACK}, headers=auth)

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["kind"] == "modules"
        assert body["restart_required"] is False
        assert body["refresh_failed"] is False
        assert body["entry_points"] == ["robotics"]
        # pip is bounded at two minutes; on the event loop that is two minutes
        # of stalled health checks, so the route must offload it.
        assert offload.call_count == 1

    def test_upgrade_response_carries_restart_required(self, client, auth, enabled,
                                                       fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", side_effect=["1.0.0", "2.0.0"]), \
                with_entry_points(module_pack_eps()), \
                patch.object(PluginLoader, "discover_plugins", return_value={}):
            resp = client.post(
                "/v1/extensions/install",
                json={"name": MODULE_PACK, "upgrade": True},
                headers=auth,
            )

        assert resp.status_code == 200
        assert resp.json()["restart_required"] is True

    @pytest.mark.parametrize("code,status", [
        (ExtensionErrorCode.UNSUPPORTED_EXTENSION, 400),
        (ExtensionErrorCode.INVALID_NAME, 400),
        (ExtensionErrorCode.INVALID_VERSION, 400),
        (ExtensionErrorCode.NOT_INSTALLED, 404),
        (ExtensionErrorCode.ENTRYPOINT_MISSING, 409),
        (ExtensionErrorCode.ROLLBACK_FAILED, 409),
        (ExtensionErrorCode.INSTALL_FAILED, 502),
        (ExtensionErrorCode.UNINSTALL_FAILED, 502),
        (ExtensionErrorCode.TIMEOUT, 504),
    ])
    def test_every_error_code_maps_to_a_fixed_status(self, code, status):
        assert ext_routes._STATUS_BY_CODE[code] == status

    def test_unsupported_name_rejected_over_http(self, client, auth, enabled, fake_pip):
        resp = client.post("/v1/extensions/install", json={"name": "requests"}, headers=auth)
        assert resp.status_code == 400
        body = resp.json()
        assert body["ok"] is False
        assert body["error"]["code"] == ExtensionErrorCode.UNSUPPORTED_EXTENSION
        assert body["error"]["name"] == "requests"
        assert fake_pip.calls == []

    def test_pip_stderr_never_reaches_the_client(self, client, auth, enabled, registry_refresh):
        secret = "https://user:hunter2@index.internal/simple"
        pip = FakePip([{"returncode": 1, "stderr": f"HTTP error from {secret}"}])
        with patch.object(loader_mod.subprocess, "run", pip):
            resp = client.post("/v1/extensions/install",
                               json={"name": MODULE_PACK}, headers=auth)

        assert resp.status_code == 502
        assert resp.json()["error"]["code"] == ExtensionErrorCode.INSTALL_FAILED
        assert "hunter2" not in resp.text
        assert "index.internal" not in resp.text

    def test_rollback_is_reported_to_the_client(self, client, auth, enabled,
                                                fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", return_value=None), \
                with_entry_points([]), \
                patch.object(PluginLoader, "discover_plugins", return_value={}):
            resp = client.post("/v1/extensions/install",
                               json={"name": MODULE_PACK}, headers=auth)

        assert resp.status_code == 409
        error = resp.json()["error"]
        assert error["code"] == ExtensionErrorCode.ENTRYPOINT_MISSING
        assert error["rolled_back"] is True
        # The rollback's own refresh succeeded, so nothing stale is left behind.
        assert error["refresh_failed"] is False

    def test_uninstall_missing_extension_is_404(self, client, auth, enabled,
                                                fake_pip, registry_refresh):
        with patch.object(PluginLoader, "installed_version", return_value=None):
            resp = client.post("/v1/extensions/uninstall",
                               json={"name": MODULE_PACK}, headers=auth)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == ExtensionErrorCode.NOT_INSTALLED

    def test_empty_name_is_rejected_by_the_model(self, client, auth, enabled):
        resp = client.post("/v1/extensions/install", json={"name": ""}, headers=auth)
        assert resp.status_code == 422

    def test_info_advertises_extension_management(self, client):
        assert "extension_management" in client.get("/v1/info").json()["capabilities"]
