"""
CLI glue for ``flyto run --capability-host``.

Builds a :class:`core.capability_host.CapabilityHost` from the run arguments
and writes its call records when the run ends. The policy itself (allow list,
physical confirmation, safe stop) lives in the host, not here.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DEFAULT_OUTPUT_DIR, Colors


def _allowed(values: Optional[List[str]]) -> List[str]:
    allowed: List[str] = []
    for value in values or []:
        allowed.extend(item.strip() for item in str(value).split(",") if item.strip())
    return allowed


def _interactive() -> bool:
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def build_capability_host(args: Any) -> Any:
    """The run's capability host, or exit 2 with the reason."""
    from core.capability_host import (
        CapabilityHost,
        CapabilityHostError,
        installed_adapters,
        tty_confirm,
    )

    adapter_id = str(args.capability_host or "").strip()
    resource_id = str(getattr(args, "resource", "") or "").strip()
    if not resource_id:
        print(f"{Colors.FAIL}Error: --capability-host needs --resource RESOURCE_ID{Colors.ENDC}")
        sys.exit(2)
    if adapter_id not in installed_adapters():
        found = ", ".join(installed_adapters()) or "none"
        print(f"{Colors.FAIL}Error: adapter {adapter_id!r} is not installed "
              f"(installed: {found}){Colors.ENDC}")
        sys.exit(2)
    try:
        host = CapabilityHost(
            adapter_id=adapter_id,
            resource_id=resource_id,
            allow=_allowed(getattr(args, "allow", None)),
            yes_physical=bool(getattr(args, "yes_physical", False)),
            # No terminal, no prompt: the host then refuses physical actuation.
            confirm=tty_confirm if _interactive() else None,
            artifact_dir=Path(DEFAULT_OUTPUT_DIR) / "capability-artifacts",
        )
    except CapabilityHostError as error:
        print(f"{Colors.FAIL}Error: {error}{Colors.ENDC}")
        sys.exit(2)
    allowed = ", ".join(sorted(host.allowed)) or "none"
    print(f"Capability host: adapter {adapter_id}, resource {resource_id}, "
          f"actuating capabilities allowed: {allowed}")
    return host


def write_capability_evidence(
    host: Any,
    evidence_path: Any,
    workflow_path: Path,
    config: Dict[str, Any],
) -> Path:
    """Write every call record as JSON and print one summary line per call."""
    records = host.records()
    if evidence_path:
        path = Path(evidence_path)
    else:
        output_dir = Path(config.get("storage", {}).get("output_dir", str(DEFAULT_OUTPUT_DIR)))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"capability_{workflow_path.stem}_{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"run_id": host.run_id, "calls": records}, indent=2, default=str))
    for record in records:
        verification = record.get("verification") or {}
        verified = verification.get("verified")
        tail = "" if verified is None else (" evidence verified" if verified else " evidence NOT verified")
        print(f"  {record.get('capability_id')}: {record.get('outcome')}{tail}"
              + (f" ({record.get('detail')})" if record.get("detail") else ""))
    print(f"Capability evidence: {path}")
    return path
