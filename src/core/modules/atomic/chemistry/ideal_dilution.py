# Copyright 2026 Flyto2. Licensed under Apache-2.0. See LICENSE.

"""Ideal dilution arithmetic only; this module has no laboratory authority."""

from typing import Any, Dict

from ...domain_solver import exact_unit, finite_number, finite_result, receipt
from ...errors import ValidationError
from ...registry import register_module


@register_module(
    module_id="chemistry.ideal_dilution", version="1.0.0", category="chemistry",
    tags=["chemistry", "dilution", "deterministic"], label="Ideal Dilution Arithmetic",
    description="Ideal C1*V1=C2*V2 arithmetic only; no substance, compatibility, reaction, lab, medical, handling, or safety authority.",
    provides_capability="domain.solve.ideal-dilution",
    semantics={"intent_ids": ["solve.ideal-dilution"], "affordances": ["compute.stock-diluent-volume"],
               "effects": ["data.compute-only"], "handled_events": ["domain.solve.requested"]},
    can_receive_from=["*"], can_connect_to=["*"], required_permissions=[],
    params_schema={name: {"type": kind, "required": True} for name, kind in {
        "stock_concentration": "number", "target_concentration": "number", "final_volume": "number",
        "concentration_unit": "string", "volume_unit": "string", "solve_mode": "string"}.items()},
)
async def ideal_dilution(context: Dict[str, Any]) -> Dict[str, Any]:
    p = context["params"]
    if p.get("solve_mode") != "stock_and_diluent_volume":
        raise ValidationError("solve_mode must be 'stock_and_diluent_volume'", field="solve_mode")
    concentration_unit = exact_unit(p, "concentration_unit", "mol/L")
    volume_unit = exact_unit(p, "volume_unit", "L")
    stock = finite_number(p.get("stock_concentration"), "stock_concentration", positive=True)
    target = finite_number(p.get("target_concentration"), "target_concentration", positive=True)
    final_volume = finite_number(p.get("final_volume"), "final_volume", positive=True)
    if target > stock:
        raise ValidationError("target_concentration cannot exceed stock_concentration", field="target_concentration")
    # Divide first: target <= stock keeps the ratio in [0, 1] and avoids the
    # needless overflow risk of multiplying two large finite inputs first.
    stock_volume = finite_result((target / stock) * final_volume, "stock_volume")
    diluent_volume = finite_result(final_volume - stock_volume, "diluent_volume")
    return receipt("chemistry.ideal_dilution", "1.0.0", "C1*V1=C2*V2; Vdiluent=Vfinal-V1",
                   {"stock_concentration": stock, "target_concentration": target, "final_volume": final_volume,
                    "solve_mode": "stock_and_diluent_volume"},
                   {"concentration": concentration_unit, "volume": volume_unit},
                   {"stock_volume": stock_volume, "diluent_volume": diluent_volume},
                   ["IDEAL ARITHMETIC ONLY", "No substance identity or compatibility model", "No reaction, laboratory, medical, handling, or safety authority"],
                   {"finite_positive_inputs": True, "target_not_above_stock": True, "supported_units": True,
                    "solve_mode_supported": True, "non_negative_diluent_volume": diluent_volume >= 0})
