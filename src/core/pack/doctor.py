# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""``flyto pack doctor``: every refusal code, with its cause and its fix.

:data:`DIAGNOSES` is the one table: code -> what it means and what to do.
It covers every code pack validation and verification can raise (manifest,
connector, pre-check sections, standalone, supply chain, signature, bundle,
install), every typed failure ``flyto pack test`` reports, and the scaffold
commands' own refusals. A test reads the pack sources and fails when a code
has no row, or a row names a code nothing raises.

:func:`diagnose` validates a pack directory. A validation stops at its first
refusal; for a connector pack the doctor then also checks each operation on
its own, so the author sees every operation that needs work in one pass.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .manifest import PackManifestError, read_pack_manifest

__all__ = ["DIAGNOSES", "UNLISTED", "Diagnosis", "diagnose", "explain", "render"]


@dataclass(frozen=True)
class Diagnosis:
    cause: str
    fix: str


D = Diagnosis

#: Every refusal and failure code -> its cause and fix.
DIAGNOSES: Mapping[str, Diagnosis] = {
    # -- reading the manifest -------------------------------------------------------------
    "FILE_UNREADABLE": D("A pack file, usually flyto-pack.json, is missing, a symlink, or unreadable.",
                         "Run the command on the pack directory itself, and make flyto-pack.json a regular file there."),
    "FILE_INVALID": D("A pack file is not a regular file, or it is larger than the bound.",
                      "Replace it with a regular file under the size bound; packs carry no devices or pipes."),
    "INVALID_JSON": D("flyto-pack.json (or a bundle document) is not valid UTF-8 JSON.",
                      "Fix the JSON syntax; a JSON linter shows the line."),
    "DUPLICATE_KEY": D("A JSON object in the manifest names the same key twice.",
                       "Keep one copy of the key; JSON readers disagree on which duplicate wins."),
    "MANIFEST_TOO_LARGE": D("The manifest is larger than 2 MiB.",
                            "Split the API into several packs, or drop long descriptions."),
    "MANIFEST_TOO_COMPLEX": D("The manifest has more JSON nodes than the bound.",
                              "Declare fewer operations or inputs per pack."),
    "MANIFEST_TOO_DEEP": D("The manifest nests deeper than the bound.", "Flatten deeply nested schemas."),
    "INVALID_VALUE": D("The manifest holds a non-finite number (NaN or infinity).", "Use a finite number."),
    "INVALID_TEXT": D("A text value has a control, bidi or zero-width character, or is too long.",
                      "Remove the hidden character or shorten the text; only tab and newline are allowed."),
    "INVALID_KEY": D("A manifest key has a hidden character, or a signing or trusted key cannot be read.",
                     "Fix the key name; for signing pass both --key and --key-id; a trusted key is a PEM public key."),
    "INVALID_MAPPING": D("A mapping in the manifest could not be read.", "Write it as a plain JSON object."),
    "INVALID_TYPE": D("The manifest holds something that is not JSON.", "Write the manifest as plain JSON."),
    "UNSUPPORTED_SCHEMA": D("The document's schema is not the one this command reads.",
                            "Set \"schema\" to flyto.pack.v1 for a pack, or flyto.bundle.v1 for a bundle."),
    "UNKNOWN_KEY": D("A section has a key the format does not define.",
                     "Remove or rename the key; the message names the section. Unknown keys are refused, not ignored."),
    "MISSING_FIELD": D("A required field is absent.", "Add the field the message names."),
    "INVALID_OBJECT": D("A section that must be an object is something else.", "Write it as a JSON object."),
    "INVALID_FIELD": D("A field has the wrong type or form.", "Give it the type the spec states for it."),
    "INVALID_BOOLEAN": D("A flag is not a JSON boolean.", "Write true or false, not \"yes\", 1 or a string."),
    "INVALID_BOUND": D("A number is outside its allowed range.", "Use a value inside the range the spec states."),
    # -- pack header and runtime ------------------------------------------------------------
    "INVALID_PACK_ID": D("pack.id is not a lowercase identifier.",
                         "Use a reverse-domain id such as com.example.items (lowercase, dots or dashes)."),
    "INVALID_SEMVER": D("A version is not semver.", "Write MAJOR.MINOR.PATCH, such as 0.1.0."),
    "INVALID_NAMESPACE": D("A namespace is invalid or reserved, or a connector pack has more than one.",
                           "Use one lowercase namespace no flyto-core module uses; it prefixes every module id."),
    "INVALID_RUNTIME": D("runtime is missing a key its binding needs, or names an unsupported binding.",
                         "For a provider API set runtime.binding to connector; other bindings need entry or locality."),
    "INVALID_DIGEST": D("A digest is not lowercase sha256:<hex>.",
                        "Let the tools write it: flyto pack build or flyto pack sign sets artifact.digest."),
    "INVALID_COUNT": D("A list has no entries or too many (operations, modules).",
                       "Declare at least one operation, and at most 256."),
    "DUPLICATE_ID": D("Two operations, modules, features or scopes share an id.", "Give each one a unique id."),
    "INVALID_MODULE_ID": D("A module id is not namespace.name in lowercase.", "Rename it to namespace.name."),
    "MODULE_NAMESPACE_MISMATCH": D("A module id is outside the pack's namespaces.",
                                   "Prefix it with a namespace from pack.namespaces."),
    "INVALID_PARAMS_SCHEMA": D("A params_schema entry has an invalid name or no type.",
                               "Give every parameter a valid name and a JSON-schema type."),
    "INVALID_CAPABILITY": D("provides_capability is not an identifier.", "Use a lowercase dotted capability id."),
    "INVALID_CONTRACT": D("A module contract is not a valid flyto.capability-contract.v1.",
                          "Fix the contract per docs/CAPABILITY_CONTRACT.md; it also needs provides_capability."),
    # -- the connector section -------------------------------------------------------------------
    "CONNECTOR_REQUIRED": D("runtime.binding is connector, but there is no connector section.",
                            "Add a connector section, or start from a scaffold: flyto pack init DIR."),
    "CONNECTOR_BINDING": D("A connector, entitlements or scopes section is on a pack that is not a connector.",
                           "Set runtime.binding to connector, or remove the section."),
    "MODULES_DERIVED": D("A connector pack also lists modules; they are derived from its operations.",
                         "Remove the modules list; each operation becomes the module <namespace>.<operation id>."),
    "INVALID_CONNECTOR": D("A connector entry has the wrong shape: method, path, input, header or bound.",
                           "Fix the entry the message names; the connector section of PACK_MANIFEST_SPEC.md shows each."),
    "INVALID_BASE_URL": D("connector.base_url (or a token URL) is not https://host[/path].",
                          "Use https; http only to a loopback host while developing; no query or fragment."),
    "INLINE_SECRET": D("The manifest carries a credential value: in auth, a default, or a URL.",
                       "Name the credential in auth (\"credential\": \"name\"); the host supplies the value at call time."),
    "UNKNOWN_AUTH_KIND": D("connector.auth names a kind core does not run.",
                           "Use api_token, oauth2_client_credentials or oauth2_authorization_code."),
    "INVALID_OPERATION_ID": D("An operation id is not a dotted lowercase identifier.",
                              "Rename it, such as item.get or portfolio.add."),
    "CONSEQUENCE_MISSING": D("Operations have no consequence: what each call does to the world is undecided.",
                             "Decide each one: flyto pack consequence DIR OP=LEVEL ... with observe, reversible, "
                             "external_write, real_world or irreversible. The HTTP method is not the answer."),
    "CONSEQUENCE_UNKNOWN": D("A consequence is not one of the five levels.",
                             "Use observe, reversible, external_write, real_world or irreversible."),
    "PATH_PARAM_UNDECLARED": D("An operation path has a {parameter} with no input of that name.",
                               "Declare the input under inputs, or remove the placeholder from the path."),
    "INVALID_JSONPATH": D("A sensitive, result_scope, feature or meter path is outside the JSONPath subset.",
                          "Use $, .name, ['name'], [n] and [*] only; no filters, slices or recursive descent."),
    "INVALID_PAGINATION": D("paginate names an unknown strategy, a key that strategy does not read, or a bad bound.",
                            "Use offset, page, cursor or link_header with that strategy's keys; cursor needs cursor_path."),
    # -- the pre-check sections ----------------------------------------------------------------
    "ENTITLEMENTS_REQUIRED": D("An operation requires features or consumes a meter, but there is no entitlements section.",
                               "Declare entitlements with a probe operation, or remove requires and consumes."),
    "FEATURE_UNDECLARED": D("An operation requires a feature entitlements.features.keys does not list.",
                            "Add the feature key to entitlements.features.keys, or fix the typo in requires."),
    "METER_UNDECLARED": D("An operation consumes a meter entitlements.meters does not declare.",
                          "Add the meter with the JSONPath of its remaining amount in the probe answer."),
    "SCOPE_UNDECLARED": D("An input scope or result_scope names a dimension scopes does not declare.",
                          "Add {\"key\": DIMENSION} to scopes, or fix the dimension name."),
    "RESULT_SCOPE_DIMENSION_REQUIRED": D("result_scope is a bare path, but the pack declares several scope dimensions.",
                                         "Write result_scope as {\"dimension\": KEY, \"path\": PATH}."),
    "PROBE_UNKNOWN": D("entitlements.probe names no operation of the connector.",
                       "Set it to the operation that reads what the account holds, or remove entitlements."),
    "PROBE_NOT_OBSERVE": D("The probe operation is not an ungated observe operation.",
                           "Give the probe consequence observe, and no requires or consumes of its own."),
    "RESOLVE_UNKNOWN": D("A scopes entry's resolve names no operation.", "Name an operation of the connector."),
    "INVALID_ENTITLEMENTS": D("entitlements has the wrong shape: keys, meters or max_age_s.",
                              "List feature keys, map meters to JSONPaths, keep max_age_s within 1..86400."),
    "INVALID_SCOPES": D("scopes is not a list of {key, resolve?} entries.", "Write scopes as [{\"key\": \"company\"}]."),
    # -- standalone and the build ----------------------------------------------------------------
    "STANDALONE_BINDING_UNSUPPORTED": D("standalone is declared on a binding that cannot run on its own.",
                                        "Only connector packs run standalone; remove the section otherwise."),
    "INVALID_STANDALONE": D("The standalone section has the wrong shape, or a path outside the pack.",
                            "Declare transports once each, runtime {language, version}, and a relative lockfile."),
    "STANDALONE_DERIVED": D("standalone declares credentials or entry points, which core derives.",
                            "Remove credentials, credentials_needed and entry_points; flyto pack build writes them."),
    "STANDALONE_TRANSPORT_UNKNOWN": D("standalone.transports names an unknown transport.",
                                      "Use stdio and/or streamable_http."),
    "STANDALONE_RUNTIME_UNSUPPORTED": D("standalone.runtime is not a supported language and version floor.",
                                        "Use {\"language\": \"python\", \"version\": \">=3.10\"}."),
    "STANDALONE_MISSING": D("The pack has no standalone section, so it cannot be built or run on its own.",
                            "Add standalone {transports, runtime, lockfile}; flyto pack init writes one."),
    "OUTPUT_EXISTS": D("The output zip already exists.", "Build to a new file; a new build is a new version."),
    "RESERVED_PATH": D("The source holds a file at a path the build writes (bin/ or the notice).",
                       "Remove it from the source; the build generates it."),
    "LOCKFILE_MISSING": D("The pack's lockfile is not in the source and none was passed.",
                          "Pass a hashed lockfile with --lock FILE, or place it at standalone.lockfile."),
    "LOCKFILE_INVALID": D("The lockfile is not pip --require-hashes format, or a line is unpinned or unhashed.",
                          "Pin every requirement with == and at least one --hash=sha256 line."),
    "LOCKFILE_RUNTIME_MISSING": D("The lockfile does not pin flyto-core.", "Add flyto-core==VERSION with its hash."),
    "LOCKFILE_RUNTIME_TOO_OLD": D("The lockfile pins a flyto-core older than pack.min_host.",
                                  "Pin flyto-core at min_host or later, or lower min_host."),
    "PACK_NOT_BUILT": D("A portable pack was verified without artifact.digest.", "Build it first: flyto pack build."),
    "ENTRY_POINT_MISSING": D("A generated entry point is missing from the built pack.",
                             "Rebuild with flyto pack build; never edit a built zip."),
    "ZIP_INVALID": D("The file is not a readable zip, is encrypted, or a size does not match.",
                     "Rebuild the zip with flyto pack build."),
    "ZIP_UNSAFE_PATH": D("A zip entry points outside the pack or is a special file.",
                         "Refuse the zip; rebuild it from source with flyto pack build."),
    "ZIP_SYMLINK": D("The zip contains a symbolic link.", "Rebuild from a source tree without symlinks."),
    "ZIP_DUPLICATE": D("Two zip entries name the same file.", "Rebuild the zip with flyto pack build."),
    "ZIP_NO_MANIFEST": D("The zip has no manifest at its root.", "Build the pack with flyto pack build."),
    "PACK_UNREADABLE": D("The pack path is missing, not a directory, or not a zip.",
                         "Pass the pack directory or the built zip."),
    "PACK_SYMLINK": D("The pack tree contains a symbolic link.", "Replace the link with the file it points to."),
    "PACK_INVALID": D("The pack tree contains a special file.", "Keep only regular files in the pack."),
    "PACK_TOO_LARGE": D("The pack has too many files or bytes.", "Remove build output and caches from the pack."),
    # -- digest, signature, revocation -------------------------------------------------------------
    "DIGEST_MISMATCH": D("The files no longer match artifact.digest.",
                         "Rebuild or re-sign after changing files; never edit a built or signed pack."),
    "UNSIGNED": D("The pack (or bundle) is not signed and a signature is required.",
                  "Sign it with flyto pack build --key ... --key-id ..., or pass --allow-unsigned for local testing."),
    "UNSIGNABLE": D("A manifest without artifact.digest was asked to be signed.",
                    "Sign through flyto pack sign or flyto pack build, which set the digest first."),
    "INVALID_SIGNATURE": D("The signature file is not valid JSON or has the wrong shape.",
                           "Re-sign; do not edit the signature file."),
    "SIGNATURE_UNAVAILABLE": D("This Python has no ed25519 support.", "Install the cryptography package."),
    "UNTRUSTED_KEY": D("The signing key is not one the verifier trusts.",
                       "Pass the publisher's public key: --trusted-key KEY_ID=FILE."),
    "SIGNATURE_MISMATCH": D("The signature does not verify: the manifest or the key differs.",
                            "Re-sign the current manifest with the key whose public half you distribute."),
    "KEY_MISMATCH": D("The signing key id differs from pack.publisher_key_id.",
                      "Sign with the key the manifest names, or update publisher_key_id."),
    "PACK_REVOKED": D("The revocation list names this pack's digest.", "Ship a new version; a revoked digest runs nowhere."),
    "REVOCATION_INVALID": D("The revocation list has the wrong shape or schema.",
                            "Use a list signed with flyto.pack-revocations.v1, unedited."),
    "REVOCATION_UNTRUSTED_KEY": D("The revocation list is signed by a key that is not trusted for it.",
                                  "Pass the list's key with --revocation-key KEY_ID=FILE."),
    "REVOCATION_SIGNATURE_MISMATCH": D("The revocation list's signature does not verify.",
                                       "Fetch the list again; never edit a signed list."),
    # -- install and run ------------------------------------------------------------------------
    "ALREADY_INSTALLED": D("A pack with this id is already installed in this process.",
                           "Uninstall it first; an upgrade is explicit."),
    "BINDING_NOT_LOADABLE": D("inprocess-python packs are not installed from a directory.",
                              "Ship them as a Python distribution with a flyto.modules entry point."),
    "HOST_TOO_OLD": D("This flyto-core is older than the pack's min_host.", "Upgrade flyto-core, or lower min_host."),
    "REGISTRATION_FAILED": D("The registry refused the pack's modules (an id or capability is taken).",
                             "Use a namespace and capabilities no installed pack owns."),
    "ENDPOINT_MISSING": D("An http pack's endpoint environment variable is not set.",
                          "Set the variable the message names to the pack service URL."),
    "INVALID_ENDPOINT": D("An http pack's endpoint is not an absolute HTTP URL with a valid host and port.",
                          "Set the endpoint to http(s)://host:port."),
    "INVALID_SERVE": D("An http pack's runtime.locality is not one the endpoint check knows.",
                       "Set runtime.locality to same_host or same_network."),
    "LOCALITY_DENIED": D("An http pack's endpoint is not where runtime.locality allows.",
                         "Use a loopback endpoint for same_host, or allow the host for same_network."),
    "PROTOCOL_ERROR": D("The pack process answered something that is not a flyto.pack.v1 reply.",
                        "Return JSON with contract_version flyto.pack.v1; see the adapter template."),
    "RESPONSE_TOO_LARGE": D("The pack process answered more than max_response_bytes.",
                            "Return less, or raise runtime.max_response_bytes."),
    "TRANSPORT_UNKNOWN": D("The requested transport is not stdio or streamable_http.", "Use --transport stdio or streamable_http."),
    "TRANSPORT_NOT_DECLARED": D("The pack does not declare the requested transport.",
                                "Add it to standalone.transports, or run with a declared one."),
    "HTTP_BIND_REFUSED": D("The standalone HTTP server was asked to listen beyond loopback.",
                           "Listen on 127.0.0.1; put a reverse proxy in front if others must reach it."),
    "HTTP_TOKEN_WEAK": D("The HTTP bearer token is too short.", "Set FLYTO_PACK_HTTP_TOKEN to a long random value."),
    # -- export and OpenAPI --------------------------------------------------------------------------
    "INVALID_TARGET": D("The export target is not an importable entry point or module:callable.",
                        "Pass a flyto.modules entry point name or package.module:register_all."),
    "EXPORT_FAILED": D("The Python pack failed while registering its modules.", "Run its register function and fix the error."),
    "EXPORT_EMPTY": D("The Python pack registered no modules.", "Make sure register_all registers at least one module."),
    "UNSUPPORTED_OPENAPI": D("The document is not OpenAPI 3, or could not be read.",
                             "Pass an OpenAPI 3.x document as JSON or YAML; convert Swagger 2.0 first."),
    # -- bundles ---------------------------------------------------------------------------------------
    "INVALID_BUNDLE": D("The bundle manifest has the wrong shape or a path outside the bundle.",
                        "Fix the section the message names; see docs/specs/BUNDLE_SPEC.md."),
    "VERSION_NOT_PINNED": D("A bundle or pack version is not one exact release.", "Pin an exact semver such as 1.2.0."),
    "DUPLICATE_NAME": D("Two bundle items share a name.", "Give each item a unique name."),
    "FILE_MISSING": D("A bundle item has no file at its declared path.", "Add the file, or fix the path."),
    "UNDECLARED_FILE": D("The bundle holds a file its manifest does not declare.", "Declare it, or remove it."),
    "WORKFLOW_INVALID": D("A bundle workflow is not a readable JSON or YAML object.", "Fix the workflow document."),
    "WORKFLOW_DIGEST_MISMATCH": D("A bundle workflow changed after the bundle was built.", "Rebuild the bundle."),
    "TEMPLATE_DIGEST_MISMATCH": D("A bundle template changed after the bundle was built.", "Rebuild the bundle."),
    "PACK_NOT_FOUND": D("A pack the bundle pins was not supplied.", "Pass it with --pack ZIP."),
    "PACK_DIGEST_MISMATCH": D("A supplied pack is not the exact build the bundle pins.",
                              "Supply that build, or rebuild the bundle against the new one."),
    "MODULE_NOT_PROVIDED": D("A workflow uses a module no pinned pack provides.",
                             "Pin the pack that provides it, or change the workflow."),
    # -- the scaffold -------------------------------------------------------------------------------------
    "INIT_TARGET_NOT_EMPTY": D("pack init was pointed at a directory that already has files.",
                               "Pass a new or empty directory; init never overwrites."),
    "CONSEQUENCE_TARGET_UNKNOWN": D("A decision names an operation the connector does not declare.",
                                    "Use an operation id from connector.operations, such as item.get."),
    "CONSEQUENCE_DECISION_INVALID": D("A decision is not written OPERATION=LEVEL.",
                                      "Write it as item.get=observe, one per operation."),
    # -- flyto pack test ------------------------------------------------------------------------------------
    "FIXTURES_MISSING": D("The pack has no fixtures/exchanges.json.",
                          "Record the provider's answers there; flyto pack init writes a starting file."),
    "FIXTURES_INVALID": D("fixtures/exchanges.json does not fit flyto.pack-fixtures.v1 or the pack.",
                          "Fix the entry the message names: customers, exchanges and calls must name the pack's own."),
    "NOT_A_CONNECTOR_PACK": D("pack test runs connector packs only.",
                              "For a process pack, run flyto pack conform against the vendor's simulator."),
    "UNEXPECTED_RESULT": D("A call came back other than its fixture expects (ok, or a named error code).",
                           "Read actual: fix the declaration, record the missing answer, or correct expect."),
    "CALL_RAISED": D("A call raised instead of returning a result, usually an input its schema refuses.",
                     "Give the call the inputs the operation declares, with their types."),
    "UNRECORDED_REQUEST": D("The runtime sent a request no recorded exchange answers.",
                            "Record that request and the provider's answer in exchanges, or fix the operation path."),
    "UNKNOWN_CREDENTIAL": D("A request carried a credential no fixture customer holds.",
                            "Give the customer the credential the call uses; only the named credential is sent."),
    "SENSITIVE_PATH_UNMATCHED": D("A sensitive path names no value in any recorded answer, so it protects nothing.",
                                  "Fix the path (a typo is the usual cause), or record an answer that has the field."),
    "DATA_PATH_UNMATCHED": D("paginate.data_path names no list in a recorded page.",
                             "Point data_path at the page's list (dot notation, such as results)."),
    "RESULT_SCOPE_UNMATCHED": D("result_scope named no item in any recorded answer, so the scope filter never ran.",
                                "Point result_scope at each item's scope value, such as $.items[*].id."),
    "PROBE_SHAPE_INVALID": D("A recorded probe answer is not the shape entitlements declares.",
                             "Fix features.path and meters, or record the provider's real probe answer."),
    "OPERATION_UNTESTED": D("No recorded call exercises the operation.", "Add a call for it under calls."),
    "EFFECTIVE_OPERATIONS_MISMATCH": D("A customer is offered other operations than its fixture says.",
                                       "Fix requires.features on the operations, or the customer's offered list."),
}

