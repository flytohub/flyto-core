# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Registry-wide coverage for the filesystem sandbox boundary.

Every published arbitrary file read/write advisory against this project has the
same shape: a module takes a caller-supplied path and reaches a filesystem sink
without routing it through ``validate_path_with_env_config``. GHSA-2956-977x-2w3r,
GHSA-p34x-fmph-9fjx, GHSA-xchh-cp84-9838, GHSA-hmq9-xw4w-7ppc,
GHSA-wc94-386q-5478 and GHSA-p64w-hgfm-824v are all that bug, found one module
at a time, wave after wave.

Fixing them individually never converged because nothing checked *coverage* —
the guard exists and is centralized, but calling it was a thing an author had to
remember. This module makes forgetting a test failure instead of an advisory:

* :func:`test_every_path_param_module_reaches_the_sandbox_helper` walks the whole
  registry and fails on any module that declares a path-shaped parameter without
  referencing the guard. It reads the *handler*, not the file: this check used to
  scan whole source files, so ``cloud.aws_s3.upload`` counted as guarded because
  ``aws_s3_download`` — a different function, further down the same file — called
  the helper. GHSA-45hf-2fmj-q442 is exactly that pair, and the same file holds
  the same asymmetry for Azure and GCS. A guarded twin cannot vouch for its
  sibling any more.
* :func:`test_allowlisted_modules_have_no_filesystem_sink` is the tripwire under
  the allowlist: an entry is only excused while the module genuinely has no
  filesystem sink, so implementing a stub or adding a write later fails here
  rather than silently inheriting an exemption.
* :func:`test_allowlist_has_no_stale_entries` keeps the allowlist honest as
  modules are renamed or removed.

Adding a module with a path parameter therefore forces one of two explicit acts:
call the guard, or write down in ``NON_FILESYSTEM_PARAMS`` why the parameter is
not a filesystem path.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

from core.modules import atomic  # noqa: F401 — registers the module catalog
from core.modules.registry.core import ModuleRegistry

# Parameter names that denote a filesystem location. Deliberately generous:
# a false positive costs one allowlist line with a reason, a false negative
# costs an advisory.
PATH_PARAM_RE = re.compile(
    r"(^|_)(path|paths|file|files|dir|dirs|directory|filepath|filename|destination"
    r"|attachment|attachments)$"
)

# The centralized helpers in core/utils.py. Referencing either one in a module's
# source is what counts as reaching the boundary.
GUARD_SYMBOLS = ("validate_path_with_env_config", "validate_path_safe")

# Anything that touches the filesystem. Used only for the allowlist tripwire.
FILESYSTEM_SINK_RE = re.compile(
    r"\bopen\("
    r"|\.read_text\(|\.write_text\(|\.read_bytes\(|\.write_bytes\("
    r"|os\.remove\(|os\.unlink\(|os\.makedirs\(|os\.mkdir\(|\.mkdir\("
    r"|shutil\."
    r"|os\.path\.exists\(|os\.path\.isfile\(|os\.path\.isdir\("
    r"|\.exists\(\)|\.is_file\(\)|\.is_dir\(\)"
)


# Parameters whose name matches PATH_PARAM_RE but which are not filesystem
# paths. Every entry states what the value actually addresses — that sentence is
# the review artifact, and the tripwire below enforces that it stays true.
NON_FILESYSTEM_PARAMS = {
    "object.get": {"path": "JSONPath expression into the input object, never a file"},
    "object.set": {"path": "JSONPath expression into the input object, never a file"},
    "http.paginate": {
        "data_path": "dotted key path into the JSON response body",
        "cursor_path": "dotted key path into the JSON response body",
    },
    "http.response_assert": {"json_path": "JSONPath expression against the response body"},
    "flow.trigger": {"webhook_path": "URL path segment this workflow listens on"},
    "http.webhook_wait": {"path": "URL path segment this workflow listens on"},
    "browser.cookies": {
        "path": "cookie Path attribute (RFC 6265), default '/'; the "
                "filesystem-backed sibling is browser.cookies_file, which is guarded"
    },
    "file.diff": {
        "filename": "display label written into the unified-diff header; "
                    "the two inputs are in-memory strings, not paths"
    },
    "llm.agent": {"prompt_path": "prompt template string, default '{{input}}'"},
    "reverse.hook": {
        "function_path": "JavaScript property path such as window.fetch, resolved "
                         "inside the attached page rather than on the host filesystem"
    },
    "slack.send": {
        "attachments": "Slack Block Kit attachment objects serialized into the "
                       "webhook JSON payload, not local file paths"
    },
    "path.basename": {"path": "pure string manipulation, no filesystem access"},
    "path.dirname": {"path": "pure string manipulation, no filesystem access"},
    "path.extension": {"path": "pure string manipulation, no filesystem access"},
    "path.is_absolute": {"path": "pure string manipulation, no filesystem access"},
    "path.normalize": {"path": "pure string manipulation, no filesystem access"},
    "testing.lint.run": {"paths": "placeholder implementation, echoes the count only"},
    "testing.unit.run": {"paths": "placeholder implementation, echoes the count only"},
    "verification.report": {
        "output_path": "declared in the schema but never read by the handler"
    },
}


def _module_source(module_id: str) -> Path:
    """Return the file that defines a module.

    Function-style modules are wrapped by ``register_module``; the wrapper
    carries ``__module__`` from the original function so this resolves to the
    real source rather than decorators.py.
    """
    module_class = ModuleRegistry.get(module_id)
    return Path(sys.modules[module_class.__module__].__file__)


