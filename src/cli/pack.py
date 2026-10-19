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

    verify_p = sub.add_parser("verify", help="Validate, digest-check and signature-check a pack (installs nothing)")
    verify_p.add_argument("pack_dir")
    verify_p.add_argument("--trusted-key", action="append", default=[], metavar="ID=FILE",
                          help="Trusted publisher public key (PEM or base64 raw); repeatable")
    verify_p.add_argument("--allow-unsigned", action="store_true", help="Accept a pack with no signature")

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


def _verify(args) -> int:
    from core.pack.manifest import pack_tree_digest, read_pack_manifest
    from core.pack.signature import read_signature, verify_manifest_signature

    manifest = read_pack_manifest(args.pack_dir)
    digest = manifest.get("artifact", {}).get("digest")
    if digest is not None and pack_tree_digest(args.pack_dir) != digest:
        print("error: pack files do not match artifact.digest", file=sys.stderr)
        return 1
    signature_doc = read_signature(args.pack_dir)
    signature = None
    if signature_doc is not None:
        signature = verify_manifest_signature(manifest, signature_doc, _trusted_keys(args.trusted_key))
    elif not args.allow_unsigned:
        print("error: pack is not signed (pass --allow-unsigned to accept it)", file=sys.stderr)
        return 1
    print(json.dumps({
        "pack_id": manifest["pack"]["id"],
        "version": manifest["pack"]["version"],
        "binding": manifest["runtime"]["binding"],
        "artifact_digest": digest,
        "signature": signature,
        "module_ids": [row["module_id"] for row in manifest["modules"]],
    }, indent=2))
    return 0


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
    }
    if action not in handlers:
        print("Usage: flyto pack <manifest|digest|keygen|sign|verify|conform|import-openapi>")
        return 1
    try:
        return handlers[action](args)
    except PackManifestError as exc:
        print(f"error [{exc.code}]: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
