"""The example in docs/specs/PORTABLE_CAPABILITY_SPEC.md is a valid pack, and says what it claims.

The page publishes a learned pick-and-place capability as the model for
publishers. These tests keep it true: the checked-in manifest validates, the
excerpt in the page is the file's own row, and the evidence verdicts the page
lists are what ``judge`` returns.
"""

import json
import re
from pathlib import Path

import pytest

from core.capability_contract import judge
from core.pack.manifest import PackManifestError, validate_pack_manifest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "packs" / "tabletop-arm" / "flyto-pack.json"
SPEC = ROOT / "docs" / "specs" / "PORTABLE_CAPABILITY_SPEC.md"
ARGUMENTS = {"object_id": "cup-1", "target_x": 0.10, "target_y": 0.30}


def _raw():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _row(manifest, module_id):
    return next(row for row in manifest["modules"] if row["module_id"] == module_id)


def _placement():
    return _row(validate_pack_manifest(_raw()), "tabletop.pick_place")["contract"]["evidence"][0]


def _observed(x, y, frame="table"):
    return {phase: {"x": x, "y": y, "frame": frame} for phase in ("after", "settled")}


def test_the_example_pack_validates_with_a_movement_capability_and_its_stop():
    manifest = validate_pack_manifest(_raw())

    assert _row(manifest, "tabletop.pick_place")["contract"]["safety_class"] == "movement"
    assert _row(manifest, "tabletop.halt")["contract"]["role"] == "safe_stop"


def test_the_excerpt_in_the_page_is_the_files_own_row():
    blocks = re.findall(r"```json\n(.*?)\n```", SPEC.read_text(encoding="utf-8"), re.S)
    excerpt = json.loads(next(block for block in blocks if '"tabletop.pick_place"' in block))
    row = _row(_raw(), "tabletop.pick_place")
    contract = {key: value for key, value in row["contract"].items() if key != "artifacts"}
    contract["evidence"] = [
        {key: value for key, value in spec.items() if key not in ("label", "unit")}
        for spec in contract["evidence"]
    ]

    assert excerpt == {
        "module_id": row["module_id"],
        "provides_capability": row["provides_capability"],
        "params_schema": row["params_schema"],
        "contract": contract,
    }


@pytest.mark.parametrize(
    ("observations", "usable"),
    [
        (_observed(0.11, 0.30), True),
        (_observed(0.15, 0.30), False),
        (_observed(0.10, 0.30, frame="camera"), False),
        ({}, False),
    ],
    ids=["1 cm off", "5 cm off", "wrong frame", "not observed"],
)
def test_the_verdicts_the_page_lists_are_what_judge_returns(observations, usable):
    assert judge(_placement(), ARGUMENTS, observations)["usable"] is usable


def test_an_unbounded_number_on_the_actuating_capability_is_refused():
    raw = _raw()
    del raw["modules"][0]["params_schema"]["target_x"]["max"]

    with pytest.raises(PackManifestError):
        validate_pack_manifest(raw)
