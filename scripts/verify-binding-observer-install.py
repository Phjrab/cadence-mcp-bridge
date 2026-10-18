"""Installed binding-observer synthetic checks; no VM, EDA, claims or grants.

Run with the installed interpreter in isolated mode. Successful local preparation
and authenticated worker construction are explicitly outside this small checker.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
from importlib.resources import files
from pathlib import Path
from unittest.mock import patch

import cadence_mcp_bridge
from cadence_mcp_bridge import (
    _binding_observation as worker,
)
from cadence_mcp_bridge import (
    binding_observation as contract,
)
from cadence_mcp_bridge import (
    binding_observation_claim,
    physical_metadata,
)
from cadence_mcp_bridge import (
    binding_observer_operator as operator,
)
from cadence_mcp_bridge.__main__ import main as cli_main
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import canonical_digest


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _verify_origins() -> None:
    for module in (
        cadence_mcp_bridge, worker, contract, operator, binding_observation_claim,
        physical_metadata,
    ):
        filename = module.__file__
        if filename is None:
            raise ValueError("installed wheel origin required")
        _require(
            Path(filename).resolve().is_relative_to(Path(sys.prefix).resolve()),
            "installed wheel origin required",
        )


def _forbidden(*args: object, **kwargs: object) -> None:
    raise AssertionError("synthetic checker reached process, transport, home or claim boundary")


def _schema() -> None:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = cli_main(["operator-binding-observation", "schema"])
    report = json.loads(stdout.getvalue())
    _require(code == 0, "installed schema CLI failed")
    _require(report["operational_status"] == "CAPABILITY_NOT_QUALIFIED", "schema enabled")
    _require(report["blockers"] == list(operator.BLOCKERS), "schema blockers changed")
    _require(report["remote_contact"] is False, "schema remote contact")
    _require(report["execution_authorized"] is False, "schema execution authority")
    _require(report["request_schema"]["additionalProperties"] is False, "open request schema")
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            cli_main(["operator-binding-observation", "observe"])
        except SystemExit as failure:
            _require(failure.code == 2, "unexpected operational CLI rejection")
        else:
            raise ValueError("operational observation CLI exposed")


def _request() -> contract.BindingScanRequest:
    return contract.BindingScanRequest.model_validate_json(json.dumps({
        "schema_version": 1,
        "observation_id": "8197b274-d171-48d5-844f-a12dc53677ec",
        "nonce": "a" * 64,
        "library": "SyntheticSources",
        "cell": "SyntheticCell",
        "view": "schematic",
        "variables": [{"logical_id": "input", "cadence_binding": "qa_input"}],
    }))


def _frame(request: contract.BindingScanRequest) -> bytes:
    return ("\n".join([
        f"BINDING_OBSERVATION_V1|{request.observation_id}|{request.nonce}"
        f"|{canonical_digest(request)}",
        "SOURCE|SyntheticSources|SyntheticCell|schematic",
        "VARIABLE|input|qa_input",
        "SCAN|1|1",
        "BIND|1|input|qa_input|SourceA|SyntheticDevices|voltage_source|symbol"
        "|dc|string|qa_input|missing|-|-|-|-",
        "COMPLETE|1|1|1",
    ]) + "\n").encode("ascii")


def _protocol(request: contract.BindingScanRequest) -> tuple[bytes, int]:
    rendered = contract.render_collector(request)
    _require(
        rendered == worker.render_collector(  # type: ignore[no-untyped-call]
            request.model_dump(mode="json")
        ),
        "fixed renderer mismatch",
    )
    _require(
        b'dbOpenCellViewByType("SyntheticSources" "SyntheticCell" "schematic" "" "r")'
        in rendered,
        "fixed renderer did not open synthetic source read only",
    )
    _require(b'outfile("binding-frame.txt")' in rendered, "fixed output changed")
    raw = _frame(request)
    observed = contract.parse_frame(raw, request)
    _require(observed["qualification"] == "NOT_ESTABLISHED_BY_BINDING_SCAN", "frame qualified")
    _require(observed["effective_cdf_complete"] is False, "missing CDF inferred")
    _require(
        observed["record_scope"] == "FIXED_FRAME_ONLY_NO_TRANSPORT_OR_SOURCE_ATTESTATION",
        "frame provenance overstated",
    )
    for name in ("new_simulations", "new_extractions", "new_result_reservation_bytes"):
        _require(observed[name] == 0, "frame claimed operational side effects")
    malformed = (
        raw[:-1],
        raw.replace(request.nonce.encode(), b"b" * 64),
        raw.replace(b"SOURCE|SyntheticSources", b"SOURCE|OtherSources"),
        raw.replace(b"COMPLETE|1|1|1", b"COMPLETE|1|1|2"),
        raw.replace(b"missing|-|-|-|-", b"missing|float|voltage|string|qa_input"),
        raw.replace(b"|dc|string|qa_input|", b"|dc|string|qa_input+1|"),
    )
    for frame in malformed:
        try:
            contract.parse_frame(frame, request)
        except ValueError:
            pass
        else:
            raise ValueError("malformed synthetic frame accepted")
    return rendered, len(malformed)


def _blocked_worker(request: contract.BindingScanRequest, rendered: bytes) -> None:
    # Test the actual bound method without constructing an authenticated remote
    # worker. No profiles, receipts, ownership state, home or process are needed.
    instance = object.__new__(worker.BindingObservationWorker)
    instance.route = {
        "profile": {"binding": {
            "library": request.library, "cell": request.cell, "view": request.view,
        }},
        "variables": request.model_dump(mode="json")["variables"],
    }
    instance.selection = {
        "request_sha256": canonical_digest(request),
        "collector_sha256": hashlib.sha256(rendered).hexdigest(),
    }
    report = instance.observe(request.model_dump(mode="json"))  # type: ignore[no-untyped-call]
    _require(report["status"] == "CAPABILITY_NOT_QUALIFIED", "worker became operational")
    _require(report["remote_execution_enabled"] is False, "worker remote execution enabled")
    _require(report["qualified"] is False, "worker claimed qualification")
    _require(report["closure_trust"] == "NOT_ESTABLISHED", "worker claimed closure trust")
    for name in ("new_eda_starts", "new_simulations", "new_extractions", "new_reservations"):
        _require(report[name] == 0, "worker claimed operational side effects")


def _pins() -> None:
    sources = {
        "copy.py": "_native_copy.py",
        "reservations.py": "_shared_reservations.py",
        "process.py": "_native_eda_worker.py",
    }
    _require(set(worker.HELPER_PINS) == set(sources), "worker helper inventory changed")
    pins = operator.asset_pins()
    _require(set(pins) == set(operator.ASSETS), "operator asset inventory changed")
    for asset in operator.ASSETS:
        raw = files("cadence_mcp_bridge").joinpath(asset).read_bytes().replace(b"\r\n", b"\n")
        _require(pins[asset] == hashlib.sha256(raw).hexdigest(), "installed asset pin mismatch")
    for remote, source in sources.items():
        _require(worker.HELPER_PINS[remote] == pins[source], "installed helper pin mismatch")


def verify(workspace: Path) -> dict[str, object]:
    _verify_origins()
    workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
    with contextlib.ExitStack() as guards:
        for target in (
            "subprocess.Popen", "socket.socket", "pathlib.Path.home",
            "cadence_mcp_bridge.physical_metadata._operator_home",
            "cadence_mcp_bridge.binding_observation_claim.claim",
            "cadence_mcp_bridge.operator_transport.run_fixed",
        ):
            guards.enter_context(patch(target, _forbidden))
        guards.enter_context(patch.object(ExecutionContext, "backend", _forbidden))
        guards.enter_context(patch.object(worker.BindingObservationWorker, "_stage", _forbidden))
        _schema()
        request = _request()
        rendered, rejected_frames = _protocol(request)
        _blocked_worker(request, rendered)
        _pins()
    _require(not list(workspace.iterdir()), "synthetic checker wrote unexpected state")
    return {
        "status": "PASS",
        "scope": "INSTALLED_BINDING_OBSERVER_SYNTHETIC_NOT_CADENCE",
        "installed_origin": True,
        "schema_cli": "INSTALLED_IN_PROCESS_WITH_SIDE_EFFECT_GUARDS",
        "observe_cli": "ABSENT",
        "successful_preparation": "NOT_TESTED_BY_THIS_CHECKER",
        "fixed_renderer": True,
        "strict_parser_rejected_frames": rejected_frames,
        "worker_observe": "BLOCKED_METHOD_WITH_SYNTHETIC_BOUND_ROUTE",
        "authenticated_worker_construction": "NOT_TESTED_BY_THIS_CHECKER",
        "normalized_installed_helper_pins": True,
        "new_simulations": 0,
        "new_extractions": 0,
        "new_reservations": 0,
        "claim_spent": False,
        "remote_contact": False,
        "qualification_established": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.workspace.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
