"""Fixed transport/lifecycle integration tests; no remote access or EDA."""

import json
import time
from dataclasses import replace
from uuid import uuid4

import pytest
from test_operator_operations import operator as operator_fixture

from cadence_mcp_bridge import authenticated_provider as wire
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle
from cadence_mcp_bridge.operator_operations import OperationRejected, prepare_plan
from cadence_mcp_bridge.variable_contracts import canonical_digest

operator = operator_fixture


@pytest.fixture
def connected(operator, monkeypatch):
    context, grant, request, settings = operator
    plan = prepare_plan(context, grant, canonical_digest(grant), request, int(time.time()))
    provider = wire.AuthenticatedOperatorProvider(
        context,
        wire.NativeProviderBinding(
            schema_version=1,
            identity_manifest_sha256="a" * 64,
            runtime_manifest_sha256=context.binding.runner_sha256,
        ),
    )
    monkeypatch.setattr(
        wire,
        "_ssh",
        lambda env: ["ssh-test", "strict-host-key", env.ssh_alias, "python", "-E", "-s", "-B"],
    )
    return provider, plan, grant, request


def envelope(provider, action, payload):
    return wire._canonical(
        {
            "schema_version": 1,
            "action": action,
            "payload": payload,
            "runtime_manifest_sha256": provider.binding.runtime_manifest_sha256,
            "identity_manifest_sha256": provider.binding.identity_manifest_sha256,
        }
    )


def observation(op, plan, phase="DISPATCHED", revision=2):
    return {
        "operation_id": op,
        "plan_sha256": plan.plan_sha256,
        "resource_domain_sha256": plan.resource_domain_sha256,
        "ledger_ref": plan.ledger_ref,
        "progress": {
            "phase": phase,
            "remote_revision": revision,
            "provider_receipt_sha256": "e" * 64,
        },
    }


def accounting(plan):
    return {
        **{
            key: getattr(plan, key)
            for key in ("resource_domain_sha256", "ledger_ref", "runner_sha256", "grant_sha256")
        },
        "cumulative_attempts": 82,
        "cumulative_reserved_bytes": 9798942720,
        "grant_attempts": 0,
        "grant_reserved_bytes": 0,
        "attempt_ceiling": 500,
        "result_ceiling_bytes": 10737418240,
        "in_flight_reserved_bytes": 0,
        "logical_bytes": 100,
        "allocated_bytes": 4096,
        "filesystem_free_bytes": 20 * 1024**3,
        "filesystem_total_bytes": 40 * 1024**3,
    }


@pytest.mark.asyncio
async def test_fixed_argv_and_no_grant_writer_or_caller_path(connected, monkeypatch):
    provider, plan, grant, request = connected
    calls = []
    op = str(uuid4())

    def transport(argv, raw, env, **bounds):
        data = json.loads(raw)
        calls.append((argv, data, bounds))
        action = data["action"]
        payload = accounting(plan) if action == "authorize" else observation(op, plan)
        return 0, envelope(provider, action, payload), b""

    monkeypatch.setattr(wire, "run_fixed", transport)
    await provider.authorize(plan, grant)
    await provider.accept(op, plan)
    await provider.lookup(op, plan)
    await provider.cancel_pending(op, plan)
    assert [entry[1]["action"] for entry in calls] == [
        "authorize",
        "accept",
        "lookup",
        "cancel_pending",
    ]
    for argv, data, bounds in calls:
        assert argv[-3] == provider.runner and argv[-2] == plan.runner_sha256
        assert set(data) == {
            "schema_version",
            "action",
            "operation_id",
            "plan",
            "plan_sha256",
            "identity_manifest_sha256",
        }
        assert "grant_json" not in data and "operator_authority" not in data
        assert bounds == {"timeout": 60, "limit": 262144}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["timeout", "status", "stderr", "junk", "binding", "wrong-job", "absent"]
)
async def test_transport_failure_is_bounded_and_never_retried(connected, monkeypatch, failure):
    provider, plan, _, _ = connected
    op = str(uuid4())
    calls = []

    def transport(argv, raw, env, **bounds):
        calls.append(raw)
        if failure == "timeout":
            raise ValueError("private-path-token-and-log")
        payload = observation(str(uuid4()) if failure == "wrong-job" else op, plan)
        if failure == "absent":
            payload = None
        raw = envelope(provider, "accept", payload)
        if failure == "junk":
            raw = b"private broken log"
        if failure == "binding":
            value = json.loads(raw)
            value["runtime_manifest_sha256"] = "9" * 64
            raw = wire._canonical(value)
        return (
            (1 if failure == "status" else 0),
            raw,
            (b"private log" if failure == "stderr" else b""),
        )

    monkeypatch.setattr(wire, "run_fixed", transport)
    with pytest.raises(OperationRejected) as error:
        await provider.accept(op, plan)
    assert len(calls) == 1 and "private" not in str(error.value)


@pytest.mark.asyncio
async def test_timeout_after_local_intent_restart_only_looks_up(connected, monkeypatch):
    provider, plan, grant, request = connected
    op = str(uuid4())
    calls = []

    def transport(argv, raw, env, **bounds):
        data = json.loads(raw)
        action = data["action"]
        calls.append(action)
        if action == "accept":
            raise ValueError("synthetic response loss after dispatch")
        return (
            0,
            envelope(
                provider,
                action,
                accounting(plan)
                if action == "authorize"
                else None
                if action == "lookup" and len(calls) == 1
                else observation(op, plan),
            ),
            b"",
        )

    monkeypatch.setattr(wire, "run_fixed", transport)
    lifecycle = OperatorLifecycle(
        provider.context, AnalysisStore(provider.context.binding.analysis_journal), provider
    )
    with pytest.raises(OperationRejected):
        await lifecycle.submit(op, grant, canonical_digest(grant), request, plan.plan_sha256)
    assert lifecycle.read(op, plan.plan_sha256).progress.phase == "UNKNOWN_OUTCOME"
    restarted = OperatorLifecycle(provider.context, AnalysisStore(lifecycle.store.path), provider)
    assert (
        await restarted.submit(op, grant, canonical_digest(grant), request, plan.plan_sha256)
    ).progress.phase == "DISPATCHED"
    assert (
        await restarted.submit(op, grant, canonical_digest(grant), request, plan.plan_sha256)
    ).progress.phase == "DISPATCHED"
    assert calls == ["lookup", "authorize", "accept", "lookup", "lookup"]


@pytest.mark.asyncio
async def test_stale_plan_rejects_before_contact_or_journal(connected, monkeypatch):
    provider, plan, _, _ = connected
    monkeypatch.setattr(wire, "run_fixed", lambda *args, **kwargs: pytest.fail("must not contact"))
    with pytest.raises(OperationRejected):
        await provider.accept(str(uuid4()), plan.model_copy(update={"runner_sha256": "9" * 64}))
    assert not provider.context.binding.analysis_journal.exists()


def test_wrong_manifest_or_changed_environment_cannot_construct(connected):
    provider, _, _, _ = connected
    with pytest.raises(OperationRejected):
        wire.AuthenticatedOperatorProvider(
            provider.context,
            provider.binding.model_copy(update={"runtime_manifest_sha256": "9" * 64}),
        )
    wrong = replace(
        provider.context,
        binding=provider.context.binding.model_copy(update={"environment_sha256": "9" * 64}),
    )
    with pytest.raises(OperationRejected):
        wire.AuthenticatedOperatorProvider(wrong, provider.binding)
