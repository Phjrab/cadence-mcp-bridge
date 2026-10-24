"""Disposable local construction; no remote installation or runtime qualification."""

import copy
import hashlib
import io
import json
import socket
import subprocess
import sys
import types
from importlib.resources import files

import pytest
from test_native_runtime import operator, operator_base, registered

from cadence_mcp_bridge import binding_observation_bootstrap as bootstrap
from cadence_mcp_bridge.binding_observation import BindingScanRequest, render_collector
from cadence_mcp_bridge.designs import DesignProfile
from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration
from cadence_mcp_bridge.native_runtime import projection
from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest

__all__ = ["operator", "operator_base", "registered"]


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def descriptions(registered):
    context, registration, _ = registered
    profile_raw = canonical(context.contracts.environment.model_dump(mode="json"))
    compiled = projection(context, registration)
    compiled["environment_sha256"] = digest(profile_raw)
    registration_raw = canonical(compiled)
    route = compiled["routes"][0]
    request = dict(
        schema_version=1,
        observation_id="2c07d8a3-4f07-4fa9-b65c-c78d6257812d",
        nonce="e" * 64,
        library=route["profile"]["binding"]["library"],
        cell=route["profile"]["binding"]["cell"],
        view="schematic",
        variables=[
            {key: variable[key] for key in ("logical_id", "cadence_binding")}
            for variable in route["variables"]
        ],
    )
    request_raw = canonical(request)
    selection = dict(
        schema_version=1, design_id=route["design_id"], analysis_id=route["analysis_id"],
        profile_sha256=digest(profile_raw), registration_sha256=digest(registration_raw),
        request_sha256=digest(request_raw),
        collector_sha256=digest(render_collector(BindingScanRequest.model_validate_json(request_raw))),
        helper_sha256=digest(files("cadence_mcp_bridge").joinpath(
            "_binding_observation.py",
        ).read_bytes().replace(b"\r\n", b"\n")),
    )
    return [profile_raw, registration_raw, canonical(selection), request_raw]


def forbidden(*args, **kwargs):
    pytest.fail("local construction must not dispatch, mutate state or claim authority")


