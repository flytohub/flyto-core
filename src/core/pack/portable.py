# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""The portable pack: one ``flyto.pack.v1`` artifact, two ways to run it.

A connector pack that carries a ``standalone`` section runs on its own, as
an MCP server on the user's machine with the user's own credentials and no
Flyto2 service involved, and the very same zip loads into a Flyto2 Space
through ``core.pack.host.install_pack``. There is no second version to keep
in step.

The author writes three things::

    "standalone": {
      "transports": ["stdio", "streamable_http"],
      "runtime": {"language": "python", "version": ">=3.10"},
      "lockfile": "requirements.lock"
    }

Core derives the rest when it normalizes the manifest, from the tables in
this file and the pack's own ``connector.auth``: the credential names the
user must supply (names only; each value is read at run time from
``FLYTO_CREDENTIAL_<NAME>`` or the OS keychain), and the install,
healthcheck and serve entry points for every platform in :data:`PLATFORMS`.
A hand-written ``credentials`` or ``entry_points`` is refused
(``STANDALONE_DERIVED``): a second copy could only disagree.

:func:`build_portable_pack` turns a source directory into the artifact: it
writes the entry-point scripts, a README and a third-party notice (all
generated, none hand-written per pack), places the hashed lockfile, sets
``artifact.digest`` over the result, signs it when given a key, verifies
what it built, and writes one deterministic zip. Two builds of one source
are byte-identical.

There is no server code in a pack. Every entry point runs ``flyto pack run``
or ``flyto pack health`` from the flyto-core the lockfile pins, and that one
runtime (``core.pack.standalone``) serves any connector pack from its
manifest.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from .manifest import (
    MANIFEST_FILENAME,
    MAX_TREE_BYTES,
    MAX_TREE_FILES,
    SIGNATURE_FILENAME,
    PackManifestError,
    _iter_pack_files,
    _read_regular_file,
    pack_tree_digest,
    read_pack_manifest,
    validate_pack_manifest,
)

__all__ = [
    "STANDALONE_TRANSPORTS",
    "STANDALONE_RUNTIMES",
    "PLATFORMS",
    "ENTRY_ACTIONS",
    "CREDENTIAL_ENV_PREFIX",
    "KEYCHAIN_SERVICE_PREFIX",
    "validate_standalone",
    "build_portable_pack",
    "extract_pack_zip",
    "opened_pack",
    "verify_pack",
    "verify_pack_dir",
]

#: The MCP transports a standalone pack can declare.
STANDALONE_TRANSPORTS = ("stdio", "streamable_http")

#: Binding -> the runtime that serves it standalone. A connector pack has no
#: code of its own; flyto-core's generic runtime serves it, so its runtime is
#: Python and the package the lockfile must pin is flyto-core.
STANDALONE_RUNTIMES: Mapping[str, Mapping[str, str]] = {
    "connector": {"language": "python", "package": "flyto-core"},
}

#: How an entry point is started on each platform, where the script lives,
#: and where the pack's environment is created (outside the pack, so
#: installing never changes the files ``artifact.digest`` covers).
PLATFORMS: Mapping[str, Mapping[str, Any]] = {
    "macos": {"suffix": ".sh", "launcher": ("sh",), "sep": "/", "dialect": "posix",
              "home": "$HOME/Library/Application Support/flyto/packs"},
    "linux": {"suffix": ".sh", "launcher": ("sh",), "sep": "/", "dialect": "posix",
              "home": "${XDG_DATA_HOME:-$HOME/.local/share}/flyto/packs"},
    "windows": {"suffix": ".cmd", "launcher": ("cmd.exe", "/d", "/c"), "sep": "\\", "dialect": "cmd",
                "home": "%LOCALAPPDATA%\\flyto\\packs"},
}

#: The entry points every platform gets.
ENTRY_ACTIONS = ("install", "healthcheck", "serve")

CREDENTIAL_ENV_PREFIX = "FLYTO_CREDENTIAL_"
KEYCHAIN_SERVICE_PREFIX = "flyto.pack."

