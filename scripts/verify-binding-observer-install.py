"""Installed binding-observer synthetic checks; no VM, EDA, claims or grants.

Run with the installed interpreter in isolated mode. Worker construction uses
fictional canonical configuration and the installed fixed-resource factory.
Successful operator preparation and actual runtime trust remain outside this check.
"""

from __future__ import annotations

import argparse
import base64
import builtins
import contextlib
import hashlib
import io
import json
import os
import sys
from importlib.resources import files
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import cadence_mcp_bridge
from cadence_mcp_bridge import (
    _binding_observation as worker,
)
from cadence_mcp_bridge import (
    _binding_storage_admin as storage_admin,
)
from cadence_mcp_bridge import (
    binding_initializer,
    binding_observation_claim,
    binding_storage_admin,
    physical_metadata,
)
from cadence_mcp_bridge import (
    binding_observation as contract,
)
from cadence_mcp_bridge import (
    binding_observation_bootstrap as bootstrap,
)
from cadence_mcp_bridge import (
    binding_observer_operator as operator,
)
from cadence_mcp_bridge.__main__ import main as cli_main
from cadence_mcp_bridge.designs import DesignProfile
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.generic_measurements import GenericReaderRegistration
from cadence_mcp_bridge.runtime_context import ExecutionContext
from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _verify_origins() -> None:
    for module in (
        cadence_mcp_bridge, worker, contract, bootstrap, operator, binding_observation_claim,
        physical_metadata,
        storage_admin, binding_storage_admin, binding_initializer,
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


@contextlib.contextmanager
def _readonly_file_opens():
    # Guard common Python file-open APIs during this synthetic check. These are
    # regression guards, not a sandbox against arbitrary hostile interpreter code.
    open_builtin, open_io, open_os = builtins.open, io.open, os.open

    def check_mode(mode):
        if not isinstance(mode, str) or any(flag in mode for flag in "wax+"):
            raise AssertionError("synthetic checker reached write-capable file-open boundary")

    def readonly_builtin(file, mode="r", *args, **kwargs):
        check_mode(mode)
        return open_builtin(file, mode, *args, **kwargs)

    def readonly_io(file, mode="r", *args, **kwargs):
        check_mode(mode)
        return open_io(file, mode, *args, **kwargs)

    def readonly_os(file, flags, *args, **kwargs):
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
        # O_TMPFILE includes O_DIRECTORY on Linux; directory reads remain valid.
        temporary = getattr(os, "O_TMPFILE", 0) & ~getattr(os, "O_DIRECTORY", 0)
        temporary |= getattr(os, "O_TEMPORARY", 0)
        if flags & (write_flags | temporary):
            raise AssertionError("synthetic checker reached write-capable file-open boundary")
        return open_os(file, flags, *args, **kwargs)

    with (
        patch.object(builtins, "open", readonly_builtin),
        patch.object(io, "open", readonly_io),
        patch.object(os, "open", readonly_os),
    ):
        yield


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
    _blocked_report(report)


def _blocked_report(report: dict[str, object]) -> None:
    _require(report["status"] == "CAPABILITY_NOT_QUALIFIED", "worker became operational")
    _require(report["remote_execution_enabled"] is False, "worker remote execution enabled")
    _require(report["qualified"] is False, "worker claimed qualification")
    _require(report["closure_trust"] == "NOT_ESTABLISHED", "worker claimed closure trust")
    for name in ("new_eda_starts", "new_simulations", "new_extractions", "new_reservations"):
        _require(report[name] == 0, "worker claimed operational side effects")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def _factory_inputs(request: contract.BindingScanRequest) -> tuple[bytes, bytes, bytes, bytes]:
    # Reuse shipped, explicitly fictional starter data. No developer profile,
    # runtime settings, journal, filesystem source or grant is loaded or created.
    starter = files("cadence_mcp_bridge").joinpath("operator_starter")
    environment = EnvironmentProfile.model_validate_json(
        starter.joinpath("environment.json").read_bytes()
    )
    registry = json.loads(starter.joinpath("designs.json").read_bytes())
    profile_data = registry["designs"][0]
    profile_data.update(
        design_id="synthetic-binding", work_copy_policy="owned_copy_only",
        allowed_analyses=["dc"], allowed_variables=["input"],
        allowed_measurements=["dc-output"],
    )
    profile_data["binding"].update(library=request.library, cell=request.cell, view=request.view)
    profile = DesignProfile.model_validate_json(json.dumps(profile_data))
    variable_data = registry["variable_sets"][0]["variables"][0]
    variable_data.update(logical_id="input", cadence_binding="qa_input")
    variables = DesignVariables.model_validate_json(json.dumps({
        "design_id": profile.design_id,
        "design_profile_sha256": canonical_digest(profile),
        "variables": [variable_data],
    }))
    ade = AdeExecutionRegistration.model_validate_json(json.dumps({
        "schema_version": 1, "design_id": profile.design_id,
        "analysis_id": "synthetic-binding-dc",
        "design_profile_sha256": canonical_digest(profile),
        "variable_set_sha256": canonical_digest(variables),
        "source_tree_sha256": "b" * 64, "ade_state_tree_sha256": "c" * 64,
        "static_statements_sha256": "d" * 64, "model_includes": [],
        "inputs": {
            "analysis": "dc", "mode": "saved_operating_point", "statement_sha256": "e" * 64,
        },
    }))
    reader = GenericReaderRegistration.model_validate_json(json.dumps({
        "schema_version": 1, "design_id": profile.design_id, "analysis_id": ade.analysis_id,
        "measurement_id": "dc-output", "ade_registration_sha256": canonical_digest(ade),
        "measurement_contract_sha256": "f" * 64,
        "nodes": [{"logical_id": "input", "selector": "/in"}],
        "sources": [], "transfer": None, "maximum_samples": 2,
    }))
    profile_raw = _canonical(environment.model_dump(mode="json"))
    library = environment.paths.workspace_root + "/" + request.library
    registration_raw = _canonical({
        "schema_version": 1, "identity_manifest_sha256": "a" * 64,
        "environment_sha256": hashlib.sha256(profile_raw).hexdigest(),
        "design_sha256": "b" * 64, "pdk_sha256": "c" * 64,
        "routes": [{
            "design_id": profile.design_id, "analysis_id": ade.analysis_id, "analysis": "dc",
            "profile": profile.model_dump(mode="json"),
            "variables": [v.model_dump(mode="json") for v in variables.variables],
            "source_cell": library + "/" + request.cell,
            "source_state": environment.paths.workspace_root + "/synthetic-binding-state",
            "model_files": [],
            "libraries": [{"name": request.library, "path": library, "tree_sha256": "d" * 64}],
            "ade": ade.model_dump(mode="json"), "reader": reader.model_dump(mode="json"),
        }],
    })
    request_raw = _canonical(request.model_dump(mode="json"))
    worker_raw = files("cadence_mcp_bridge").joinpath("_binding_observation.py").read_bytes()
    selection_raw = _canonical({
        "schema_version": 1, "design_id": profile.design_id, "analysis_id": ade.analysis_id,
        "profile_sha256": hashlib.sha256(profile_raw).hexdigest(),
        "registration_sha256": hashlib.sha256(registration_raw).hexdigest(),
        "request_sha256": hashlib.sha256(request_raw).hexdigest(),
        "collector_sha256": hashlib.sha256(contract.render_collector(request)).hexdigest(),
        "helper_sha256": hashlib.sha256(worker_raw.replace(b"\r\n", b"\n")).hexdigest(),
    })
    return profile_raw, registration_raw, selection_raw, request_raw


def _authenticated_factory(request: contract.BindingScanRequest) -> None:
    arguments = _factory_inputs(request)
    names = (
        "cadence_mcp_bridge._binding_observation", "cadence_mcp_bridge._native_copy",
        "cadence_mcp_bridge._shared_reservations", "cadence_mcp_bridge._native_eda_worker",
        "_cadence_binding_observation_retained",
        "binding_observation_copy", "binding_observation_reservations",
        "binding_observation_process",
    )
    poisoned = {name: ModuleType(name) for name in names}
    for module in poisoned.values():
        module.BindingObservationWorker = _forbidden
        module.authenticated_modules = _forbidden
        module.EdaWorker = _forbidden
        module.snapshot = _forbidden
        module.ReservationSession = _forbidden
    with contextlib.ExitStack() as poison:
        poison.enter_context(patch.dict(sys.modules, poisoned))
        for name, module in poisoned.items():
            if name.startswith("cadence_mcp_bridge."):
                poison.enter_context(patch.object(
                    cadence_mcp_bridge, name.rsplit(".", 1)[1], module, create=True,
                ))
        instance = bootstrap.construct_worker(*arguments)
        _require(type(instance) is not worker.BindingObservationWorker, "cached worker reused")
        with patch.object(type(instance), "_stage", _forbidden):
            _blocked_report(instance.observe(request.model_dump(mode="json")))
    selected = json.loads(arguments[2])
    selected["helper_sha256"] = "0" * 64
    # A wrong worker identity must reject before the first worker/helper compile.
    with patch.object(bootstrap, "compile", _forbidden, create=True):
        try:
            bootstrap.construct_worker(
                arguments[0], arguments[1], _canonical(selected), arguments[3],
            )
        except ValueError:
            pass
        else:
            raise ValueError("wrong selected worker digest accepted")


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


def _inert_storage_admin() -> None:
    _require(storage_admin.CONFIG_JSON is None, "package contains a VM admin configuration")
    _require(binding_storage_admin.admin is storage_admin, "installed admin resource identity")
    with patch.object(sys, "argv", ["storage-admin.py", "plan"]):
        try:
            storage_admin.main()
        except ValueError as error:
            _require(str(error) == "exported_fixed_configuration_required", "unexpected admin gate")
        else:
            raise ValueError("unconfigured administrator resource started")


def _inert_initializer_export(request: contract.BindingScanRequest) -> None:
    profile_raw, registration_raw, _, _ = _factory_inputs(request)
    raw = binding_initializer.helper_bytes(
        EnvironmentProfile.model_validate_json(profile_raw), json.loads(registration_raw),
    )
    namespace = {"__name__": "installed_inert_initializer"}
    exec(compile(raw, "installed_inert_initializer.py", "exec"), namespace)
    _require(set(namespace["SOURCES"]) == set(binding_initializer.RESOURCES),
             "initializer source inventory")
    for name, resource in binding_initializer.RESOURCES.items():
        expected = files("cadence_mcp_bridge").joinpath(resource).read_bytes().replace(
            b"\r\n", b"\n")
        _require(base64.b64decode(namespace["SOURCES"][name]) == expected,
                 "initializer installed bytes")
        _require(namespace["PINS"][name] == hashlib.sha256(expected).hexdigest(),
                 "initializer installed source pin")
    _require("loaded" not in namespace, "initializer export ran helper code")


def _inert_initializer_delta() -> None:
    # Validate installed delta arithmetic on literal synthetic rows under the
    # same no-write/process/transport guards; no successful rebind is implied.
    rows = [["directory", "", 0o775, 500, 500, "1.000000000"],
            ["file", "libInit.il", 0o664, 500, 500, "1.000000000", 0, "a" * 64, 1]]
    content = [["directory", ""], ["file", "libInit.il", 0, "a" * 64]]
    snapshot = dict(schema_version=2, tree_sha256=hashlib.sha256(_canonical(rows)).hexdigest(),
                    content_sha256=hashlib.sha256(_canonical(content)).hexdigest(),
                    entries=2, bytes=0, metadata=rows)
    _require(binding_initializer._snapshot_projection(snapshot) == rows,
             "installed initializer snapshot projection")
    try:
        binding_initializer._snapshot_projection({**snapshot, "tree_sha256": "0" * 64})
    except ValueError:
        pass
    else:
        raise ValueError("installed initializer accepted altered original snapshot")


def _inert_initializer_tty() -> None:
    # Literal parser-only synthetic envelope: no stage, privileged process,
    # successful metadata repair or real root provenance is established here.
    pins = {name: str(index) * 64 for index, name in enumerate((
        "frame_sha256", "helper_sha256", "plan_sha256",
    ), 1)}
    streams = {"stdout": b'{"synthetic":true}\n', "stderr": b""}
    envelope = {
        "schema_version": 1, "kind": "FIXED_INITIALIZER_TTY_TERMINAL",
        "status": "HELPER_SUCCEEDED", "returncode": 0,
        "helper_started": True, "files_retained": True, **pins,
        **{name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                  "base64": base64.b64encode(raw).decode("ascii")}
           for name, raw in streams.items()},
    }
    canonical = _canonical(envelope)
    _require(binding_initializer.parse_tty_terminal(canonical + b"\r\n", {"pins": pins})
             == (0, streams["stdout"], streams["stderr"]), "installed TTY parser CRLF")
    for bad in (b"noise\r\n" + canonical + b"\r\n", canonical + b"\r\n\r\n",
                canonical, canonical.replace(b'"returncode":0', b'"returncode":true')):
        try:
            binding_initializer.parse_tty_terminal(bad, {"pins": pins})
        except ValueError:
            pass
        else:
            raise ValueError("installed TTY parser accepted noise or invalid terminal")
    _require(binding_initializer.TTY_LIMITS["stdout_bytes"] == 8_388_608,
             "installed TTY stdout bound")
    _require(binding_initializer.TTY_LIMITS["stderr_bytes"] == 1_048_576,
             "installed TTY stderr bound")


