"""Production result parsers and SDK summaries consume registered fresh policies.

All frames and ledgers here are disposable synthetic observations; no SSH runs.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from mcp import Client
from pydantic import ValidationError
from test_amplifier_sweeps import child
from test_bandwidth_study import artifact as bandwidth_artifact
from test_bias_range import payload as bias_payload
from test_offset_service import artifact as offset_artifact
from test_power_measurements import artifact as power_artifact
from test_slew_study import artifact as slew_artifact
from test_storage import Backend, snapshot
from test_storage import artifact as storage_artifact

from cadence_mcp_bridge.amplifier_sweeps import AmplifierChild
from cadence_mcp_bridge.bandwidth_study import RefinementExtraction
from cadence_mcp_bridge.bias_range import BiasExtraction
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.errors import RemoteFailureError
from cadence_mcp_bridge.offset_study import OffsetExtraction
from cadence_mcp_bridge.power_measurements import PowerCounter, PowerExtraction
from cadence_mcp_bridge.resource_policy import (
    FreshResourceCounter,
    RetainedResourceCounter,
    RetainedResourcePolicy,
)
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.slew_study import StepExtraction
from cadence_mcp_bridge.ssh_backend import OpenSshBackend
from cadence_mcp_bridge.storage import StorageSnapshot, StorageSupervisor, snapshot_digest

CAMPAIGN = "dba8b62e-8518-4e68-8b27-6f8f76ef84bf"
OTHER_CAMPAIGN = "bda7bfc6-16e4-482e-a0e4-8b9a31f5c783"
CHILD = uuid5(NAMESPACE_URL, "synthetic-fresh-policy-consumer")
KINDS = ("power", "bandwidth", "bias", "slew", "offset", "amplifier")
MODELS = {
    "power": PowerExtraction,
    "bandwidth": RefinementExtraction,
    "bias": BiasExtraction,
    "slew": StepExtraction,
    "offset": OffsetExtraction,
    "amplifier": AmplifierChild,
}


def counters(value: Any) -> list[dict[str, Any]]:
    found = []
    if isinstance(value, dict):
        if "counter" in value:
            found.append(value["counter"])
        for nested in value.values():
            found.extend(counters(nested))
    elif isinstance(value, list):
        for nested in value:
            found.extend(counters(nested))
    return found


def receipt(kind: str, fresh: bool = True) -> dict[str, Any]:
    value = {
        "power": power_artifact,
        "bandwidth": lambda: bandwidth_artifact().model_dump(mode="json"),
        "bias": bias_payload,
        "slew": lambda: slew_artifact().model_dump(mode="json"),
        "offset": lambda: offset_artifact().model_dump(mode="json"),
        "amplifier": lambda: child(CHILD, "dc", "0.319", "a" * 64, 77).model_dump(mode="json"),
    }[kind]()
    if fresh:
        for counter in counters(value):
            counter.update(campaign_id=CAMPAIGN, policy={
                "campaign_id": CAMPAIGN, "attempt_ceiling": 100,
                "result_ceiling_bytes": 10 * 1024**3,
            })
        if kind == "power":
            value["counter"].update(count=1, result_reserved_bytes=65536)
            value["counter"]["policy"].update(attempt_ceiling=2, result_ceiling_bytes=131072)
    return value


@pytest.mark.parametrize("kind", KINDS)
def test_production_models_preserve_legacy_shape_and_fresh_policy(kind: str) -> None:
    old = receipt(kind, fresh=False)
    legacy = MODELS[kind].model_validate_json(json.dumps(old))
    assert counters(legacy.model_dump(mode="json")) == counters(old)
    assert all(set(counter) == {"campaign_id", "count", "result_reserved_bytes"}
               for counter in counters(old))
    fresh = receipt(kind)
    result = MODELS[kind].model_validate_json(json.dumps(fresh))
    assert counters(result.model_dump(mode="json")) == counters(fresh)
    for counter in counters(fresh):
        assert FreshResourceCounter.model_validate(counter).policy.campaign_id == CAMPAIGN
    if kind == "power":
        assert isinstance(result.counter, FreshResourceCounter)
        assert isinstance(legacy.counter, PowerCounter)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("change", ["missing-policy", "campaign", "attempts", "bytes", "bool"])
def test_real_consumer_models_reject_unbound_and_exceeded_policies(kind: str, change: str) -> None:
    value = receipt(kind)
    counter = counters(value)[0]
    if change == "missing-policy":
        counter.pop("policy")
    elif change == "campaign":
        counter["policy"]["campaign_id"] = OTHER_CAMPAIGN
    elif change == "attempts":
        counter["policy"]["attempt_ceiling"] = counter["count"] - 1
    elif change == "bytes":
        counter["policy"]["result_ceiling_bytes"] = counter["result_reserved_bytes"] - 1
    else:
        counter["count"] = True
    with pytest.raises(ValidationError):
        MODELS[kind].model_validate_json(json.dumps(value))


@pytest.mark.parametrize("kind", ["bandwidth", "bias", "slew", "offset"])
@pytest.mark.parametrize("change", ["legacy", "campaign", "policy"])
def test_composite_receipts_cannot_mix_domains_or_registered_policies(
    kind: str, change: str,
) -> None:
    value = receipt(kind)
    counter = counters(value)[-1]
    if change == "legacy":
        counter.pop("policy")
        counter["campaign_id"] = "AUTO-PHASE-01"
    elif change == "campaign":
        counter["campaign_id"] = counter["policy"]["campaign_id"] = OTHER_CAMPAIGN
    else:
        counter["policy"]["attempt_ceiling"] = 99
    with pytest.raises(ValidationError, match="shared registered resource policy"):
        MODELS[kind].model_validate_json(json.dumps(value))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["power", "bandwidth", "slew", "offset", "amplifier"])
@pytest.mark.parametrize("valid", [True, False])
async def test_fixed_ssh_result_consumers_validate_fresh_receipts(
    kind: str, valid: bool, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cadence_mcp_bridge.bandwidth_study import REFERENCE_OPERATION as bandwidth_operation
    from cadence_mcp_bridge.offset_study import REFERENCE_OPERATION as offset_operation
    from cadence_mcp_bridge.power_measurements import REFERENCE_OPERATION as power_operation
    from cadence_mcp_bridge.slew_study import REFERENCE_OPERATION as slew_operation

    value = receipt(kind)
    if not valid:
        counters(value)[0].pop("policy")
    calls: list[tuple[Any, ...]] = []
    backend = OpenSshBackend(BridgeConfig())

    def invoke(*args: Any) -> str:
        calls.append(args)
        return json.dumps(value)

    monkeypatch.setattr(backend, "_invoke_at_path", invoke)
    method, identity = {
        "power": (backend.power_extraction_result, power_operation),
        "bandwidth": (backend.bandwidth_refinement_result, bandwidth_operation),
        "slew": (backend.slew_step_result, slew_operation),
        "offset": (backend.offset_study_result, offset_operation),
        "amplifier": (backend.amplifier_result, CHILD),
    }[kind]
    if valid:
        result = await method(identity)
        assert counters(result.model_dump(mode="json")) == counters(value)
    else:
        with pytest.raises(RemoteFailureError):
            await method(identity)
    assert len(calls) == 1
    assert calls[0][1] == "result"


@pytest.mark.asyncio
@pytest.mark.parametrize("consumed", [False, True])
async def test_storage_supervisor_and_sdk_report_registered_lower_ceiling(consumed: bool) -> None:
    raw = snapshot(storage_artifact(1, "EVIDENCE_REQUIRED")).model_dump(mode="json")
    raw.update(contract_version=2, spectre_attempts=1 if consumed else 0,
               reserved_result_bytes=65536 if consumed else 0, result_ceiling_bytes=131072,
               ledger_policy={"campaign_id": CAMPAIGN, "attempt_ceiling": 2,
                              "result_ceiling_bytes": 131072})
    value = StorageSnapshot.model_validate_json(json.dumps(raw))
    value = value.model_copy(update={"snapshot_id": snapshot_digest(value)})
    backend = Backend(value)
    result = await StorageSupervisor(backend).summary()
    assert result.result_ceiling_bytes == value.ledger_policy.result_ceiling_bytes == 131072
    assert result.reserved_result_bytes == raw["reserved_result_bytes"]
    assert result.spectre_attempts == raw["spectre_attempts"]
    async with Client(create_server(CadenceService(backend))) as client:  # type: ignore[arg-type]
        output = await client.call_tool("cadence_storage_summary", {})
        assert not output.is_error
        assert output.structured_content["result_ceiling_bytes"] == 131072
        assert output.structured_content["reserved_result_bytes"] == raw["reserved_result_bytes"]
    assert backend.executions == 0



def retained_receipt(kind: str) -> dict[str, Any]:
    value = receipt(kind, fresh=False)
    policy = RetainedResourcePolicy(
        campaign_id="AUTO-PHASE-01", attempt_ceiling=500, result_ceiling_bytes=16 * 1024**3,
        policy_sha256="1625e131118a0c0b4ff466c567d8a79bcb050dbf798505c23685e7b5604adac0",
    ).model_dump()
    for counter in counters(value):
        counter["policy"] = dict(policy)
    if kind == "power":
        value["counter"].update(count=102, result_reserved_bytes=12483297280)
    return value


@pytest.mark.parametrize("kind", KINDS)
def test_production_consumers_require_and_preserve_retained_v6_policy(kind: str) -> None:
    value = retained_receipt(kind)
    result = MODELS[kind].model_validate_json(json.dumps(value))
    assert counters(result.model_dump(mode="json")) == counters(value)
    for counter in counters(value):
        assert RetainedResourceCounter.model_validate(counter).policy.result_ceiling_bytes == (
            16 * 1024**3
        )
    if kind == "power":
        assert isinstance(result.counter, RetainedResourceCounter)


@pytest.mark.parametrize("change", ["missing-policy", "hash", "limit", "bytes", "attempts", "bool"])
def test_above_historical_counter_cannot_implicitly_gain_retained_v6_policy(change: str) -> None:
    value = retained_receipt("power")
    counter = value["counter"]
    if change == "missing-policy":
        counter.pop("policy")
    elif change == "hash":
        counter["policy"]["policy_sha256"] = "0" * 64
    elif change == "limit":
        counter["policy"]["result_ceiling_bytes"] = 10 * 1024**3
    elif change == "bytes":
        counter["result_reserved_bytes"] = 16 * 1024**3 + 1
    elif change == "attempts":
        counter["count"] = 501
    else:
        counter["count"] = True
    with pytest.raises(ValidationError):
        PowerExtraction.model_validate_json(json.dumps(value))


@pytest.mark.parametrize("kind", ["bandwidth", "bias", "slew", "offset"])
def test_retained_and_legacy_observations_cannot_splice_in_one_receipt(kind: str) -> None:
    value = retained_receipt(kind)
    counters(value)[-1].pop("policy")
    with pytest.raises(ValidationError, match="shared registered resource policy"):
        MODELS[kind].model_validate_json(json.dumps(value))


@pytest.mark.asyncio
async def test_registered_v3_storage_supervisor_sdk_keep_vm_ceiling_and_consumption() -> None:
    raw = snapshot(storage_artifact(1, "EVIDENCE_REQUIRED")).model_dump(mode="json")
    raw.update(contract_version=3, spectre_attempts=102, reserved_result_bytes=12483297280,
               result_ceiling_bytes=16 * 1024**3,
               ledger_policy=retained_receipt("power")["counter"]["policy"])
    value = StorageSnapshot.model_validate_json(json.dumps(raw))
    value = value.model_copy(update={"snapshot_id": snapshot_digest(value)})
    backend = Backend(value)
    result = await StorageSupervisor(backend).summary()
    assert result.result_ceiling_bytes == 17179869184
    assert result.reserved_result_bytes == 12483297280 and result.spectre_attempts == 102
    assert result.disk_floor_bytes == 2147483648 and result.disk_floor_status == "OK"
    async with Client(create_server(CadenceService(backend))) as client:  # type: ignore[arg-type]
        output = await client.call_tool("cadence_storage_summary", {})
        assert not output.is_error
        assert output.structured_content["result_ceiling_bytes"] == 17179869184
        assert output.structured_content["reserved_result_bytes"] == 12483297280
        assert output.structured_content["spectre_attempts"] == 102
    assert backend.executions == 0


def test_retained_storage_policy_cannot_be_used_as_fresh_or_implicit_legacy() -> None:
    raw = snapshot().model_dump(mode="json")
    raw.update(spectre_attempts=102, reserved_result_bytes=12483297280,
               result_ceiling_bytes=16 * 1024**3,
               ledger_policy=retained_receipt("power")["counter"]["policy"])
    for version in (1, 2):
        raw["contract_version"] = version
        with pytest.raises(ValidationError):
            StorageSnapshot.model_validate_json(json.dumps(raw))
    raw["contract_version"] = 3
    raw["ledger_policy"]["policy_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        StorageSnapshot.model_validate_json(json.dumps(raw))