GENERATED_DIR = "bin"
README_FILENAME = "README.md"
NOTICE_FILENAME = "THIRD_PARTY_NOTICES.md"
#: Paths a build writes. A source that already holds one is refused, so a
#: generated file can never be shadowed by a hand-written one.
RESERVED_PREFIXES = (GENERATED_DIR + "/",)
RESERVED_FILES = (NOTICE_FILENAME,)

_AUTHOR_KEYS = frozenset({"transports", "runtime", "lockfile"})
_DERIVED_KEYS = frozenset({"credentials", "credentials_needed", "entry_points"})
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_MAX_ZIP_NAME = 512


def _fail(code: str, message: str) -> None:
    raise PackManifestError(code, message)


# ---------------------------------------------------------------------------
# The standalone section
# ---------------------------------------------------------------------------


def _safe_relative(path: Any, where: str) -> str:
    if type(path) is not str or not path or len(path) > 256:
        _fail("INVALID_STANDALONE", f"{where} must be a relative path inside the pack")
    parts = path.split("/")
    if (
        path.startswith("/") or "\\" in path or ":" in path or "\x00" in path
        or any(part in ("", ".", "..") for part in parts)
    ):
        _fail("INVALID_STANDALONE", f"{where} must be a relative path inside the pack")
    if path in (MANIFEST_FILENAME, SIGNATURE_FILENAME, README_FILENAME) or _reserved(path):
        _fail("INVALID_STANDALONE", f"{where} names a file the build writes")
    return path


def _reserved(rel: str) -> bool:
    return rel in RESERVED_FILES or any(rel.startswith(prefix) for prefix in RESERVED_PREFIXES)


def _python_floor(version: Any) -> Tuple[int, int]:
    """``>=3.10`` -> ``(3, 10)``. Only a floor is accepted: it is what a script can check."""
    import re

    match = re.fullmatch(r">=(\d{1,2})\.(\d{1,3})", version) if type(version) is str else None
    if match is None:
        _fail("STANDALONE_RUNTIME_UNSUPPORTED", "standalone.runtime.version must be a floor such as >=3.10")
    return int(match.group(1)), int(match.group(2))


def _entry(platform: str, action: str) -> str:
    spec = PLATFORMS[platform]
    return spec["sep"].join((GENERATED_DIR, platform, action + spec["suffix"]))


def _entry_points(transports: List[str]) -> Dict[str, Dict[str, Any]]:
    points: Dict[str, Dict[str, Any]] = {}
    for platform, spec in PLATFORMS.items():
        launcher = list(spec["launcher"])
        points[platform] = {
            "install": launcher + [_entry(platform, "install")],
            "healthcheck": launcher + [_entry(platform, "healthcheck")],
            "serve": {t: launcher + [_entry(platform, "serve"), "--transport", t] for t in transports},
        }
    return points


def credential_env(name: str) -> str:
    return CREDENTIAL_ENV_PREFIX + name.upper()