def verify(workspace: Path) -> dict[str, object]:
    _verify_origins()
    workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
    with contextlib.ExitStack() as guards:
        guards.enter_context(_readonly_file_opens())
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
        _authenticated_factory(request)
        _pins()
        _inert_storage_admin()
        _inert_initializer_export(request)
        _inert_initializer_delta()
        _inert_initializer_tty()
    _require(not list(workspace.iterdir()), "synthetic checker wrote unexpected state")
    return {
        "status": "PASS",
        "scope": "INSTALLED_BINDING_OBSERVER_SYNTHETIC_NOT_CADENCE",
        "installed_origin": True,
        "file_open_guards": "READ_ONLY_BUILTINS_IO_OS_OPEN",
        "schema_cli": "INSTALLED_IN_PROCESS_WITH_SIDE_EFFECT_GUARDS",
        "observe_cli": "ABSENT",
        "successful_preparation": "NOT_TESTED_BY_THIS_CHECKER",
        "fixed_renderer": True,
        "strict_parser_rejected_frames": rejected_frames,
        "worker_observe": "BLOCKED_METHOD_WITH_SYNTHETIC_BOUND_ROUTE",
        "authenticated_worker_construction": "INSTALLED_FIXED_RESOURCE_FACTORY_SYNTHETIC_CONFIG",
        "cached_worker_and_helper_poisoning": "IGNORED_BY_FRESH_AUTHENTICATED_MODULES",
        "wrong_selected_worker_digest": "REJECTED_BEFORE_CODE_LOAD",
        "normalized_installed_helper_pins": True,
        "storage_admin_unconfigured_and_inert": True,
        "initializer_export_fixed_installed_sources_and_inert": True,
        "initializer_delta_installed_synthetic_snapshot_and_bad_pin": True,
        "initializer_tty_installed_parser_crlf_and_noise_rejection": True,
        "initializer_tty_current_vm_or_administrator_execution": "NOT_TESTED_BY_THIS_CHECKER",
        "initializer_successful_prospective_export": "NOT_TESTED_BY_THIS_CHECKER",
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
