"""
Pack CLI Commands — the language-neutral ``flyto.pack.v1`` contract.

Usage:
    flyto pack init <dir> [--openapi FILE] [--pack-id ID] [--namespace NS] [--probe OPERATION]
    flyto pack consequence <pack-dir> OPERATION=LEVEL [OPERATION=LEVEL ...]
    flyto pack doctor <pack-dir> [--json]
    flyto pack test <pack-dir> [--json]
    flyto pack manifest <entry-point|module:callable> [--pack-id ID] [--version V] [-o FILE]
    flyto pack digest <pack-dir>
    flyto pack keygen --private FILE --public FILE
    flyto pack sign <pack-dir> --key PRIVATE_PEM --key-id ID
    flyto pack verify <pack-dir> [--trusted-key ID=PUBLIC_KEY_FILE ...] [--allow-unsigned]
    flyto pack conform <pack-dir> [--trusted-key ID=PUBLIC_KEY_FILE ...] [--static-only] [--json]
    flyto pack import-openapi <openapi.json|yaml> [-o FILE]
    flyto pack build <pack-dir> [-o ZIP] [--lock FILE] [--key PRIVATE_PEM --key-id ID]
    flyto pack verify <pack-dir|zip> [...] [--revocations FILE --revocation-key ID=FILE ...]
    flyto pack run <pack-dir|zip> [--transport stdio|streamable_http] [--port N] [trust options] [--provider-base-url URL]
    flyto pack health <pack-dir|zip> [trust options] [--provider-base-url URL]
    flyto pack serve-fixtures <pack-dir> [--port N]
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

    init_p = sub.add_parser(
        "init", help="Scaffold a pack: a connector or a device adapter, with a test (every consequence unset)"
    )
    init_p.add_argument("pack_dir", help="New or empty directory to write the pack into")
    init_p.add_argument("--template", choices=("connector", "device-adapter"), default="connector",
                        help="connector: a provider API (default); device-adapter: a module pack with capability "
                             "contracts, served over JSON-RPC on stdio against a simulated device")
    init_p.add_argument("--openapi", help="Draft the operations from this OpenAPI 3 document (JSON or YAML)")
    init_p.add_argument("--pack-id", help="Pack id (default: com.example.<directory name>)")
    init_p.add_argument("--namespace", help="Module namespace (default: the last part of the pack id)")
    init_p.add_argument("--probe", help="The operation that reads what the account holds (entitlements.probe)")

    consequence_p = sub.add_parser(
        "consequence", help="Record your decision of what each operation does to the world"
    )
    consequence_p.add_argument("pack_dir")
    consequence_p.add_argument("decisions", nargs="+", metavar="TARGET=LEVEL",
                               help="observe, reversible, external_write, real_world or irreversible")

    doctor_p = sub.add_parser("doctor", help="Explain every validation refusal: its cause and its fix")
    doctor_p.add_argument("pack_dir")
    doctor_p.add_argument("--json", action="store_true", help="Print the diagnoses as JSON")

    test_p = sub.add_parser(
        "test", help="Run each operation against the recorded fixtures through the real runtime, then conform"
    )
    test_p.add_argument("pack_dir")
    test_p.add_argument("--json", action="store_true", help="Print the report as JSON")

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
    _add_maintenance_arguments(verify_p)

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
    _add_maintenance_arguments(run_p)
    _add_provider_argument(run_p)

    health_p = sub.add_parser("health", help="Healthcheck a portable pack: verify, runtime, credential names")
    health_p.add_argument("source", help="Pack directory or built zip")
    _add_trust_arguments(health_p)
    _add_maintenance_arguments(health_p)
    _add_provider_argument(health_p)

    certify_p = sub.add_parser(
        "certify", help="Run verify, compatibility, conform, pack test and standalone health; sign a "
                        "certification record when every check passes"
    )
    certify_p.add_argument("source", help="Built pack zip (or a signed pack directory)")
    certify_p.add_argument("--key", required=True, help="Certifier ed25519 private key (PEM)")
    certify_p.add_argument("--key-id", required=True, help="Certifier key id")
    certify_p.add_argument("-o", "--output", help="Record to write (default: <pack id>-<version>.certification.json)")
    certify_p.add_argument("--json", action="store_true", help="Print the whole report as JSON")
    _add_trust_arguments(certify_p)
    certify_p.add_argument("--key-rotation", action="append", default=[], metavar="FILE",
                           help="Publisher key rotation statement (flyto.publisher-key-rotation.v1); repeatable")

    matrix_p = sub.add_parser("matrix", help="Print the pack feature x flyto-core version matrix")
    matrix_p.add_argument("--json", action="store_true", help="Print it as JSON (flyto.pack-compatibility-matrix.v1)")
    matrix_p.add_argument("--certification", action="append", default=[], metavar="FILE",
                          help="Certification record to list (verified with --certifier-key); repeatable")
    matrix_p.add_argument("--certifier-key", action="append", default=[], metavar="ID=FILE",
                          help="Public key trusted to sign certification records; repeatable")

    rotate_p = sub.add_parser("rotate-key", help="Sign a publisher key rotation statement with the old key")
    rotate_p.add_argument("--key", required=True, help="The old publisher private key (PEM)")
    rotate_p.add_argument("--key-id", required=True, help="The old publisher key id")
    rotate_p.add_argument("--new-public", required=True, help="The new publisher public key (PEM)")
    rotate_p.add_argument("--new-key-id", required=True, help="The new publisher key id")
    rotate_p.add_argument("-o", "--output", required=True, help="Statement to write; must not exist")

    fixtures_p = sub.add_parser(
        "serve-fixtures", help="Serve a pack's recorded fixtures as a local provider stand-in (loopback only)"
    )
    fixtures_p.add_argument("pack_dir", help="Pack source directory holding fixtures/exchanges.json")
    fixtures_p.add_argument("--port", type=int, default=0, help="Port on 127.0.0.1 (0 picks one)")

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


def _add_maintenance_arguments(parser) -> None:
    parser.add_argument("--key-rotation", action="append", default=[], metavar="FILE",
                        help="Publisher key rotation statement (flyto.publisher-key-rotation.v1); repeatable")
    parser.add_argument("--certification-policy", metavar="FILE",
                        help="Certification policy table (flyto.pack-certification-policy.v1)")
    parser.add_argument("--certifier-key", action="append", default=[], metavar="ID=FILE",
                        help="Public key trusted to sign certification records; repeatable")
    parser.add_argument("--certification", action="append", default=[], metavar="FILE",
                        help="Certification record (flyto.pack-certification.v1); repeatable")


def _add_provider_argument(parser) -> None:
    parser.add_argument("--provider-base-url", metavar="URL",
                        help="Send the pack's requests here instead of its manifest base_url, for local testing: "
                             "a loopback address (such as flyto pack serve-fixtures) or a host in FLYTO_ALLOWED_HOSTS")


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


def _read_documents(paths):
    return [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths or ()]


def _certification(args):
    """The certification gate the arguments name, or ``None`` when no policy is given."""
    path = getattr(args, "certification_policy", None)
    if not path:
        if getattr(args, "certification", None):
            raise ValueError("--certification needs --certification-policy")
        return None
    from core.pack.certification import load_certification_policy

    return load_certification_policy(json.loads(Path(path).read_text(encoding="utf-8")),
                                     _trusted_keys(getattr(args, "certifier_key", None) or []),
                                     records=_read_documents(getattr(args, "certification", None)))


def _trust(args):
    trust = {
        "trusted_keys": _trusted_keys(getattr(args, "trusted_key", None) or []),
        "require_signature": not getattr(args, "allow_unsigned", False),
        "revocations": _revocations(args),
    }
    if hasattr(args, "certification_policy"):
        trust["key_rotations"] = _read_documents(args.key_rotation)
        trust["certification"] = _certification(args)
    return trust


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

    pack = load_standalone(args.source, transport=args.transport, provider_base_url=getattr(args, "provider_base_url", None),
                           **_trust(args))

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

    report = health(args.source, provider_base_url=getattr(args, "provider_base_url", None), **_trust(args))
    print(json.dumps(report, indent=2))
    return 0 if report["healthy"] else 1


def _serve_fixtures(args) -> int:
    import threading

    from core.pack.recorded import serve_fixtures

    with serve_fixtures(args.pack_dir, port=args.port) as url:
        print(f"serving recorded fixtures at {url}", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            return 0
    return 0


def _conform(args) -> int:
    from core.pack.conformance import conform, render

    report = conform(args.pack_dir, trusted_keys=_trusted_keys(args.trusted_key), run=not args.static_only)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report))
    return 0 if report["conformant"] else 1


def _certify(args) -> int:
    from core.pack.certification import certify

    trust = _trust(args)
    key, key_id = _private_key(args)
    report = certify(args.source, private_key=key, key_id=key_id, key_rotations=_read_documents(args.key_rotation),
                     **trust)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["results"]:
            print(f"  [{item['verdict']:<14}] {item['check']:<18} {item['detail']}")
    if report["record"] is None:
        print("not certified: every applicable check must pass", file=sys.stderr)
        return 1
    output = args.output or f"{report['pack']['id']}-{report['pack']['version']}.certification.json"
    with open(output, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(report["record"], indent=2) + "\n")
    print(f"certified {report['pack']['id']} {report['pack']['version']} ({report['pack_digest']}) as {key_id}: "
          f"{output}", file=sys.stderr)
    return 0


def _matrix(args) -> int:
    from core.pack.certification import verify_certification
    from core.pack.compatibility import compatibility_matrix, render_matrix_markdown

    keys = _trusted_keys(args.certifier_key)
    bodies = [verify_certification(document, keys) for document in _read_documents(args.certification)]
    matrix = compatibility_matrix(bodies)
    print(json.dumps(matrix, indent=2) if args.json else render_matrix_markdown(matrix), end="" if not args.json
          else "\n")
    return 0


def _rotate_key(args) -> int:
    from datetime import datetime, timezone

    from core.pack.publisher_keys import sign_key_rotation
    from core.pack.signature import load_public_key

    key, key_id = _private_key(args)
    issued = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    statement = sign_key_rotation(key, key_id, load_public_key(Path(args.new_public).read_text(encoding="utf-8")),
                                  args.new_key_id, issued_at=issued)
    with open(args.output, "x", encoding="utf-8") as handle:
        handle.write(json.dumps(statement, indent=2) + "\n")
    print(f"wrote {args.output}: {key_id} -> {args.new_key_id}")
    return 0


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


def _init(args) -> int:
    from core.pack.scaffold import init_pack

    report = init_pack(args.pack_dir, openapi=args.openapi, pack_id=args.pack_id, namespace=args.namespace,
                       probe=args.probe, template=args.template)
    print(json.dumps(report, indent=2))
    print(f"decide each consequence: flyto pack consequence {args.pack_dir} "
          + " ".join(f"{op}=LEVEL" for op in report["undecided"]), file=sys.stderr)
    return 0


def _consequence(args) -> int:
    from core.pack.scaffold import decide_consequences, parse_decisions

    report = decide_consequences(args.pack_dir, parse_decisions(args.decisions))
    print(json.dumps(report, indent=2))
    if report["undecided"]:
        print(f"still undecided: {', '.join(report['undecided'])}", file=sys.stderr)
    return 0


def _doctor(args) -> int:
    from core.pack.doctor import diagnose, render

    report = diagnose(args.pack_dir)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["valid"] else 1


def _test(args) -> int:
    from core.pack.recorded import render, run_pack_tests

    report = run_pack_tests(args.pack_dir)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report))
    return 0 if report["passed"] else 1


def run_pack_command(args) -> int:
    """Execute a pack subcommand."""
    from core.pack.manifest import PackManifestError

    action = getattr(args, "pack_action", None)
    handlers = {
        "init": _init,
        "consequence": _consequence,
        "doctor": _doctor,
        "test": _test,
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
        "serve-fixtures": _serve_fixtures,
        "certify": _certify,
        "matrix": _matrix,
        "rotate-key": _rotate_key,
    }
    if action not in handlers:
        print("Usage: flyto pack <" + "|".join(handlers) + ">")
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