def validate_standalone(value: Any, manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """The normalized ``standalone`` section of ``manifest``, or a typed refusal."""
    binding = manifest["runtime"]["binding"]
    if binding not in STANDALONE_RUNTIMES:
        _fail("STANDALONE_BINDING_UNSUPPORTED",
              f"standalone needs a binding core serves on its own: {', '.join(STANDALONE_RUNTIMES)}")
    if type(value) is not dict:
        _fail("INVALID_STANDALONE", "standalone must be an object")
    if _DERIVED_KEYS & set(value):
        _fail("STANDALONE_DERIVED", "standalone credentials and entry points are derived by core, not declared")
    unknown = set(value) - _AUTHOR_KEYS
    if unknown:
        _fail("UNKNOWN_KEY", f"standalone contains an unknown key: {sorted(unknown)[0]}")
    missing = sorted(_AUTHOR_KEYS - set(value))
    if missing:
        _fail("MISSING_FIELD", f"standalone is missing required field: {missing[0]}")

    transports = value["transports"]
    if type(transports) is not list or not transports or len(set(map(str, transports))) != len(transports):
        _fail("INVALID_STANDALONE", "standalone.transports must list each transport once")
    for transport in transports:
        if transport not in STANDALONE_TRANSPORTS:
            _fail("STANDALONE_TRANSPORT_UNKNOWN",
                  f"standalone.transports names one of {', '.join(STANDALONE_TRANSPORTS)}")
    ordered = [t for t in STANDALONE_TRANSPORTS if t in transports]

    expected = STANDALONE_RUNTIMES[binding]
    runtime = value["runtime"]
    if type(runtime) is not dict or set(runtime) != {"language", "version"}:
        _fail("STANDALONE_RUNTIME_UNSUPPORTED", "standalone.runtime is {language, version}")
    if runtime["language"] != expected["language"]:
        _fail("STANDALONE_RUNTIME_UNSUPPORTED",
              f"a {binding} pack runs on the {expected['language']} runtime of {expected['package']}")
    _python_floor(runtime["version"])

    from .supply_chain import LOCKFILE_FORMAT

    lockfile = _safe_relative(value["lockfile"], "standalone.lockfile")
    pack_id = manifest["pack"]["id"]
    credentials = []
    for entry in (manifest.get("connector") or {}).get("auth") or ():
        name = entry["credential"]
        if any(item["name"] == name for item in credentials):
            continue
        credentials.append({
            "name": name,
            "env": credential_env(name),
            "keychain": {"service": KEYCHAIN_SERVICE_PREFIX + pack_id, "account": name},
        })
    return {
        "transports": ordered,
        "runtime": {"language": runtime["language"], "version": runtime["version"], "package": expected["package"]},
        "lockfile": {"path": lockfile, "format": LOCKFILE_FORMAT},
        # The connector tries its auth entries in order and uses the first
        # whose credential resolves, so one of them is enough.
        "credentials": credentials,
        "credentials_needed": "one_of" if credentials else "none",
        "entry_points": _entry_points(ordered),
    }


# ---------------------------------------------------------------------------
# Generated files
# ---------------------------------------------------------------------------

_POSIX_HEAD = """#!/bin/sh
# {action} for {pack_id} {version}, generated by flyto-core {core} from flyto-pack.json.
# Do not edit: artifact.digest covers this file, and the pack refuses to start if it changes.
set -eu
PACK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
VENV="${{FLYTO_PACK_HOME:-{home}}}/{pack_id}/{version}/venv"
"""

_POSIX_BODY = {
    "install": """PY="${{FLYTO_PYTHON:-python3}}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= ({major}, {minor}) else 1)' \\
  || {{ echo "{pack_id} needs Python {floor}" >&2; exit 1; }}
"$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --require-hashes --only-binary=:all: -r "$PACK_DIR/{lockfile}"
echo "Installed {pack_id} {version}. Check it with: sh bin/{platform}/healthcheck.sh" >&2
""",
    "healthcheck": """exec "$VENV/bin/flyto" pack health "$PACK_DIR" "$@"
""",
    "serve": """exec "$VENV/bin/flyto" pack run "$PACK_DIR" "$@"
""",
}

_CMD_HEAD = """@echo off
rem {action} for {pack_id} {version}, generated by flyto-core {core} from flyto-pack.json.
rem Do not edit: artifact.digest covers this file, and the pack refuses to start if it changes.
setlocal
set "PACK_DIR=%~dp0..\\.."
if defined FLYTO_PACK_HOME (set "PACK_HOME=%FLYTO_PACK_HOME%") else (set "PACK_HOME={home}")
set "VENV=%PACK_HOME%\\{pack_id}\\{version}\\venv"
"""

_CMD_BODY = {
    "install": """if defined FLYTO_PYTHON (set "PY=%FLYTO_PYTHON%") else (set "PY=python")
"%PY%" -c "import sys; sys.exit(0 if sys.version_info >= ({major}, {minor}) else 1)" || (echo {pack_id} needs Python {floor_cmd} 1>&2 & exit /b 1)
"%PY%" -m venv "%VENV%" || exit /b 1
"%VENV%\\Scripts\\python.exe" -m pip install --require-hashes --only-binary=:all: -r "%PACK_DIR%\\{lockfile_win}" || exit /b 1
echo Installed {pack_id} {version}. Check it with: bin\\windows\\healthcheck.cmd 1>&2
""",
    "healthcheck": """"%VENV%\\Scripts\\flyto.exe" pack health "%PACK_DIR%" %*
exit /b %ERRORLEVEL%
""",
    "serve": """"%VENV%\\Scripts\\flyto.exe" pack run "%PACK_DIR%" %*
exit /b %ERRORLEVEL%
""",
}

#: Script dialect -> (head, bodies, line ending).
_DIALECTS = {"posix": (_POSIX_HEAD, _POSIX_BODY, "\n"), "cmd": (_CMD_HEAD, _CMD_BODY, "\r\n")}


def _core_version() -> str:
    from .host import _host_version

    return _host_version()


def render_script(platform: str, action: str, manifest: Mapping[str, Any]) -> bytes:
    """One entry-point script, from the manifest and the platform table alone."""
    spec = PLATFORMS[platform]
    head, bodies, newline = _DIALECTS[spec["dialect"]]
    standalone = manifest["standalone"]
    major, minor = _python_floor(standalone["runtime"]["version"])
    fields = {
        "action": action, "platform": platform, "core": _core_version(), "home": spec["home"],
        "pack_id": manifest["pack"]["id"], "version": manifest["pack"]["version"],
        "major": major, "minor": minor, "floor": standalone["runtime"]["version"],
        "floor_cmd": standalone["runtime"]["version"].replace(">", "^>"),
        "lockfile": standalone["lockfile"]["path"],
        "lockfile_win": standalone["lockfile"]["path"].replace("/", "\\"),
    }
    text = head.format(**fields) + bodies[action].format(**fields)
    return text.replace("\n", newline).encode("utf-8")


def _tool_rows(manifest: Mapping[str, Any]) -> List[str]:
    from .connector import CONSEQUENCE_ANNOTATIONS, module_id_for

    namespace = manifest["pack"]["namespaces"][0]
    rows = ["| Tool | Operation | Consequence | Read-only | Destructive | Requires |",
            "| --- | --- | --- | --- | --- | --- |"]
    for op in manifest["connector"]["operations"]:
        hints = CONSEQUENCE_ANNOTATIONS[op["consequence"]]
        required = (op.get("requires") or {}).get("features") or []
        keys = required.get("any", []) if isinstance(required, Mapping) else required
        needs = (" or " if isinstance(required, Mapping) else ", ").join(f"`{key}`" for key in keys) or "-"
        rows.append(
            f"| `{module_id_for(namespace, op['id'])}` | {op.get('label', op['id'])} | {op['consequence']} | "
            f"{'yes' if hints['readOnlyHint'] else 'no'} | {'yes' if hints['destructiveHint'] else 'no'} | "
            f"{needs} |"
        )
    if manifest.get("entitlements"):
        rows += ["", "`tools/list` shows only the tools your credential is entitled to, as the provider's",
                 f"`{module_id_for(namespace, manifest['entitlements']['probe'])}` answer says. If that answer "
                 "cannot be read, only the tools that require nothing are listed."]
    return rows


def render_readme(manifest: Mapping[str, Any], author_readme: Optional[str]) -> bytes:
    """The pack's README: how to run it on its own, its tools, its credentials."""
    from .standalone_auth import KEYCHAIN_STORE_HINTS

    pack = manifest["pack"]
    standalone = manifest["standalone"]
    title = pack.get("title") or pack["id"]
    lines = [
        f"# {title}",
        "",
        f"`{pack['id']}` {pack['version']}. Generated by flyto-core {_core_version()} from `flyto-pack.json`;",
        "do not edit. The pack's `artifact.digest` covers this file.",
        "",
    ]
    if pack.get("description"):
        lines += [pack["description"], ""]
    lines += [
        "This one artifact runs two ways: on its own, as an MCP server on your machine with your own",
        "credentials, or loaded into a Flyto2 Space from this file. There is no second version.",
        "",
        "## Run it on its own",
        "",
        f"It needs Python {standalone['runtime']['version']}. From the unpacked pack directory:",
        "",
        "| Platform | Install | Healthcheck | Serve (stdio) |",
        "| --- | --- | --- | --- |",
    ]
    for platform, entry in standalone["entry_points"].items():
        serve = entry["serve"].get("stdio") or next(iter(entry["serve"].values()))
        lines.append(f"| {platform} | `{' '.join(entry['install'])}` | `{' '.join(entry['healthcheck'])}` | "
                     f"`{' '.join(serve)}` |")
    lines += [
        "",
        "Install creates the pack's own environment outside this directory (set `FLYTO_PACK_HOME` to",
        f"choose where) from `{standalone['lockfile']['path']}`, whose every requirement is pinned and",
        "hashed. The server refuses to start unless the pack verifies: pass `--trusted-key ID=FILE` for a",
        "signed pack, or `--allow-unsigned` for one you built yourself. `--revocations FILE` with",
        "`--revocation-key ID=FILE` also checks a signed revocation list first.",
        "",
        "Transports: " + ", ".join(f"`{t}`" for t in standalone["transports"]) + ".",
    ]
    if "streamable_http" in standalone["transports"]:
        lines += [
            "Over Streamable HTTP (`--transport streamable_http --port N`) the server listens on loopback",
            "only, at `/mcp`, and every request needs `Authorization: Bearer <token>`; set the token in",
            "`FLYTO_PACK_HTTP_TOKEN`, or the server makes one and prints it to stderr.",
        ]
    lines += ["", "## Credentials", ""]
    if not standalone["credentials"]:
        lines += ["This pack calls its API without a credential.", ""]
    else:
        lines += [
            "The pack holds credential names, never values. At each call the server reads the value",
            "from the environment variable first, then from the OS keychain"
            + (" (one of them is enough)." if len(standalone["credentials"]) > 1 else "."),
            "",
            "| Credential | Environment variable | Keychain service | Keychain account |",
            "| --- | --- | --- | --- |",
        ]
        for item in standalone["credentials"]:
            lines.append(f"| `{item['name']}` | `{item['env']}` | `{item['keychain']['service']}` | "
                         f"`{item['keychain']['account']}` |")
        lines += ["", "To store one in the keychain:", ""]
        first = standalone["credentials"][0]["keychain"]
        for platform, hint in KEYCHAIN_STORE_HINTS.items():
            lines.append(f"- {platform}: `{hint.format(service=first['service'], account=first['account'])}`")
        lines += ["", "Set `FLYTO_PACK_NO_KEYCHAIN=1` to read the environment only.", ""]
    lines += ["## Tools", ""] + _tool_rows(manifest) + [
        "",
        "## Load it into a Flyto2 Space",
        "",
        "Install this same zip from a file; nothing is published to a marketplace. Each tool above is",
        "a module of the same id in the Space, and the Space supplies the credential by the same name.",
        "",
        "## Verify it",
        "",
        "`flyto pack verify <this zip>` checks the files against `artifact.digest`, the signature, and",
        "a revocation list when one is given.",
        "",
    ]
    if author_readme:
        lines += ["## About this pack", "", author_readme.strip().replace("\r\n", "\n"), ""]
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def render_notice(manifest: Mapping[str, Any], requirements: List[Mapping[str, Any]]) -> bytes:
    """The third-party notice: every distribution the lockfile installs, with its hashes."""
    lines = [
        "# Third-party notices",
        "",
        f"`{manifest['pack']['id']}` {manifest['pack']['version']} installs these distributions from",
        f"`{manifest['standalone']['lockfile']['path']}`, each pinned to one version and checked against",
        "these SHA-256 hashes at install time. Each distribution's license is the one declared in its",
        "own metadata (`pip show <name>` in the pack's environment).",
        "",
    ]
    for item in requirements:
        lines += [f"## {item['name']} {item['version']}", ""]
        if item.get("marker"):
            lines += [f"Installed when: `{item['marker']}`", ""]
        lines += [f"- `{digest}`" for digest in item["hashes"]] + [""]
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


# ---------------------------------------------------------------------------
# Zip
# ---------------------------------------------------------------------------


def _write_file(path: Path, data: bytes, executable: bool) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o755 if executable else 0o644)