#: The row for a code this flyto-core does not describe (never a guess at its meaning).
UNLISTED = Diagnosis("A refusal this version of the doctor does not describe.",
                     "Read the message; check the code against the spec for this flyto-core version.")


def explain(code: str, message: str, *, operation: Optional[str] = None,
            operations: Sequence[str] = ()) -> Dict[str, Any]:
    """One refusal, with the table's cause and fix."""
    row = DIAGNOSES.get(code, UNLISTED)
    entry: Dict[str, Any] = {"code": code, "message": message, "cause": row.cause, "fix": row.fix}
    if operation is not None:
        entry["operation"] = operation
    if operations:
        entry["operations"] = list(operations)
    return entry


def _from(error: PackManifestError) -> Dict[str, Any]:
    named = error.operations if len(error.operations) > 1 else ()
    return explain(error.code, str(error), operation=error.operation, operations=named)


def _per_operation(root: Path) -> List[Dict[str, Any]]:
    """Every operation-level refusal, each operation checked on its own."""
    from .connector import _operation, _refuse_undecided
    from .portable import _read_raw_manifest

    try:
        operations = _read_raw_manifest(root)["connector"]["operations"]
    except (PackManifestError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(operations, list):
        return []
    found = []
    try:
        _refuse_undecided(operations)
    except PackManifestError as error:
        found.append(_from(error))
    for index, op in enumerate(operations):
        if isinstance(op, dict) and op.get("consequence") is None:
            # Only to reach the checks after the consequence; never written back,
            # never reported as a decision.
            op = {**op, "consequence": "observe"}
        try:
            _operation(op, index)
        except PackManifestError as error:
            found.append(_from(error))
    return found


def diagnose(pack_dir: os.PathLike[str] | str) -> Dict[str, Any]:
    """Validate a pack directory and explain every refusal found."""
    root = Path(pack_dir)
    try:
        manifest = read_pack_manifest(root)
    except PackManifestError as error:
        diagnoses, seen = [], set()
        for entry in [_from(error), *_per_operation(root)]:
            key = (entry["code"], entry.get("operation"), tuple(entry.get("operations", ())))
            if key not in seen:
                seen.add(key)
                diagnoses.append(entry)
        return {"pack_dir": str(root), "valid": False, "diagnoses": diagnoses}
    return {"pack_dir": str(root), "valid": True, "pack": dict(manifest["pack"]), "diagnoses": [],
            "next": f"flyto pack test {root}"}


def render(report: Mapping[str, Any]) -> str:
    if report["valid"]:
        pack = report["pack"]
        return f"no refusal: {pack['id']} {pack['version']} validates.\nnext: {report['next']}"
    lines = []
    for entry in report["diagnoses"]:
        about = ""
        if entry.get("operations"):
            about = f"  (operations: {', '.join(entry['operations'])})"
        elif entry.get("operation"):
            about = f"  (operation: {entry['operation']})"
        lines += [f"{entry['code']}{about}", f"  said:  {entry['message']}", f"  cause: {entry['cause']}",
                  f"  fix:   {entry['fix']}", ""]
    lines.append(f"{len(report['diagnoses'])} refusal(s); fix them and run flyto pack doctor again")
    return "\n".join(lines)
