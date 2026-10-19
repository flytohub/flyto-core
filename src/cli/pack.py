"""
Pack CLI Commands — the language-neutral ``flyto.pack.v1`` contract.

Usage:
    flyto pack manifest <entry-point|module:callable> [--pack-id ID] [--version V] [-o FILE]
    flyto pack digest <pack-dir>
    flyto pack keygen --private FILE --public FILE
    flyto pack sign <pack-dir> --key PRIVATE_PEM --key-id ID
    flyto pack verify <pack-dir> [--trusted-key ID=PUBLIC_KEY_FILE ...] [--allow-unsigned]
    flyto pack conform <pack-dir> [--trusted-key ID=PUBLIC_KEY_FILE ...] [--static-only] [--json]
    flyto pack import-openapi <openapi.json|yaml> [-o FILE]
    flyto pack build <pack-dir> [-o ZIP] [--lock FILE] [--key PRIVATE_PEM --key-id ID]
    flyto pack verify <pack-dir|zip> [...] [--revocations FILE --revocation-key ID=FILE ...]
    flyto pack run <pack-dir|zip> [--transport stdio|streamable_http] [--port N] [trust options]
    flyto pack health <pack-dir|zip> [trust options]
    flyto bundle build <bundle-dir> --pack ZIP ... [-o ZIP] [--key PRIVATE_PEM --key-id ID]
    flyto bundle verify <bundle-dir|zip> --pack ZIP ... [trust options]
"""

import json
import sys
from pathlib import Path


def add_pack_parser(subparsers) -> None:
    """Add the ``pack`` subcommand to the CLI."""
    pack_parser = subparsers.add_parser(
        "pack",
        help="Language-neutral module packs (flyto.pack.v1)",
        description="Export, sign and verify flyto.pack.v1 module pack manifests.",
    )
    sub = pack_parser.add_subparsers(dest="pack_action", help="Pack actions")

    manifest_p = sub.add_parser("manifest", help="Print the manifest a Python pack's decorators produce")
    manifest_p.add_argument("target", help="flyto.modules entry point name, or package.module:register_all")
    manifest_p.add_argument("--pack-id", help="Pack id (default: the entry point name)")
    manifest_p.add_argument("--version", help="Pack version (default: the distribution version)")
    manifest_p.add_argument("--description", help="Pack description")
    manifest_p.add_argument("-o", "--output", help="Write to this file instead of stdout")

    digest_p = sub.add_parser("digest", help="Print the tree digest of a pack directory")
    digest_p.add_argument("pack_dir")

    keygen_p = sub.add_parser("keygen", help="Generate an ed25519 publisher key pair")
    keygen_p.add_argument("--private", required=True, help="Private key output (PEM, mode 0600)")
    keygen_p.add_argument("--public", required=True, help="Public key output (PEM)")

    sign_p = sub.add_parser("sign", help="Set artifact.digest and write flyto-pack.sig.json")
    sign_p.add_argument("pack_dir")
    sign_p.add_argument("--key", required=True, help="ed25519 private key (PEM)")
    sign_p.add_argument("--key-id", required=True, help="Publisher key id")

    verify_p = sub.add_parser(
        "verify", help="Validate a pack directory or zip: digest, signature, revocation (installs nothing)"
    )
    verify_p.add_argument("pack_dir", help="Pack directory or built zip")
    _add_trust_arguments(verify_p)

    build_p = sub.add_parser(
        "build", help="Build a portable pack zip: validate, generate entry points, README and notice, sign"
    )
    build_p.add_argument("pack_dir")
    build_p.add_argument("-o", "--output", help="Zip to write (default: <pack id>-<version>.zip); must not exist")
    build_p.add_argument("--lock", help="Hashed lockfile to place at standalone.lockfile")
    build_p.add_argument("--key", help="ed25519 private key (PEM) to sign with")
    build_p.add_argument("--key-id", help="Publisher key id (with --key)")

    run_p = sub.add_parser("run", help="Run a portable pack on its own as an MCP server")
    run_p.add_argument("source", help="Pack directory or built zip")
    run_p.add_argument("--transport", choices=("stdio", "streamable_http"), default="stdio")
    run_p.add_argument("--host", default="127.0.0.1", help="Loopback address for streamable_http")
    run_p.add_argument("--port", type=int, default=8765, help="Port for streamable_http (0 picks one)")
    _add_trust_arguments(run_p)

    health_p = sub.add_parser("health", help="Healthcheck a portable pack: verify, runtime, credential names")
    health_p.add_argument("source", help="Pack directory or built zip")
    _add_trust_arguments(health_p)

    conform_p = sub.add_parser(
        "conform",
        help="Offline conformance: static checks, then the pack's runner (run it against a simulator)",
    )
    conform_p.add_argument("pack_dir")
    conform_p.add_argument("--trusted-key", action="append", default=[], metavar="ID=FILE",
                           help="Trusted publisher public key (PEM or base64 raw); repeatable")
    conform_p.add_argument("--static-only", action="store_true", help="Read the files; never start the runner")
    conform_p.add_argument("--json", action="store_true", help="Print the report as JSON")

    import_p = sub.add_parser(
        "import-openapi",
        help="Draft a connector section from an OpenAPI 3 document (every consequence left for you to set)",
    )
    import_p.add_argument("document", help="OpenAPI 3 document, JSON or YAML")
    import_p.add_argument("-o", "--output", help="Write the draft to this file instead of stdout")


