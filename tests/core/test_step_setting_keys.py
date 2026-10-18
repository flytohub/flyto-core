"""The per-step execution settings are one table the engine owns.

A step's ``timeout``, ``retry``, ``on_error``, ``when``, ``foreach``/``as`` and
``output`` belong to the step and the engine, not to its module: no module
schema declares them, and a host asking a module contract about a step's
parameters must not take one for an undeclared module parameter.
``STEP_SETTING_KEYS`` is where a host reads which names those are.
"""
import inspect

from core.engine import flow_control
from core.engine.step_executor import executor
from core.engine.workflow import engine


def test_the_table_names_every_setting_the_engine_reads_off_a_step():
    source = inspect.getsource(executor) + inspect.getsource(engine)
    canonical = flow_control.STEP_SETTING_KEYS - set(flow_control.LEGACY_STEP_SETTING_KEYS)
    for key in canonical:
        assert f"step_config.get('{key}'" in source or f"step.get('{key}'" in source, key


def test_the_legacy_spellings_are_settings_too():
    for legacy, canonical in flow_control.LEGACY_STEP_SETTING_KEYS.items():
        assert {legacy, canonical} <= flow_control.STEP_SETTING_KEYS


def test_a_setting_is_never_a_module_parameter_name_the_engine_ignores():
    assert flow_control.is_step_setting("timeout")
    assert flow_control.is_step_setting("onError")
    assert not flow_control.is_step_setting("timeout_ms")
    assert not flow_control.is_step_setting("password")
