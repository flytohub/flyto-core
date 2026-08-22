from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMON = {
    "schema": "flyto.product-contract.v1",
    "product": "Flyto2",
    "promise": "Turn AI work into verified, replayable procedures.",
    "proof_line": "AI said it finished. Flyto2 shows the proof.",
}
CORE_PACKAGE = {
    "name": "flyto-core",
    "layer": "execution",
    "layer_order": 3,
    "owns": [
        "schema validation",
        "deterministic execution and replay",
        "evidence",
    ],
    "does_not_own": [
        "intent and provider governance",
        "procedure learning and scoring",
        "hosted product and account logic",
    ],
}


def _load_contract() -> dict:
    """Parse this deliberately small TOML contract with Python 3.9 stdlib."""
    values = {}
    section = values
    pending_key = None
    pending_values = []
    for raw_line in (ROOT / "flyto-product.toml").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if pending_key is not None:
            if line == "]":
                section[pending_key] = pending_values
                pending_key = None
                pending_values = []
            else:
                pending_values.append(line.rstrip(",").strip('"'))
            continue
        if line.startswith("["):
            name = line[1:-1]
            section = values.setdefault(name, {})
            continue
        key, raw_value = (part.strip() for part in line.split("=", 1))
        if raw_value == "[":
            pending_key = key
        elif raw_value.startswith('"'):
            section[key] = raw_value.strip('"')
        else:
            section[key] = int(raw_value)
    assert pending_key is None
    return values


def test_core_product_contract_is_exact() -> None:
    contract = _load_contract()
    assert contract == {**COMMON, "package": CORE_PACKAGE}


def test_readme_presents_the_shared_contract_and_core_role() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for value in COMMON.values():
        assert value in readme
    for role in (
        "`flyto-ai` | Understand, route, and govern new work and provider use.",
        "`flyto-blueprint` | Store, learn from, and score reusable procedures; it never executes them.",
        "`flyto-core` | Validate schemas, execute and replay deterministically, and emit evidence.",
        "`flyto-core` is a standalone execution package",
    ):
        assert role in readme
