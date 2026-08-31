from __future__ import annotations

import json
from importlib import util
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = PROJECT_ROOT / "remote" / "py26" / "actual_profile_audit.py"


def load_helper() -> ModuleType:
    spec = util.spec_from_file_location("actual_profile_audit", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parameter_metadata_separates_declaration_from_reference() -> None:
    helper = load_helper()
    source = (
        b"parameters VBIASN=300m\n"
        b"BIASN (vbiasn 0) vsource dc=VBIASN\n"
        b"BIASP (vbiasp 0) vsource dc=VBIASP\n"
    )

    metadata = helper.parameter_metadata(source)

    assert metadata["VBIASN"] == {
        "declared_in_source": True,
        "declaration_occurrences": 1,
        "non_declaration_occurrences": 1,
        "referenced_outside_declaration": True,
        "token_occurrences": 2,
    }
    assert metadata["VBIASP"]["declared_in_source"] is False
    assert metadata["VBIASP"]["referenced_outside_declaration"] is True


def test_build_audit_returns_only_bounded_metadata(tmp_path: Path) -> None:
    helper = load_helper()
    source = tmp_path / "netlist"
    source.write_bytes(
        b"parameters VBIASN=300m VBIASP=650m\n"
        b"BIASN (vbiasn 0) vsource dc=VBIASN\n"
        b"BIASP (vbiasp 0) vsource dc=VBIASP\n"
    )
    state = tmp_path / "state1"
    state.mkdir()
    (state / "metadata").write_text("bounded fixture", encoding="utf-8")
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "profile_id": helper.PROFILE_ID,
                "source_netlist": str(source),
                "state_path": str(state),
                "fixed_parameters": {"VBIASN": "300m", "VBIASP": "650m"},
                "variables": {},
            }
        ),
        encoding="utf-8",
    )
    helper.PROFILE_PATH = str(profile_path)
    helper.SOURCE_NETLIST = str(source)
    helper.STATE_PATH = str(state)
    helper.JOBS_ROOT = str(jobs)

    audit = helper.build_audit()

    assert audit["raw_content_included"] is False
    assert audit["paths_included"] is False
    assert audit["profile"]["fixed_parameters"] == {
        "VBIASN": "300m",
        "VBIASP": "650m",
    }
    assert audit["source_netlist"]["parameter_metadata"]["VBIASN"][
        "referenced_outside_declaration"
    ]
    assert len(audit["source_netlist"]["sha256"]) == 64
    assert len(audit["ade_state"]["tree_metadata_sha256"]) == 64
    assert audit["latest_successful_actual_manifest"] == {"found": False}
    assert str(tmp_path) not in json.dumps(audit)