def _tree_files(root: Path) -> List[Tuple[str, bytes, bool]]:
    """Every file of a built pack, the manifest and signature included, sorted."""
    files = [(rel, data, bool(mode & stat.S_IXUSR)) for rel, data, mode in _iter_pack_files(root)]
    for name in (MANIFEST_FILENAME, SIGNATURE_FILENAME):
        if (root / name).exists():
            files.append((name, _read_regular_file(root / name, MAX_TREE_BYTES), False))
    return sorted(files)


def write_deterministic_zip(files: List[Tuple[str, bytes, bool]], output: Path) -> None:
    """A deterministic zip: sorted entries, fixed timestamps, fixed permissions; ``output`` must not exist."""
    with open(output, "xb") as handle, zipfile.ZipFile(handle, "w") as archive:
        for rel, data, executable in sorted(files):
            info = zipfile.ZipInfo(rel, date_time=_ZIP_EPOCH)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)


def _zip_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def extract_pack_zip(zip_path: os.PathLike[str] | str, dest: os.PathLike[str] | str, *,
                     required: str = MANIFEST_FILENAME) -> Path:
    """Extract a pack (or bundle) zip into the empty directory ``dest``, refusing anything unsafe.

    Every entry is checked before the first byte is written: a path that
    leaves ``dest`` (absolute, ``..``, a drive, a backslash), a symlink or
    other special entry, an encrypted entry, two names that collide on a
    case-insensitive file system, or a tree beyond the pack bounds. The zip
    must hold ``required`` at its root.
    """
    target = Path(dest)
    try:
        archive = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        _fail("ZIP_INVALID", "the pack is not a readable zip")
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_TREE_FILES + 2:
            _fail("PACK_TOO_LARGE", "the pack zip has too many entries")
        files: List[zipfile.ZipInfo] = []
        seen: Dict[str, str] = {}
        directories = set()
        total = 0
        for info in infos:
            name = info.filename
            is_dir = name.endswith("/")
            bare = name[:-1] if is_dir else name
            parts = bare.split("/")
            if (
                not bare or len(name) > _MAX_ZIP_NAME or name.startswith("/") or "\\" in name or ":" in name
                or "\x00" in name or any(part in ("", ".", "..") for part in parts)
            ):
                _fail("ZIP_UNSAFE_PATH", "a zip entry names a path outside the pack")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                _fail("ZIP_SYMLINK", "the pack zip contains a symbolic link")
            if mode and stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                _fail("ZIP_UNSAFE_PATH", "the pack zip contains a special file")
            if info.flag_bits & 0x1:
                _fail("ZIP_INVALID", "the pack zip contains an encrypted entry")
            key = _zip_key(bare)
            if key in seen and not (is_dir and seen[key] == "dir"):
                _fail("ZIP_DUPLICATE", "two zip entries name the same file")
            seen[key] = "dir" if is_dir else "file"
            for depth in range(1, len(parts)):
                directories.add(_zip_key("/".join(parts[:depth])))
            if is_dir:
                continue
            total += info.file_size
            if info.file_size > MAX_TREE_BYTES or total > MAX_TREE_BYTES:
                _fail("PACK_TOO_LARGE", "the pack zip exceeds the byte limit")
            files.append(info)
        if any(seen.get(directory) == "file" for directory in directories):
            _fail("ZIP_DUPLICATE", "a zip entry is both a file and a directory")
        if required not in {info.filename for info in files}:
            _fail("ZIP_NO_MANIFEST", f"the zip has no {required} at its root")
        for info in files:
            with archive.open(info) as source:
                data = source.read(info.file_size + 1)
            if len(data) != info.file_size:
                _fail("ZIP_INVALID", "a zip entry's size does not match its header")
            executable = bool((info.external_attr >> 16) & stat.S_IXUSR)
            _write_file(target.joinpath(*info.filename.split("/")), data, executable)
    return target