def _registered_name(module_id: str) -> str:
    """The name of the function or class ``register_module`` was applied to."""
    module_class = ModuleRegistry.get(module_id)
    wrapped = getattr(module_class, "__wrapped_func__", None)
    return wrapped.__name__ if wrapped is not None else module_class.__name__


_DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _definitions(source: str) -> dict:
    """Every top-level-reachable def/class in a file, by name."""
    return {
        node.name: node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, _DEFINITION_NODES)
    }


def _called_names(node) -> set:
    """Names this definition calls, whether bare or through an attribute."""
    names = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _reaches_guard(module_id: str) -> bool:
    """Whether this module's own handler reaches the sandbox helper.

    One hop of indirection counts, because a handler that hands the path to a
    helper in its own file — ``_prepare_output``, ``draw_annotations`` — has
    genuinely routed it through the guard. Two functions that merely share a
    file have not, which is the distinction the old file-wide scan could not
    make.
    """
    source = _module_source(module_id).read_text(encoding="utf-8")
    definitions = _definitions(source)
    node = definitions.get(_registered_name(module_id))
    if node is None:  # unparseable shape: fall back to the file-wide answer
        return any(symbol in source for symbol in GUARD_SYMBOLS)

    reachable = [node]
    for name in _called_names(node):
        helper = definitions.get(name)
        if helper is not None:
            reachable.append(helper)
            for nested in _called_names(helper):
                deeper = definitions.get(nested)
                if deeper is not None:
                    reachable.append(deeper)

    return any(
        symbol in (ast.get_source_segment(source, reached) or "")
        for reached in reachable
        for symbol in GUARD_SYMBOLS
    )


def _path_params(metadata: dict) -> list:
    schema = metadata.get("params_schema") or {}
    return sorted(name for name in schema if PATH_PARAM_RE.search(name))


def _registry_path_params():
    """(module_id, [param names]) for every module declaring a path parameter."""
    # Runtime stability visibility is product policy. Security coverage must
    # inspect every registered module, including beta and experimental sinks.
    all_metadata = ModuleRegistry.get_all_metadata(filter_by_stability=False)
    for module_id, metadata in sorted(all_metadata.items()):
        names = _path_params(metadata)
        if names:
            yield module_id, names


def test_registry_is_populated():
    """Guard against the whole suite passing vacuously on an empty registry."""
    assert ModuleRegistry.module_count() > 300
    assert sum(1 for _ in _registry_path_params()) > 50


def test_every_path_param_module_reaches_the_sandbox_helper():
    """No module may take a path parameter without reaching the guard.

    A failure here is not a style violation. It is the precondition for every
    arbitrary file read/write advisory this project has published.
    """
    offenders = []

    for module_id, names in _registry_path_params():
        if _reaches_guard(module_id):
            continue

        excused = NON_FILESYSTEM_PARAMS.get(module_id, {})
        unexplained = [name for name in names if name not in excused]
        if unexplained:
            offenders.append(f"{module_id}: {unexplained}")

    assert not offenders, (
        "These modules take a filesystem-shaped parameter but never reach "
        "validate_path_with_env_config:\n  "
        + "\n  ".join(offenders)
        + "\n\nEither call the guard, or add the parameter to "
          "NON_FILESYSTEM_PARAMS with a note on what the value really "
          "addresses (a JSONPath, a URL segment, a remote host path)."
    )


@pytest.mark.parametrize("module_id", sorted(NON_FILESYSTEM_PARAMS))
def test_allowlisted_modules_have_no_filesystem_sink(module_id):
    """An allowlist entry is only valid while the module touches no files.

    This is what keeps the exemptions from going stale. ``testing.unit.run`` and
    ``testing.lint.run`` are placeholders today; the day one is implemented for
    real it will open files, fail here, and have to be guarded — instead of
    inheriting an exemption written when it did nothing.
    """
    source = _module_source(module_id).read_text(encoding="utf-8")
    sinks = sorted(set(FILESYSTEM_SINK_RE.findall(source)))

    assert not sinks, (
        f"{module_id} is in NON_FILESYSTEM_PARAMS on the grounds that its path "
        f"parameter is not a filesystem path, but its source now contains "
        f"filesystem operations {sinks}. Route the parameter through "
        f"validate_path_with_env_config and drop the allowlist entry."
    )


def test_allowlist_has_no_stale_entries():
    """Every allowlisted module and parameter must still exist and still match."""
    live = dict(_registry_path_params())
    stale = []

    for module_id, params in NON_FILESYSTEM_PARAMS.items():
        if module_id not in live:
            stale.append(f"{module_id}: no longer declares a path parameter")
            continue
        for name in params:
            if name not in live[module_id]:
                stale.append(f"{module_id}.{name}: parameter is gone")

    assert not stale, "NON_FILESYSTEM_PARAMS has drifted from the registry:\n  " + "\n  ".join(stale)


def test_allowlist_entries_state_a_reason():
    """A bare exemption is not reviewable; require a real sentence."""
    thin = [
        f"{module_id}.{name}"
        for module_id, params in NON_FILESYSTEM_PARAMS.items()
        for name, reason in params.items()
        if len(reason.strip()) < 25
    ]
    assert not thin, f"These allowlist entries need a substantive reason: {thin}"
