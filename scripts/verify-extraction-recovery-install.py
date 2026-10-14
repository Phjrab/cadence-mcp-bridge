"""Installed extraction CLI/asset checks; synthetic only, no VM or admission."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from cadence_mcp_bridge import _native_dispatch, _native_setup
from cadence_mcp_bridge.__main__ import build_parser
from cadence_mcp_bridge.extraction_recovery import RecoveryPlan
from cadence_mcp_bridge.native_runtime import SOURCES


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    workspace = arguments.workspace.resolve()
    workspace.mkdir(mode=0o700)
    before = list(workspace.iterdir())
    import cadence_mcp_bridge.extraction_recovery as recovery

    assert Path(recovery.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    cli = build_parser()
    assert "operator-recovery" in cli.format_help()
    parsed = cli.parse_args([
        "operator-recovery", "plan", "--settings", str(workspace / "absent-settings.json"),
        "--context", "synthetic", "--request", str(workspace / "absent-request.json"),
        "--original-operation-id", "11111111-1111-4111-8111-111111111111",
        "--original-plan-sha256", "a" * 64, "--output", str(workspace / "new-plan.json"),
    ])
    assert parsed.recovery_action == "plan"
    assert "recovery.py" in SOURCES and set(_native_dispatch.FILES) == set(_native_setup.FILES)
    asset = files("cadence_mcp_bridge").joinpath(SOURCES["recovery.py"]).read_bytes()
    assert b"class ExtractionRecovery" in asset and b"subprocess" not in asset
    assert "recovery" in RecoveryPlan.model_json_schema()["properties"]
    assert list(workspace.iterdir()) == before
    print(json.dumps({
        "status": "PASS", "scope": "INSTALLED_SYNTHETIC_CLI_AND_ASSETS_NOT_CADENCE",
        "import_initialization": False, "new_simulations": 0, "new_reservations": 0,
        "remote_contact": False, "published_2_0_0_qualification": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