@contextlib.contextmanager
def opened_pack(source: os.PathLike[str] | str, *, required: str = MANIFEST_FILENAME) -> Iterator[Path]:
    """The directory for ``source``: the directory itself, or a private extraction of a zip."""
    path = Path(source)
    if path.is_dir():
        yield path
        return
    if not path.is_file():
        _fail("PACK_UNREADABLE", "the pack is neither a directory nor a file")
    scratch = Path(tempfile.mkdtemp(prefix="flyto-pack-zip-"))
    try:
        extract_pack_zip(path, scratch, required=required)
        yield scratch
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _check_portable_tree(root: Path, manifest: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """A built portable pack has its lockfile and every entry point; returns the lock's requirements."""
    from .supply_chain import parse_lockfile

    standalone = manifest["standalone"]
    if "artifact" not in manifest:
        _fail("PACK_NOT_BUILT", "a portable pack carries artifact.digest; run flyto pack build")
    for platform in PLATFORMS:
        for action in ENTRY_ACTIONS:
            if not (root / GENERATED_DIR / platform / (action + PLATFORMS[platform]["suffix"])).is_file():
                _fail("ENTRY_POINT_MISSING", f"the {platform} {action} entry point is missing")
    lock = root / standalone["lockfile"]["path"]
    if not lock.is_file():
        _fail("LOCKFILE_MISSING", "the pack's lockfile is missing")
    try:
        text = _read_regular_file(lock, 1024 * 1024).decode("utf-8")
    except UnicodeDecodeError:
        _fail("LOCKFILE_INVALID", "the lockfile is not UTF-8")
    return parse_lockfile(text, runtime_package=standalone["runtime"]["package"],
                          min_version=manifest["pack"].get("min_host"))


def verify_pack_dir(
    root: Path,
    *,
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    revocations: Any = None,
    key_rotations: Sequence[Any] = (),
    certification: Any = None,
) -> Dict[str, Any]:
    """Verify one pack directory without installing it; returns what was verified.

    The publisher check is ``install_pack``'s own (``verify_publisher``), and
    so is the certification policy, so what verifies here installs there.
    """
    from .host import _host_version
    from .publisher_keys import verify_publisher
    from .signature import read_signature
    from .supply_chain import pack_digest

    manifest = read_pack_manifest(root)
    # Revocation first: a revoked pack is refused whatever else is true of it.
    if revocations is not None:
        revocations.check(manifest)
    digest = manifest.get("artifact", {}).get("digest")
    if digest is not None and pack_tree_digest(root) != digest:
        _fail("DIGEST_MISMATCH", "pack files do not match artifact.digest")
    requirements = _check_portable_tree(root, manifest) if "standalone" in manifest else None
    signature = verify_publisher(manifest, read_signature(root), trusted_keys=trusted_keys,
                                 require_signature=require_signature, revocations=revocations,
                                 key_rotations=key_rotations)
    certified = certification.check(manifest, host_version=_host_version()) if certification is not None else None
    report: Dict[str, Any] = {
        "pack_id": manifest["pack"]["id"],
        "version": manifest["pack"]["version"],
        "binding": manifest["runtime"]["binding"],
        "artifact_digest": digest,
        "pack_digest": pack_digest(manifest),
        "signature": signature,
        "revocation": (f"checked against list {revocations.sequence} from {revocations.key_id}"
                       if revocations is not None else "no list configured"),
        "module_ids": [row["module_id"] for row in manifest["modules"]],
    }
    if certified is not None:
        report["certification"] = {"certifier_key_id": certified["certifier_key_id"],
                                   "certified_at": certified["certified_at"], "core": certified["core"]}
    if requirements is not None:
        report["standalone"] = {"transports": manifest["standalone"]["transports"],
                                "credentials": [item["name"] for item in manifest["standalone"]["credentials"]],
                                "requirements": [f"{r['name']}=={r['version']}" for r in requirements]}
    return report


def verify_pack(
    source: os.PathLike[str] | str,
    *,
    trusted_keys: Optional[Mapping[str, Any]] = None,
    require_signature: bool = True,
    revocations: Any = None,
    key_rotations: Sequence[Any] = (),
    certification: Any = None,
) -> Dict[str, Any]:
    """Verify a pack directory or zip: digest, signature, revocation, and a portable pack's tree."""
    with opened_pack(source) as root:
        return verify_pack_dir(root, trusted_keys=trusted_keys, require_signature=require_signature,
                               revocations=revocations, key_rotations=key_rotations, certification=certification)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _read_raw_manifest(root: Path) -> Dict[str, Any]:
    from .manifest import MAX_MANIFEST_BYTES, _reject_duplicates

    raw = _read_regular_file(root / MANIFEST_FILENAME, MAX_MANIFEST_BYTES)
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates)