def _add_trust_arguments(parser) -> None:
    parser.add_argument("--trusted-key", action="append", default=[], metavar="ID=FILE",
                        help="Trusted publisher public key (PEM or base64 raw); repeatable")
    parser.add_argument("--allow-unsigned", action="store_true", help="Accept a pack with no signature")
    parser.add_argument("--revocations", help="Signed revocation list (flyto.pack-revocations.v1) to check first")
    parser.add_argument("--revocation-key", action="append", default=[], metavar="ID=FILE",
                        help="Public key trusted to sign the revocation list; repeatable")


def add_bundle_parser(subparsers) -> None:
    """Add the ``bundle`` subcommand: packs by pinned digest, plus workflows and templates."""
    bundle_parser = subparsers.add_parser(
        "bundle",
        help="Bundles (flyto.bundle.v1): packs pinned by digest, workflows, templates",
        description="Build and verify flyto.bundle.v1 bundles. A bundle references packs; it never copies one.",
    )
    sub = bundle_parser.add_subparsers(dest="bundle_action", help="Bundle actions")
    build_p = sub.add_parser("build", help="Pin the packs and file digests, validate, and write a bundle zip")
    build_p.add_argument("source", help="Bundle directory holding flyto-bundle.json")
    build_p.add_argument("--pack", action="append", default=[], help="A referenced pack (zip or directory)")
    build_p.add_argument("-o", "--output", help="Zip to write (default: <bundle id>-<version>.bundle.zip)")
    build_p.add_argument("--key", help="ed25519 private key (PEM) to sign with")
    build_p.add_argument("--key-id", help="Publisher key id (with --key)")
    build_p.add_argument("--trusted-key", action="append", default=[], metavar="ID=FILE",
                         help="Trusted publisher key for the referenced packs; repeatable")
    build_p.add_argument("--allow-unsigned", action="store_true", help="Accept unsigned referenced packs")
    verify_p = sub.add_parser("verify", help="Verify a bundle against the packs it pins")
    verify_p.add_argument("source", help="Bundle directory or zip")
    verify_p.add_argument("--pack", action="append", default=[], help="A referenced pack (zip or directory)")
    _add_trust_arguments(verify_p)


def _trusted_keys(pairs):
    keys = {}
    for pair in pairs:
        key_id, sep, path = pair.partition("=")
        if not sep or not key_id or not path:
            raise ValueError("--trusted-key must be ID=FILE")
        keys[key_id] = Path(path).read_text(encoding="utf-8")
    return keys


def _manifest(args) -> int:
    from core.pack.export import export_python_pack

    manifest = export_python_pack(
        args.target, pack_id=args.pack_id, version=args.version, description=args.description
    )
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


def _digest(args) -> int:
    from core.pack.manifest import pack_tree_digest

    print(pack_tree_digest(args.pack_dir))
    return 0


def _keygen(args) -> int:
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    fd = os.open(args.private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(private)
    Path(args.public).write_bytes(public)
    print(f"wrote {args.private} (private) and {args.public} (public)")
    return 0


def _sign(args) -> int:
    from cryptography.hazmat.primitives import serialization

    from core.pack.manifest import (
        MANIFEST_FILENAME,
        SIGNATURE_FILENAME,
        pack_tree_digest,
        validate_pack_manifest,
    )
    from core.pack.signature import sign_manifest

    pack_dir = Path(args.pack_dir)
    path = pack_dir / MANIFEST_FILENAME
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["artifact"] = {"digest": pack_tree_digest(pack_dir)}
    manifest = validate_pack_manifest(raw)
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    key = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
    signature = sign_manifest(manifest, key, args.key_id)
    (pack_dir / SIGNATURE_FILENAME).write_text(json.dumps(signature, indent=2) + "\n", encoding="utf-8")
    print(f"signed {manifest['pack']['id']} {manifest['pack']['version']} with {args.key_id}: "
          f"{raw['artifact']['digest']}")
    return 0


def _revocations(args):
    """The verified revocation list the arguments name, or ``None``."""
    path = getattr(args, "revocations", None)
    if not path:
        return None
    from core.pack.supply_chain import read_revocations

    return read_revocations(path, _trusted_keys(getattr(args, "revocation_key", None) or []))


def _trust(args):
    return {
        "trusted_keys": _trusted_keys(getattr(args, "trusted_key", None) or []),
        "require_signature": not getattr(args, "allow_unsigned", False),
        "revocations": _revocations(args),
    }


def _verify(args) -> int:
    from core.pack.portable import verify_pack

    print(json.dumps(verify_pack(args.pack_dir, **_trust(args)), indent=2))
    return 0


def _private_key(args):
    if not getattr(args, "key", None):
        return None, None
    from cryptography.hazmat.primitives import serialization

    if not args.key_id:
        raise ValueError("--key needs --key-id")
    return serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None), args.key_id


