"""One pack, three products, every combination a customer can hold.

A provider sells products separately. Its pack declares each product as a
feature, and each operation requires the features it needs; one operation
(``plan.forecast``) needs two. A customer is offered exactly the operations
their entitlement allows, as the provider's own probe answers it, through
``effective_module_ids``. The expected listings below are written out by
hand for all eight combinations, not computed from the same rule.

The fake provider is built from the example's recorded fixtures; nothing
reaches a real provider.
"""

import pytest
from devkit_helpers import ROOT

from core.modules.registry import ModuleRegistry
from core.pack.host import effective_module_ids
from core.pack.recorded import recorded_install, render, run_pack_tests

EXAMPLE = ROOT / "examples" / "packs" / "product-combinations"
PACK_ID = "com.example.suite"

#: Customer (the products it holds) -> exactly the operations it is offered.
OFFERED = {
    "none": ["account.entitlements"],
    "records": ["account.entitlements", "record.get"],
    "planning": ["account.entitlements", "plan.get"],
    "analytics": ["account.entitlements", "trend.get"],
    "records_planning": ["account.entitlements", "plan.get", "record.get"],
    "records_analytics": ["account.entitlements", "record.get", "trend.get"],
    "planning_analytics": ["account.entitlements", "plan.forecast", "plan.get", "trend.get"],
    "records_planning_analytics": ["account.entitlements", "plan.forecast", "plan.get", "record.get", "trend.get"],
}


@pytest.mark.parametrize("customer", sorted(OFFERED))
async def test_each_combination_is_offered_exactly_what_it_holds(customer):
    async with recorded_install(EXAMPLE) as session:
        offered = await effective_module_ids(PACK_ID, session.secrets(customer))
    assert offered == [f"suite.{op}" for op in OFFERED[customer]]


def test_the_table_covers_every_combination_of_the_three_products():
    products = ("records", "planning", "analytics")
    combinations = {frozenset(name.split("_")) - {"none"} for name in OFFERED}
    assert len(combinations) == 2 ** len(products)
    assert all(combo <= set(products) for combo in combinations)


@pytest.mark.parametrize("customer, missing", [
    ("planning", ["analytics"]),
    ("analytics", ["planning"]),
    ("records", ["planning", "analytics"]),
])
async def test_the_two_product_operation_names_what_is_missing(customer, missing):
    async with recorded_install(EXAMPLE) as session:
        result = await ModuleRegistry.get("suite.plan.forecast")({"plan": "p-1"}, session.context(customer)).run()
    assert result["ok"] is False and result["error_code"] == "FEATURE_NOT_ENTITLED"
    assert result["missing_features"] == missing
    assert session.requests("/v1/plans/p-1/forecast") == []


async def test_the_two_product_operation_runs_for_a_customer_holding_both():
    async with recorded_install(EXAMPLE) as session:
        result = await ModuleRegistry.get("suite.plan.forecast")(
            {"plan": "p-1"}, session.context("planning_analytics")).run()
    assert result["ok"] is True
    assert result["data"] == {"plan": "p-1", "forecast": [9, 11]}
    assert result["metadata"]["precheck"]["features"] == ["planning", "analytics"]


def test_the_example_passes_its_own_pack_test():
    report = run_pack_tests(EXAMPLE)
    assert report["passed"] is True, render(report)
    assert set(report["customers"]) == set(OFFERED)
    assert all(item["verdict"] == "pass" for item in report["customers"].values())
