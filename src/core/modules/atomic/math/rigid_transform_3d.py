# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Deterministic 3D point rigid transform, with no physical-world validation."""

import math
from typing import Any, Dict

from ...domain_solver import exact_unit, finite_number, finite_result, receipt, safe_text
from ...errors import ValidationError
from ...registry import register_module

TOLERANCE = 1e-12


@register_module(
    module_id="math.rigid_transform_3d", version="1.0.0", category="math",
    subcategory="geometry", tags=["math", "geometry", "deterministic"],
    label="3D Rigid Point Transform",
    description="Apply a declared proper orthonormal 3x3 rotation and translation to one 3D point.",
    provides_capability="domain.solve.rigid-transform-3d",
    semantics={"intent_ids": ["solve.rigid-transform-3d"], "affordances": ["transform.point-3d"],
               "effects": ["data.compute-only"], "handled_events": ["domain.solve.requested"]},
    can_receive_from=["*"], can_connect_to=["*"], required_permissions=[],
    params_schema={name: {"type": kind, "required": True} for name, kind in {
        "point": "array", "rotation": "array", "translation": "array",
        "source_frame": "string", "target_frame": "string", "length_unit": "string"}.items()},
)
async def rigid_transform_3d(context: Dict[str, Any]) -> Dict[str, Any]:
    p = context["params"]
    unit = exact_unit(p, "length_unit", "m")
    frames = [safe_text(p.get("source_frame"), "source_frame"),
              safe_text(p.get("target_frame"), "target_frame")]
    if frames[0] == frames[1]:
        raise ValidationError("source_frame and target_frame must be distinct non-empty strings")
    point_raw, translation_raw, rotation_raw = p.get("point"), p.get("translation"), p.get("rotation")
    if type(point_raw) is not list or len(point_raw) != 3 or type(translation_raw) is not list or len(translation_raw) != 3:
        raise ValidationError("point and translation must each have exactly 3 values")
    if type(rotation_raw) is not list or len(rotation_raw) != 3 or any(type(row) is not list or len(row) != 3 for row in rotation_raw):
        raise ValidationError("rotation must be a 3x3 matrix")
    point = [finite_number(v, "point") for v in point_raw]
    translation = [finite_number(v, "translation") for v in translation_raw]
    rotation = [[finite_number(v, "rotation") for v in row] for row in rotation_raw]
    products = [[finite_result(sum(rotation[k][i] * rotation[k][j] for k in range(3)), "rotation")
                 for j in range(3)] for i in range(3)]
    orthonormal = all(abs(products[i][j] - (1.0 if i == j else 0.0)) <= TOLERANCE for i in range(3) for j in range(3))
    determinant = (rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
                   - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
                   + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0]))
    determinant = finite_result(determinant, "rotation")
    if not orthonormal:
        raise ValidationError(f"rotation must be orthonormal within tolerance {TOLERANCE}")
    if not math.isclose(determinant, 1.0, rel_tol=0.0, abs_tol=TOLERANCE):
        raise ValidationError(f"rotation determinant must be +1 within tolerance {TOLERANCE}")
    transformed = [finite_result(sum(rotation[i][j] * point[j] for j in range(3)) + translation[i], "result")
                   for i in range(3)]
    return receipt("math.rigid_transform_3d", "1.0.0", "p_target = R * p_source + t",
                   {"point": point, "rotation": rotation, "translation": translation,
                    "source_frame": frames[0], "target_frame": frames[1]},
                   {"point": unit, "translation": unit, "result": unit}, {"point": transformed},
                   ["R is a declared proper rotation", "All lengths use one explicit metre unit", "No physical-world frame validation"],
                   {"finite_inputs": True, "shape_3d": True, "frames_distinct": True,
                    "rotation_orthonormal": True, "determinant_positive_one": True, "single_supported_unit": True})