def _build(args) -> int:
    from core.pack.manifest import read_pack_manifest
    from core.pack.portable import build_portable_pack

    output = args.output
    if not output:
        pack = read_pack_manifest(args.pack_dir)["pack"]
        output = f"{pack['id']}-{pack['version']}.zip"
    key, key_id = _private_key(args)
    report = build_portable_pack(args.pack_dir, output, lockfile=args.lock, private_key=key, key_id=key_id)
    print(json.dumps(report, indent=2))
    return 0


def _run(args) -> int:
    import asyncio
    import os
    import secrets

    from core.pack.standalone import load_standalone, serve_http, serve_stdio

    pack = load_standalone(args.source, transport=args.transport, **_trust(args))

    async def serve() -> None:
        try:
            if args.transport == "stdio":
                await serve_stdio(pack)
            else:
                token = os.environ.get("FLYTO_PACK_HTTP_TOKEN")
                if not token:
                    token = secrets.token_urlsafe(32)
                    print(f"bearer token for this run: {token}", file=sys.stderr, flush=True)
                await serve_http(pack, host=args.host, port=args.port, token=token)
        finally:
            await pack.close()

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        return 0
    return 0


def _health(args) -> int:
    from core.pack.standalone import health

    report = health(args.source, **_trust(args))
    print(json.dumps(report, indent=2))
    return 0 if report["healthy"] else 1


def _conform(args) -> int:
    from core.pack.conformance import conform, render

    report = conform(args.pack_dir, trusted_keys=_trusted_keys(args.trusted_key), run=not args.static_only)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report))
    return 0 if report["conformant"] else 1


def _import_openapi(args) -> int:
    import yaml

    from core.pack.openapi import import_openapi

    text = Path(args.document).read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    draft = import_openapi(document)
    output = json.dumps(draft, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    undecided = sum(1 for item in draft["unmapped"] if item["where"].endswith(".consequence"))
    print(f"{len(draft['connector']['operations'])} operations drafted; {undecided} consequences to decide; "
          f"{len(draft['unmapped']) - undecided} other items not mapped", file=sys.stderr)
    return 0


def run_pack_command(args) -> int:
    """Execute a pack subcommand."""
    from core.pack.manifest import PackManifestError

    action = getattr(args, "pack_action", None)
    handlers = {
        "manifest": _manifest,
        "digest": _digest,
        "keygen": _keygen,
        "sign": _sign,
        "verify": _verify,
        "conform": _conform,
        "import-openapi": _import_openapi,
        "build": _build,
        "run": _run,
        "health": _health,
    }
    if action not in handlers:
        print("Usage: flyto pack <manifest|digest|keygen|sign|verify|conform|import-openapi|build|run|health>")
        return 1
    try:
        return handlers[action](args)
    except PackManifestError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _bundle_build(args) -> int:
    from core.pack.bundle import BUNDLE_FILENAME, build_bundle

    output = args.output
    if not output:
        header = json.loads((Path(args.source) / BUNDLE_FILENAME).read_text(encoding="utf-8"))["bundle"]
        output = f"{header['id']}-{header['version']}.bundle.zip"
    key, key_id = _private_key(args)
    report = build_bundle(args.source, output, packs=args.pack, trusted_keys=_trusted_keys(args.trusted_key),
                          require_signature=not args.allow_unsigned, private_key=key, key_id=key_id)
    print(json.dumps(report, indent=2))
    return 0


def _bundle_verify(args) -> int:
    from core.pack.bundle import verify_bundle

    trust = _trust(args)
    report = verify_bundle(args.source, packs=args.pack, require_bundle_signature=trust["require_signature"], **trust)
    print(json.dumps(report, indent=2))
    return 0


def run_bundle_command(args) -> int:
    """Execute a bundle subcommand."""
    from core.pack.manifest import PackManifestError

    handlers = {"build": _bundle_build, "verify": _bundle_verify}
    action = getattr(args, "bundle_action", None)
    if action not in handlers:
        print("Usage: flyto bundle <build|verify>")
        return 1
    try:
        return handlers[action](args)
    except PackManifestError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
