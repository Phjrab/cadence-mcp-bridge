"""Explicit CLI lifecycle against a synthetic fixed transport."""

import hashlib
import json
import time
from uuid import uuid4

import pytest
from test_authenticated_provider import accounting, observation
from test_operator_operations import operator

from cadence_mcp_bridge import authenticated_provider as wire
from cadence_mcp_bridge.__main__ import main
from cadence_mcp_bridge.analysis_store import AnalysisStore
from cadence_mcp_bridge.operator_operations import prepare_plan

__all__ = ["operator"]


@pytest.fixture
def cli(operator, tmp_path, monkeypatch):
    context, grant, request, settings = operator
    paths = {name: tmp_path / (name + ".json") for name in ("grant", "request", "provider")}
    paths["grant"].write_bytes(grant.model_dump_json().encode())
    paths["request"].write_bytes(request.model_dump_json().encode())
    binding = wire.NativeProviderBinding(
        schema_version=1,
        identity_manifest_sha256="a" * 64,
        runtime_manifest_sha256=context.binding.runner_sha256,
    )
    paths["provider"].write_bytes(binding.model_dump_json().encode())

    def sha(name):
        return hashlib.sha256(paths[name].read_bytes()).hexdigest()

    plan = prepare_plan(context, grant, sha("grant"), request, int(time.time()))
    args = [
        "--settings",
        str(settings),
        "--context",
        context.binding.context_id,
        "--provider-binding",
        str(paths["provider"]),
        "--expected-provider-sha256",
        sha("provider"),
        "--operation-id",
        str(uuid4()),
        "--expected-plan-sha256",
        plan.plan_sha256,
    ]
    authority = ["--grant", str(paths["grant"]), "--expected-grant-sha256", sha("grant")]
    explicit = ["--request", str(paths["request"])]
    monkeypatch.setattr(wire, "_ssh", lambda _: ["fixed-ssh", "python", "-B"])
    return context, plan, args, authority, explicit, paths


def test_submit_retry_reconcile_share_one_durable_identity(cli, monkeypatch, capsys):
    context, plan, args, authority, explicit, paths = cli
    op = args[args.index("--operation-id") + 1]
    calls = []

    def transport(argv, raw, environment, **bounds):
        data = json.loads(raw)
        action = data["action"]
        calls.append(action)
        payload = (
            accounting(plan) if action == "authorize" else observation(op, plan, "DISPATCHED", 2)
        )
        return (
            0,
            wire._canonical(
                {
                    "schema_version": 1,
                    "action": action,
                    "payload": payload,
                    "runtime_manifest_sha256": plan.runner_sha256,
                    "identity_manifest_sha256": "a" * 64,
                }
            ),
            b"",
        )

    monkeypatch.setattr(wire, "run_fixed", transport)
    for action, tail in (
        ("submit", authority + explicit),
        ("submit", authority + explicit),
        ("reconcile", []),
    ):
        assert main(["operation", action, *args, *tail]) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["progress"]["phase"] == "DISPATCHED"
        assert result["operation_id"] == op and not result["simulation_retry"]
    assert calls == ["authorize", "accept", "lookup", "lookup"]
    assert AnalysisStore(context.binding.analysis_journal).operation(op).plan == plan


def test_binding_drift_denied_before_journal_or_contact(cli, monkeypatch, capsys):
    context, _, args, authority, explicit, paths = cli
    paths["provider"].write_bytes(b"{}")
    monkeypatch.setattr(wire, "run_fixed", lambda *a, **k: pytest.fail("must not contact"))
    assert main(["operation", "submit", *args, *authority, *explicit]) == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "native_operator_binding_changed"
    assert not context.binding.analysis_journal.exists() and not context.lock_path.exists()


def test_lost_acceptance_reply_never_resends_or_erases_intent(cli, monkeypatch, capsys):
    context, plan, args, authority, explicit, _ = cli
    calls = []

    def transport(argv, raw, environment, **bounds):
        data = json.loads(raw)
        action = data["action"]
        calls.append(action)
        if action == "accept":
            raise ValueError("synthetic lost acknowledgement")
        payload = accounting(plan) if action == "authorize" else None
        return (
            0,
            wire._canonical(
                {
                    "schema_version": 1,
                    "action": action,
                    "payload": payload,
                    "runtime_manifest_sha256": plan.runner_sha256,
                    "identity_manifest_sha256": "a" * 64,
                }
            ),
            b"",
        )

    monkeypatch.setattr(wire, "run_fixed", transport)
    assert main(["operation", "submit", *args, *authority, *explicit]) == 1
    first = json.loads(capsys.readouterr().out)
    assert first["reason"] == "native_provider_transport_unknown"
    assert main(["operation", "submit", *args, *authority, *explicit]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["progress"]["phase"] == "UNKNOWN_OUTCOME"
    assert calls == ["authorize", "accept", "lookup"]
    op = args[args.index("--operation-id") + 1]
    assert (
        AnalysisStore(context.binding.analysis_journal).operation(op).progress.phase
        == "UNKNOWN_OUTCOME"
    )
