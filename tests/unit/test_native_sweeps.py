"""Synthetic orchestration, retaining one authoritative native lifecycle/ledger."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_operator_operations import operator

from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.native_service import NativeOperationRequest
from cadence_mcp_bridge.native_sweeps import (
    NativeSweepQuery,
    NativeSweepRequest,
    NativeSweepSubmission,
    NativeSweepSupervisor,
)
from cadence_mcp_bridge.operator_operations import OperationProgress, prepare_plan
from cadence_mcp_bridge.runtime_context import load_runtime

__all__ = ["operator"]


@pytest.fixture
def sweep_native(operator):
    context, grant, request, settings = operator
    registry = json.loads(context.binding.design_registry.read_bytes())
    # Numeric qualification is explicit synthetic fixture data, never VM evidence.
    for v in registry["variable_sets"][0]["variables"]:
        if v["logical_id"] == "bias-n":
            v.update(
                mutation_policy="owned_copy_only",
                fixed_value=None,
                default=None,
                minimum="0.8",
                maximum="1.2",
                range_status="qualified",
                review_id="synthetic-region",
                step="0.1",
                step_policy="grid",
            )
    import hashlib

    from cadence_mcp_bridge.variable_contracts import DesignVariables, canonical_digest

    variable_hash = canonical_digest(
        DesignVariables.model_validate_json(json.dumps(registry["variable_sets"][0]))
    )
    variables = DesignVariables.model_validate_json(json.dumps(registry["variable_sets"][0]))
    axis = next(v for v in variables.variables if v.logical_id == "bias-n")
    registry["range_reviews"] = [
        dict(
            review_id="synthetic-region",
            design_id=variables.design_id,
            design_profile_sha256=variables.design_profile_sha256,
            variable_contract_sha256=canonical_digest(axis),
            evidence_id="synthetic-test-region",
            evidence_sha256="e" * 64,
            scope="operator_reviewed_project_numeric_contract",
        )
    ]
    for c in registry["analysis_contracts"]:
        c["variable_set_sha256"] = variable_hash
    context.binding.design_registry.write_bytes(
        type(context.contracts.designs)
        .model_validate_json(json.dumps(registry))
        .model_dump_json()
        .encode()
    )
    digest = hashlib.sha256(context.binding.design_registry.read_bytes()).hexdigest()
    runtime = json.loads(settings.read_bytes())
    runtime["contexts"][0]["design_sha256"] = digest
    settings.write_text(json.dumps(runtime))
    context = load_runtime(settings)[0]
    regions = tuple(
        r.model_copy(update={"minimum": "0.8", "maximum": "1.2"}) if r.logical_id == "bias-n" else r
        for r in grant.numeric_regions
    )
    grant = grant.model_copy(update={"design_sha256": digest, "numeric_regions": regions})
    store = AnalysisStore(context.binding.analysis_journal)

    class Native:
        def __init__(self):
            self.context, self.grant = context, grant
            self.lifecycle = SimpleNamespace(store=store)
            self.calls = []
            self.phase = "SUCCEEDED"
            self.changed = False

        def current(self):
            pass

        async def plan(self, requested):
            from cadence_mcp_bridge.operator_operations import OperationRequest

            requested = OperationRequest.model_validate_json(requested.model_dump_json())
            plan = prepare_plan(context, self.grant, canonical_digest(self.grant), requested, 100)
            if self.changed:
                plan = plan.model_copy(update={"runner_sha256": "c" * 64})
            return SimpleNamespace(plan=plan)

        async def observe(self, query, submission=None):
            if submission is not None:
                plan = (await self.plan(submission)).plan
                first = store.admit_operation(query.operation_id, plan, dispatch_intent=True)
                if first:
                    self.calls.append(query.operation_id)
                    before = store.operation(query.operation_id)
                    store.advance_operation(
                        query.operation_id,
                        before.progress,
                        OperationProgress(
                            phase=self.phase, remote_revision=1, provider_receipt_sha256="d" * 64
                        ),
                    )
            return SimpleNamespace(progress=store.operation(query.operation_id).progress)

        async def result(self, query):
            return SimpleNamespace(
                model_dump=lambda **kwargs: {"operation_id": query.operation_id, "value": 1.0}
            )

    native = Native()
    sweep = NativeSweepRequest(
        template=NativeOperationRequest.model_validate_json(request.model_dump_json()),
        variable_id="bias-n",
        values=("0.8", "1", "1.2"),
    )
    return native, sweep


async def admit(native, request):
    supervisor = NativeSweepSupervisor(native)
    planned = await supervisor.plan(request)
    query = NativeSweepQuery(sweep_id=str(uuid4()), expected_plan_sha256=planned.plan_sha256)
    submission = NativeSweepSubmission(**query.model_dump(), request=request)
    result = await supervisor.submit(submission)
    return supervisor, query, submission, result


@pytest.mark.asyncio
async def test_plan_and_admit_do_not_dispatch_then_restart_and_second_batch(sweep_native):
    native, request = sweep_native
    supervisor = NativeSweepSupervisor(native)
    planned = await supervisor.plan(request)
    assert planned.point_count == 3
    assert not native.lifecycle.store.path.exists()
    supervisor, query, submission, status = await admit(native, request)
    assert status.state == "PLANNED" and native.calls == []
    ids = tuple(p["operation_id"] for p in status.points)
    for i in range(3):
        supervisor = NativeSweepSupervisor(native)
        await supervisor.advance(query)
        # Parent retry is lookup-only, even when next untouched point exists.
        await supervisor.submit(submission)
        assert len(native.calls) == i + 1
    assert (await supervisor.status(query)).state == "SUCCEEDED"
    await supervisor.advance(query)
    assert len(native.calls) == 3
    assert tuple(p["operation_id"] for p in (await supervisor.status(query)).points) == ids
    assert len((await supervisor.result(query)).points) == 3
    second, second_query, _, _ = await admit(native, request)
    await second.advance(second_query)
    assert len(native.calls) == 4 and native.calls[-1] not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["FAILED", "EXTRACTION_FAILED", "RUNNING"])
async def test_partial_failure_or_running_stops_further_admission(sweep_native, phase):
    native, request = sweep_native
    native.phase = phase
    supervisor, query, submission, _ = await admit(native, request)
    first = await supervisor.advance(query)
    for _ in range(3):
        await NativeSweepSupervisor(native).advance(query)
        await supervisor.submit(submission)
    assert len(native.calls) == 1
    assert all(p["phase"] == "NOT_RUN" for p in first.points[1:])
    with pytest.raises(InvalidInputError):
        await supervisor.result(query)


@pytest.mark.asyncio
async def test_unknown_dispatch_outcome_is_lookup_only(sweep_native):
    native, request = sweep_native
    supervisor, query, _, status = await admit(native, request)
    point = status.points[0]
    plan = supervisor.store.read(query).plan.points[0]
    native.lifecycle.store.admit_operation(point["operation_id"], plan, dispatch_intent=True)
    assert (await supervisor.advance(query)).state == "STOPPED"
    assert native.calls == []


@pytest.mark.asyncio
async def test_changed_policy_and_corrupt_checkpoint_fail_without_dispatch(sweep_native):
    native, request = sweep_native
    supervisor, query, submission, _ = await admit(native, request)
    await supervisor.advance(query)
    native.changed = True
    with pytest.raises(InvalidInputError):
        await supervisor.advance(query)
    assert len(native.calls) == 1
    with native.lifecycle.store.connection(create=False) as c:
        c.execute("UPDATE native_sweeps_v1 SET document='{}'")
    with pytest.raises(InvalidInputError):
        await supervisor.submit(submission)
    assert len(native.calls) == 1


@pytest.mark.asyncio
async def test_axis_unit_fixed_scope_and_bounds_denied(sweep_native):
    native, request = sweep_native
    for values in (("0.7",), ("1.05",)):
        bad = request.model_copy(update={"values": values})
        with pytest.raises((ValueError, InvalidInputError)):
            await NativeSweepSupervisor(native).plan(bad)
    with pytest.raises(InvalidInputError):
        await NativeSweepSupervisor(native).plan(
            request.model_copy(update={"variable_id": "bias-p"})
        )
    for values in (("1", "1.0"), tuple(str(i) for i in range(17)), (1.0,), ("nan",)):
        with pytest.raises(ValidationError):
            NativeSweepRequest(template=request.template, variable_id="bias-n", values=values)
    assert native.calls == [] and not native.lifecycle.store.path.exists()


@pytest.mark.asyncio
async def test_mcp_sweep_schemas_plan_and_idempotent_submission(sweep_native):
    from pathlib import Path

    from cadence_mcp_bridge.native_server import register_native_tools
    from cadence_mcp_bridge.server import DesignContractServer

    native, request = sweep_native
    server = DesignContractServer("synthetic-native-sweeps")
    register_native_tools(server, native)
    names = {
        "cadence_plan_native_sweep",
        "cadence_submit_native_sweep",
        "cadence_advance_native_sweep",
        "cadence_native_sweep_status",
        "cadence_native_sweep_result",
        "cadence_evaluate_native_specification",
    }
    tools = {tool.name: tool for tool in await server.list_tools() if tool.name in names}
    snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "docs/contracts/MCP_NATIVE_SWEEP_SPEC_V1_SNAPSHOT.json"
        ).read_bytes()
    )
    assert {
        name: tool.model_dump(mode="json", by_alias=True) for name, tool in tools.items()
    } == snapshot["tools"]
    for tool in tools.values():
        assert tool.input_schema["additionalProperties"] is False
        assert not set(tool.input_schema["properties"]) & {
            "path",
            "command",
            "grant",
            "target",
            "host",
        }
    result = await server.call_tool(
        "cadence_plan_native_sweep", {"request": request.model_dump(mode="json")}
    )
    assert not result.is_error and result.structured_content is not None
    query = dict(
        sweep_id=str(uuid4()), expected_plan_sha256=result.structured_content["plan_sha256"]
    )
    payload = dict(**query, request=request.model_dump(mode="json"))
    for _ in range(2):
        submitted = await server.call_tool("cadence_submit_native_sweep", {"submission": payload})
        assert not submitted.is_error and submitted.structured_content["state"] == "PLANNED"
    assert native.calls == []
    advanced = await server.call_tool("cadence_advance_native_sweep", {"request": query})
    assert not advanced.is_error and len(native.calls) == 1