def build_portable_pack(
    source: os.PathLike[str] | str,
    output: os.PathLike[str] | str,
    *,
    lockfile: Optional[os.PathLike[str] | str] = None,
    private_key: Any = None,
    key_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build ``source`` into the portable zip ``output``; returns the build report.

    ``lockfile`` places that file at the path ``standalone.lockfile`` names
    (otherwise the source must already hold it). With ``private_key`` and
    ``key_id`` the manifest is signed. ``output`` must not exist: an update
    is a new version built to a new file, never a change to a built one.
    """
    from .supply_chain import pack_digest, parse_lockfile

    src = Path(source)
    out = Path(output)
    if (private_key is None) != (key_id is None):
        _fail("INVALID_KEY", "signing needs both a key and a key id")
    if os.path.lexists(out):
        _fail("OUTPUT_EXISTS", "the output file exists; a new build is a new version in a new file")
    manifest = read_pack_manifest(src)
    if "standalone" not in manifest:
        _fail("STANDALONE_MISSING", "a portable pack declares a standalone section")
    raw = _read_raw_manifest(src)
    raw.pop("artifact", None)
    standalone = manifest["standalone"]
    lock_rel = standalone["lockfile"]["path"]

    with tempfile.TemporaryDirectory(prefix="flyto-pack-build-") as scratch:
        stage = Path(scratch) / "pack"
        stage.mkdir(mode=0o700)
        author_readme: Optional[str] = None
        for rel, data, mode in _iter_pack_files(src):
            if _reserved(rel):
                _fail("RESERVED_PATH", f"the source holds {rel}, a path the build writes")
            if rel == README_FILENAME:
                author_readme = data.decode("utf-8", "replace")
                continue
            if rel == lock_rel and lockfile is not None:
                continue
            _write_file(stage.joinpath(*rel.split("/")), data, bool(mode & stat.S_IXUSR))
        if lockfile is not None:
            _write_file(stage.joinpath(*lock_rel.split("/")),
                        _read_regular_file(Path(lockfile), 1024 * 1024), False)
        lock_path = stage.joinpath(*lock_rel.split("/"))
        if not lock_path.is_file():
            _fail("LOCKFILE_MISSING", f"the pack needs {lock_rel} (pass --lock FILE)")
        try:
            lock_text = lock_path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            _fail("LOCKFILE_INVALID", "the lockfile is not UTF-8")
        requirements = parse_lockfile(lock_text, runtime_package=standalone["runtime"]["package"],
                                      min_version=manifest["pack"].get("min_host"))

        for platform in PLATFORMS:
            for action in ENTRY_ACTIONS:
                rel = "/".join((GENERATED_DIR, platform, action + PLATFORMS[platform]["suffix"]))
                _write_file(stage.joinpath(*rel.split("/")), render_script(platform, action, manifest),
                            PLATFORMS[platform]["dialect"] == "posix")
        _write_file(stage / README_FILENAME, render_readme(manifest, author_readme), False)
        _write_file(stage / NOTICE_FILENAME, render_notice(manifest, requirements), False)

        raw["artifact"] = {"digest": pack_tree_digest(stage)}
        normalized = validate_pack_manifest(raw)
        (stage / MANIFEST_FILENAME).write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
        trusted = None
        if private_key is not None:
            from .signature import sign_manifest

            signature = sign_manifest(normalized, private_key, key_id)
            (stage / SIGNATURE_FILENAME).write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")
            trusted = {key_id: private_key.public_key()}
        # What was built is verified as a host would verify it, before it is written out.
        verified = verify_pack_dir(stage, trusted_keys=trusted, require_signature=private_key is not None)
        write_deterministic_zip(_tree_files(stage), out)

    return {
        "pack_id": normalized["pack"]["id"],
        "version": normalized["pack"]["version"],
        "zip": str(out),
        "zip_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "artifact_digest": normalized["artifact"]["digest"],
        "pack_digest": pack_digest(normalized),
        "signed": private_key is not None,
        "transports": standalone["transports"],
        "requirements": verified["standalone"]["requirements"],
    }
