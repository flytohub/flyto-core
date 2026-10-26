"""
Chain CLI Commands -- verify a ``flyto.execution-chain.v1`` record offline.

Usage:
    flyto chain verify <record.json> --keys <keys.json> [--keys FILE ...] [--trust all|host-only]

``<record.json>`` is a record or an execution-chain export (only its record is
read; keys embedded in an export are used only when that file is also passed
as ``--keys``). A ``--keys`` file holds a ``flyto.execution-chain-keys.v1``
document, a ``{"<signer>": <document>}`` map, an export, or a JSON list of
any of these. ``--cloud-keys`` and ``--host-keys`` are accepted as aliases.

Exit codes: 0 verified, 1 refused, 2 incomplete. The report is JSON on stdout.
No network is used.
"""

import argparse
import json
from pathlib import Path
from typing import Any, List, Sequence, Union

VERIFY_EPILOG = "Exit codes: 0 verified, 1 refused (typed codes in the report), 2 incomplete."


def _add_verify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("record", help="A flyto.execution-chain.v1 record, or an execution-chain export")
    parser.add_argument("--keys", action="append", default=[], metavar="FILE",
                        help="Published key documents (repeatable): a document, a {signer: document} map, "
                             "an export, or a list of them")
    parser.add_argument("--cloud-keys", action="append", default=[], metavar="FILE", help=argparse.SUPPRESS)
    parser.add_argument("--host-keys", action="append", default=[], metavar="FILE", help=argparse.SUPPRESS)
    parser.add_argument("--trust", choices=("all", "host-only"), default="all",
                        help="host-only: check host-signed sections and every link, with no issuer key")


def add_chain_parser(subparsers) -> None:
    """Add the ``chain`` subcommand to the CLI."""
    chain_parser = subparsers.add_parser(
        "chain",
        help="Execution chain records (flyto.execution-chain.v1)",
        description="Verify an execution chain record offline against published keys.",
    )
    sub = chain_parser.add_subparsers(dest="chain_action", help="Chain actions")
    verify_p = sub.add_parser("verify", help="Verify a record's links, signatures and invariants offline",
                              epilog=VERIFY_EPILOG)
    _add_verify_arguments(verify_p)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flyto")
    add_chain_parser(parser.add_subparsers(dest="command"))
    return parser


def _read(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _verify(args) -> int:
    from core.chain import record_from, verify_record
    from core.chain.keys import ChainKeysError
    from core.chain.verify import key_documents_from, refused

    try:
        record = record_from(_read(args.record))
        inputs = [_read(path) for path in (*args.keys, *args.cloud_keys, *args.host_keys)]
    except (OSError, ValueError):
        report = refused(None, args.trust, ["CHAIN_INPUT_UNREADABLE"])
    else:
        try:
            keys = key_documents_from(inputs)
        except ChainKeysError as error:
            report = refused(record, args.trust, [error.code], detail=str(error))
        else:
            report = verify_record(record, keys, trust=args.trust)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return int(report["exit"])


def run_chain_command(args: Union[argparse.Namespace, Sequence[str]]) -> int:
    """Execute a chain subcommand (a parsed namespace, or the argv after ``chain``)."""
    if not isinstance(args, argparse.Namespace):
        args = _parser().parse_args(["chain", *list(args)])
    handlers = {"verify": _verify}
    handler = handlers.get(getattr(args, "chain_action", None))
    if handler is None:
        _parser().parse_args(["chain", "--help"])
        return 1
    return handler(args)


__all__: List[str] = ["add_chain_parser", "run_chain_command"]
