"""Helpers for the provider developer kit tests: the CLI, a decided scaffold, fixture edits."""

import argparse
import json
from pathlib import Path

from cli.pack import add_pack_parser, run_pack_command

ROOT = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).parent / "fixtures" / "portable_requirements.lock"

#: The decisions an author makes for the blank template's two operations.
BLANK_DECISIONS = ("account.entitlements=observe", "item.get=observe")


def cli(*argv):
    """Run ``flyto pack ...`` in-process; returns the exit code."""
    parser = argparse.ArgumentParser()
    add_pack_parser(parser.add_subparsers(dest="command"))
    return run_pack_command(parser.parse_args(["pack", *map(str, argv)]))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, document):
    Path(path).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def edit_json(path, change):
    document = read_json(path)
    change(document)
    write_json(path, document)
    return document


def decided_scaffold(tmp_path, name="items-pack"):
    """``flyto pack init`` from the blank template, with every consequence decided."""
    target = tmp_path / name
    assert cli("init", target, "--pack-id", "com.example.items") == 0
    assert cli("consequence", target, *BLANK_DECISIONS) == 0
    return target


def operation(document, op_id):
    return next(op for op in document["connector"]["operations"] if op["id"] == op_id)
