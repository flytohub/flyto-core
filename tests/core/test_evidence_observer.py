"""An evidence spec may require that another resource observed the effect.

``observer: other_resource`` -- a plug switching a lamp is proven by a camera
seeing the room brighten, never by the plug's own report. A capability host
observes only its own adapter, so it never proves such a spec; the control
plane that holds every resource's observations judges it.
"""

import pytest

from core.capability_contract import EVIDENCE_OBSERVERS, judge, validate_evidence

LIT = {
    "kind": "lamp_lit", "observe": "scene_light", "phases": ["before", "after"],
    "measure": {"op": "delta", "fields": ["mean_luma"]},
    "expect": {"value": 60}, "tolerance": {"absolute": 40, "relative": 0},
}
BRIGHTER = {"before": {"mean_luma": 20.0}, "after": {"mean_luma": 80.0}}


def test_the_observers_are_the_actor_and_another_resource():
    assert frozenset({"self", "other_resource"}) == EVIDENCE_OBSERVERS


@pytest.mark.parametrize("observer", ["self", "other_resource"])
def test_a_declared_observer_is_kept(observer):
    assert validate_evidence({**LIT, "observer": observer})["observer"] == observer


def test_an_undeclared_observer_adds_no_key_so_stored_hashes_hold():
    assert "observer" not in validate_evidence(dict(LIT))


@pytest.mark.parametrize("observer", ["camera", "", 1, None, "OTHER_RESOURCE"])
def test_an_unknown_observer_is_rejected(observer):
    with pytest.raises(ValueError, match="observer"):
        validate_evidence({**LIT, "observer": observer})


def test_the_actor_proves_its_own_spec_as_before():
    assert judge({**LIT, "observer": "self"}, {}, BRIGHTER)["usable"] is True


def test_a_host_never_proves_another_resources_spec_from_its_own_observations():
    verdict = judge({**LIT, "observer": "other_resource"}, {}, BRIGHTER)
    assert verdict["usable"] is False
    assert "another resource" in verdict["reason"]
