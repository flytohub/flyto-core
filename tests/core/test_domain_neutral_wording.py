# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Generic contract modules describe any resource, never one kind of machine.

A capability contract, the capability host, the adapter status contract and
the execution-chain verifier serve a software connector and a piece of
equipment alike. Their wording stays neutral, so a reader never takes one
domain's example for the rule. Pack examples and vendor packs are not listed:
they are allowed to be about one machine.
"""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"

#: Modules that define a contract for every kind of resource.
GENERIC_MODULES = (
    "core/capability_contract.py",
    "core/capability_host/host.py",
    "core/capability_host/__init__.py",
    "core/adapter_status.py",
    "core/chain/__init__.py",
    "core/chain/record.py",
    "core/chain/keys.py",
    "core/chain/verify.py",
    "cli/chain.py",
)

#: Words that name one kind of machine.
DOMAIN_WORDS = re.compile(r"\b(robots?|robotic|cars?|vehicles?|rosbridge|ros ?2?)\b", re.IGNORECASE)


@pytest.mark.parametrize("relative", GENERIC_MODULES)
def test_generic_contract_modules_use_neutral_wording(relative):
    text = (SRC / relative).read_text(encoding="utf-8")
    found = [
        f"{relative}:{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if DOMAIN_WORDS.search(line)
    ]
    assert found == []