def test_fixed_installed_bytes_construct_fresh_private_disabled_worker(
    descriptions, tmp_path, monkeypatch,
):
    import os

    from cadence_mcp_bridge import binding_observation_claim

    before = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(os, "mkdir", forbidden)
    monkeypatch.setattr(os, "open", forbidden)
    monkeypatch.setattr(binding_observation_claim, "claim", forbidden)
    first = bootstrap.construct_worker(*descriptions)
    second = bootstrap.construct_worker(*descriptions)
    assert type(first) is not type(second)
    assert first.copying is not second.copying and first.accounting is not second.accounting
    assert first.copying.MAX_ENTRIES == 64 and first.copying.MAX_BYTES == 1_048_576
    assert type(first).__module__ == "_cadence_binding_observation_retained"
    assert type(first).__module__ not in sys.modules
    assert first.selection == json.loads(descriptions[2])
    outcome = first.observe(json.loads(descriptions[3]))
    assert outcome["status"] == "CAPABILITY_NOT_QUALIFIED"
    assert outcome["qualified"] is False and outcome["closure_trust"] == "NOT_ESTABLISHED"
    assert outcome["remote_execution_enabled"] is False
    assert outcome["new_eda_starts"] == outcome["new_simulations"] == 0
    assert outcome["new_extractions"] == outcome["new_reservations"] == 0
    after = {str(path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after


@pytest.mark.parametrize("document", range(4))
@pytest.mark.parametrize("kind", ["extra", "boolean_schema", "duplicate", "noncanonical",
                                  "malformed", "nonfinite", "list", "oversize", "not_bytes"])
def test_closed_canonical_bounded_json_is_checked_before_code_evaluation(
    descriptions, monkeypatch, document, kind,
):
    args = list(descriptions)
    value = json.loads(args[document])
    if kind == "extra":
        args[document] = canonical({**value, "trusted": True})
    elif kind == "boolean_schema":
        args[document] = canonical({**value, "schema_version": True})
    elif kind == "duplicate":
        args[document] = b'{"schema_version":1,' + args[document][1:]
    elif kind == "noncanonical":
        args[document] += b"\n"
    elif kind == "malformed":
        args[document] = b'{"broken":'
    elif kind == "nonfinite":
        args[document] = b'{"schema_version":NaN}'
    elif kind == "list":
        args[document] = b"[]"
    elif kind == "oversize":
        args[document] = b" " * (262_145 if document == 1 else 65_537)
    else:
        args[document] = args[document].decode("ascii")
    monkeypatch.setattr(bootstrap, "compile", forbidden, raising=False)
    with pytest.raises(ValueError):
        bootstrap.construct_worker(*args)


@pytest.mark.parametrize("field", ["profile_sha256", "registration_sha256", "request_sha256",
                                   "helper_sha256", "collector_sha256"])
def test_selected_digests_authenticate_input_and_retained_code(descriptions, monkeypatch, field):
    selection = json.loads(descriptions[2])
    selection[field] = "0" * 64
    descriptions[2] = canonical(selection)
    if field != "collector_sha256":
        monkeypatch.setattr(bootstrap, "compile", forbidden, raising=False)
    with pytest.raises(ValueError, match="digest"):
        bootstrap.construct_worker(*descriptions)


@pytest.mark.parametrize("resource", ["_binding_observation.py", "_native_copy.py",
                                      "_shared_reservations.py", "_native_eda_worker.py"])
def test_changed_installed_resource_rejects_before_compiling_any_source(
    descriptions, monkeypatch, resource,
):
    package = files("cadence_mcp_bridge")
    reads = []

    class Resource:
        def __init__(self, name=None):
            self.name = name

        def joinpath(self, name):
            reads.append(name)
            return Resource(name)

        def open(self, mode):
            assert mode == "rb"
            raw = package.joinpath(self.name).read_bytes()
            if self.name == resource:
                raw += b"\nraise RuntimeError('changed bytes cannot execute')\n"
            return io.BytesIO(raw)

    monkeypatch.setattr(bootstrap, "files", lambda package_name: Resource())
    monkeypatch.setattr(bootstrap, "compile", forbidden, raising=False)
    with pytest.raises(ValueError, match="digest"):
        bootstrap.construct_worker(*descriptions)
    assert set(reads) == {
        "_binding_observation.py", "_native_copy.py", "_shared_reservations.py",
        "_native_eda_worker.py",
    }


@pytest.mark.parametrize("kind", ["oversize", "empty", "relabelled"])
def test_resource_bounds_and_fixed_pins_cannot_be_selected_by_json(
    descriptions, monkeypatch, kind,
):
    package = files("cadence_mcp_bridge")

    class Resource:
        def __init__(self, name=None):
            self.name = name

        def joinpath(self, name):
            return Resource(name)

        def open(self, mode):
            assert mode == "rb"
            if self.name == "_native_copy.py":
                raw = b"x" * 131_073 if kind == "oversize" else b""
                if kind == "relabelled":
                    raw = b"raise RuntimeError('caller-selected digest cannot authorize helper')"
                return io.BytesIO(raw)
            return package.joinpath(self.name).open(mode)

    monkeypatch.setattr(bootstrap, "files", lambda package_name: Resource())
    monkeypatch.setattr(bootstrap, "compile", forbidden, raising=False)
    with pytest.raises(ValueError, match="code_bound|helper_digest"):
        bootstrap.construct_worker(*descriptions)


def test_cached_worker_and_helpers_never_supply_constructed_code(descriptions, monkeypatch):
    import cadence_mcp_bridge

    poison = types.ModuleType("poisoned_namesake")
    poison.BindingObservationWorker = forbidden
    poison.render_collector = forbidden
    poison.authenticated_modules = forbidden
    for name in (
        "_binding_observation", "_native_copy", "_shared_reservations", "_native_eda_worker",
    ):
        monkeypatch.setitem(sys.modules, "cadence_mcp_bridge." + name, poison)
        monkeypatch.setattr(cadence_mcp_bridge, name, poison, raising=False)
    monkeypatch.setitem(sys.modules, "_cadence_binding_observation_retained", poison)
    worker = bootstrap.construct_worker(*descriptions)
    assert worker.observe(json.loads(descriptions[3]))["new_eda_starts"] == 0
    assert type(worker) is not poison.BindingObservationWorker
    assert sys.modules["_cadence_binding_observation_retained"] is poison


@pytest.mark.parametrize("kind", ["nested_extra", "missing_route", "duplicate_route",
                                  "source_escape", "incomplete_request", "wrong_binding"])
def test_closed_projection_and_complete_registered_request_are_required(
    descriptions, monkeypatch, kind,
):
    args = copy.deepcopy(descriptions)
    registration = json.loads(args[1])
    selection = json.loads(args[2])
    request = json.loads(args[3])
    route = registration["routes"][0]
    if kind == "nested_extra":
        route["ade"]["trusted"] = True
    elif kind == "missing_route":
        selection["analysis_id"] = "unregistered"
    elif kind == "duplicate_route":
        registration["routes"].append(route)
    elif kind == "source_escape":
        route["source_state"] = "/not-registered/saved-state"
    elif kind == "incomplete_request":
        request["variables"] = request["variables"][:-1]
    else:
        request["variables"][0]["cadence_binding"] = "WrongBinding"
    args[1], args[3] = canonical(registration), canonical(request)
    selection["registration_sha256"] = digest(args[1])
    selection["request_sha256"] = digest(args[3])
    args[2] = canonical(selection)
    monkeypatch.setattr(bootstrap, "compile", forbidden, raising=False)
    with pytest.raises(ValueError):
        bootstrap.construct_worker(*args)


@pytest.mark.parametrize("explicit_empty_set", [False, True])
def test_unselected_route_preserves_absent_or_explicit_empty_variable_set(
    descriptions, explicit_empty_set,
):
    registration = json.loads(descriptions[1])
    route = copy.deepcopy(registration["routes"][0])
    route["design_id"] = "unselected-empty"
    route["analysis_id"] = "unselected-empty-dc"
    route["profile"]["design_id"] = route["design_id"]
    route["profile"]["allowed_variables"] = []
    profile = DesignProfile.model_validate_json(canonical(route["profile"]))
    route["variables"] = []
    variables = DesignVariables(
        design_id=route["design_id"], design_profile_sha256=canonical_digest(profile),
        variables=(),
    )
    route["ade"].update(
        design_id=route["design_id"], analysis_id=route["analysis_id"],
        design_profile_sha256=canonical_digest(profile),
        variable_set_sha256=canonical_digest(variables) if explicit_empty_set else None,
    )
    ade = AdeExecutionRegistration.model_validate_json(canonical(route["ade"]))
    route["reader"].update(
        design_id=route["design_id"], analysis_id=route["analysis_id"],
        ade_registration_sha256=canonical_digest(ade),
    )
    registration["routes"].append(route)
    registration["routes"].sort(key=lambda item: (item["design_id"], item["analysis_id"]))
    descriptions[1] = canonical(registration)
    selection = json.loads(descriptions[2])
    selection["registration_sha256"] = digest(descriptions[1])
    descriptions[2] = canonical(selection)
    worker = bootstrap.construct_worker(*descriptions)
    assert worker.observe(json.loads(descriptions[3]))["status"] == "CAPABILITY_NOT_QUALIFIED"
