# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Deterministic SI-only constant-acceleration kinematics."""

from typing import Any, Dict

from ...domain_solver import exact_unit, finite_number, finite_result, receipt
from ...errors import ValidationError
from ...registry import register_module


@register_module(
    module_id="physics.kinematics_constant_acceleration", version="1.0.0", category="physics",
    tags=["physics", "kinematics", "deterministic"], label="1D Constant-Acceleration Kinematics",
    description="Compute position and velocity for a 1D constant-acceleration SI model.",
    provides_capability="domain.solve.constant-acceleration-kinematics",
    semantics={"intent_ids": ["solve.constant-acceleration-kinematics"], "affordances": ["compute.position-velocity"],
               "effects": ["data.compute-only"], "handled_events": ["domain.solve.requested"]},
    can_receive_from=["*"], can_connect_to=["*"], required_permissions=[],
    params_schema={name: {"type": kind, "required": True} for name, kind in {
        "x0": "number", "v0": "number", "acceleration": "number", "time": "number", "solve_mode": "string",
        "position_unit": "string", "velocity_unit": "string", "acceleration_unit": "string", "time_unit": "string"}.items()},
)
async def kinematics(context: Dict[str, Any]) -> Dict[str, Any]:
    p = context["params"]
    if p.get("solve_mode") != "position_and_velocity":
        raise ValidationError("solve_mode must be 'position_and_velocity'", field="solve_mode")
    units = {field: exact_unit(p, field, unit) for field, unit in {
        "position_unit": "m", "velocity_unit": "m/s", "acceleration_unit": "m/s^2", "time_unit": "s"}.items()}
    x0, v0, acceleration, time = (finite_number(p.get(name), name) for name in ("x0", "v0", "acceleration", "time"))
    if time < 0:
        raise ValidationError("time must be non-negative", field="time")
    position = finite_result(x0 + v0 * time + 0.5 * acceleration * time * time, "position")
    velocity = finite_result(v0 + acceleration * time, "velocity")
    return receipt("physics.kinematics_constant_acceleration", "1.0.0",
                   "x=x0+v0*t+0.5*a*t^2; v=v0+a*t",
                   {"x0": x0, "v0": v0, "acceleration": acceleration, "time": time,
                    "solve_mode": "position_and_velocity"}, units,
                   {"position": position, "velocity": velocity},
                   ["Acceleration is constant over the entire time interval", "One-dimensional SI model only", "No physical-world validation"],
                   {"finite_inputs": True, "non_negative_time": True, "si_units_only": True, "solve_mode_supported": True})
