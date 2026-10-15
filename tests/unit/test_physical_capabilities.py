"""Physical inventory must not turn presence, errors or fixtures into qualification."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge.physical_capabilities import (
    CAPABILITIES,
    FACETS,
    PhysicalCapabilityInventory,
    PhysicalCapabilityObservation,
    PhysicalFacetAssessment,
    PhysicalScope,
    assess_physical_capabilities,
)

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)
SCOPE = PhysicalScope(
    environment_id="fixture-vm",
    environment_sha256="1" * 64,
    pdk_id="fixture-pdk",
    pdk_sha256="2" * 64,
)


def observation(**overrides: Any) -> PhysicalCapabilityObservation:
    data = {
        "capability": "drc",
        "facet": "installation",
        "outcome": "present",
        "reason": "presence_observed",
        "subject_sha256": "3" * 64,
        "evidence": {
            "evidence_id": "fixture-record",
            "scope": SCOPE.model_dump(mode="json"),
            "origin": "current_vm",
            "observed_at": NOW.isoformat(),
            "evidence_sha256": "4" * 64,
            "source_sha256": "5" * 64,
        },
    }
    data.update(overrides)
    return PhysicalCapabilityObservation.model_validate_json(json.dumps(data))


def assess(*items: PhysicalCapabilityObservation) -> dict[str, PhysicalFacetAssessment]:
    report = assess_physical_capabilities(
        PhysicalCapabilityInventory(scope=SCOPE, observations=items), assessed_at=NOW
    )
    return {f.facet: f for c in report.capabilities if c.capability == "drc" for f in c.facets}


def test_empty_inventory_explicitly_covers_unobserved_capabilities() -> None:
    report = assess_physical_capabilities(PhysicalCapabilityInventory(scope=SCOPE), assessed_at=NOW)
    assert tuple(c.capability for c in report.capabilities) == CAPABILITIES
    for capability in report.capabilities:
        assert tuple(f.facet for f in capability.facets) == FACETS
        assert [f.status for f in capability.facets] == [
            "UNKNOWN",
            "UNKNOWN",
            "UNKNOWN",
            "LICENSE_UNVERIFIED",
            "EXECUTION_UNVERIFIED",
        ]
        assert not capability.execution_qualified
        assert not capability.signoff_qualified
    assert not report.execution_authorized
    assert not report.remote_contact


def test_observed_tools_interfaces_decks_do_not_qualify_execution_or_license() -> None:
    facets = assess(
        observation(observed_version="1.2.3"),
        observation(facet="interface", interface_id="bounded-help-v1"),
        observation(facet="deck"),
    )
    assert [facets[f].status for f in FACETS] == [
        "INSTALLED_OBSERVED",
        "INTERFACE_OBSERVED",
        "DECK_OBSERVED",
        "LICENSE_UNVERIFIED",
        "EXECUTION_UNVERIFIED",
    ]


@pytest.mark.parametrize(
    "reason",
    [
        "read_error",
        "permission_denied",
        "timeout",
        "malformed_response",
        "not_found_in_bounded_scope",
    ],
)
def test_failed_or_bounded_missing_reads_are_unknown_not_absent(reason: str) -> None:
    result = assess(observation(outcome="error", reason=reason, subject_sha256=None))
    assert result["installation"].status == "UNKNOWN"
    assert result["installation"].reason == reason


@pytest.mark.parametrize(
    "reason", ["registered_binding_missing", "unsupported_registered_combination"]
)
def test_explicit_configuration_blocker_is_distinct_from_read_error(reason: str) -> None:
    result = assess(observation(outcome="blocked", reason=reason, subject_sha256=None))
    assert result["installation"].status == "BLOCKED"
    assert result["installation"].reason == reason


@pytest.mark.parametrize("facet", ["license", "execution"])
def test_inventory_cannot_claim_license_checkout_or_execution(facet: str) -> None:
    with pytest.raises(ValidationError, match="cannot establish license or execution"):
        observation(facet=facet)


@pytest.mark.parametrize(
    "origin,reason",
    [
        ("synthetic_fixture", "synthetic_evidence_only"),
        ("repository_contract", "repository_contract_only"),
    ],
)
def test_fixture_and_contract_evidence_remain_visible_without_actual_vm_promotion(
    origin: str, reason: str
) -> None:
    evidence = observation().evidence.model_dump(mode="json") | {"origin": origin}
    item = observation(evidence=evidence)
    result = assess(item)
    assert result["installation"].status == "UNKNOWN"
    assert result["installation"].reason == reason
    report = assess_physical_capabilities(
        PhysicalCapabilityInventory(scope=SCOPE, observations=(item,)), assessed_at=NOW
    )
    assert report.observations == (item,)
    assert report.observations[0].evidence.origin == origin


@pytest.mark.parametrize(
    "age,expected", [(86400, "INSTALLED_OBSERVED"), (86401, "UNKNOWN"), (-1, "UNKNOWN")]
)
def test_observation_freshness_is_explicit_and_bounded(age: int, expected: str) -> None:
    evidence = observation().evidence.model_dump(mode="json") | {
        "origin": "retained_vm",
        "observed_at": (NOW - timedelta(seconds=age)).isoformat(),
    }
    result = assess(observation(evidence=evidence))
    assert result["installation"].status == expected
    if age > 86400:
        assert result["installation"].reason == "stale_observation"
    elif age < 0:
        assert result["installation"].reason == "observation_after_assessment"


@pytest.mark.parametrize("field", ["environment_id", "environment_sha256", "pdk_id", "pdk_sha256"])
def test_different_vm_or_pdk_evidence_cannot_be_combined(field: str) -> None:
    evidence = observation().evidence.model_dump(mode="json")
    evidence["scope"][field] = "7" * 64 if field.endswith("sha256") else "another-binding"
    with pytest.raises(ValidationError, match="binding differs"):
        PhysicalCapabilityInventory(scope=SCOPE, observations=(observation(evidence=evidence),))


def test_duplicate_facet_does_not_silently_replace_conflicting_evidence() -> None:
    with pytest.raises(ValidationError, match="duplicate capability facet"):
        PhysicalCapabilityInventory(scope=SCOPE, observations=(observation(), observation()))


@pytest.mark.parametrize(
    "changes",
    [
        {"subject_sha256": None},
        {"subject_sha256": "not-a-hash"},
        {"facet": "interface"},
        {"interface_id": "arbitrary-path"},
        {"observed_version": "/private/tool"},
        {"command": "arbitrary-command"},
        {"status": "VERIFIED"},
        {"outcome": "error", "reason": "presence_observed", "subject_sha256": None},
        {"outcome": "blocked", "reason": "read_error", "subject_sha256": None},
        {"outcome": "not_assessed", "reason": "not_assessed"},
    ],
)
def test_observation_contract_rejects_unbound_or_misleading_claims(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        observation(**changes)


def test_missing_probe_stays_unverified_without_losing_reason() -> None:
    result = assess(
        observation(
            facet="license",
            outcome="not_assessed",
            reason="no_approved_read_interface",
            subject_sha256=None,
        )
    )
    assert result["license"].status == "LICENSE_UNVERIFIED"
    assert result["license"].reason == "no_approved_read_interface"


def test_no_verified_state_can_be_deserialized() -> None:
    with pytest.raises(ValidationError):
        PhysicalFacetAssessment(facet="deck", status="VERIFIED", reason="presence_observed")  # type: ignore[arg-type]


def test_hash_and_evidence_survive_local_json_round_trip() -> None:
    inventory = PhysicalCapabilityInventory(scope=SCOPE, observations=(observation(),))
    first = assess_physical_capabilities(inventory, assessed_at=NOW)
    copied = PhysicalCapabilityInventory.model_validate_json(inventory.model_dump_json())
    second = assess_physical_capabilities(copied, assessed_at=NOW)
    assert first == second
    assert first.observations[0].evidence.evidence_sha256 == "4" * 64
    changed = PhysicalCapabilityInventory(
        scope=SCOPE, observations=(observation(subject_sha256="6" * 64),)
    )
    assert assess_physical_capabilities(changed, assessed_at=NOW).inventory_sha256 != (
        first.inventory_sha256
    )


@pytest.mark.parametrize("age", [-1, True, 31_536_001])
def test_invalid_age_policy_rejected(age: int) -> None:
    with pytest.raises(ValueError, match="invalid observation age"):
        assess_physical_capabilities(
            PhysicalCapabilityInventory(scope=SCOPE),
            assessed_at=NOW,
            maximum_observation_age_seconds=age,
        )


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        assess_physical_capabilities(
            PhysicalCapabilityInventory(scope=SCOPE), assessed_at=datetime(2026, 1, 1)
        )
    evidence = observation().evidence.model_dump(mode="json") | {
        "observed_at": "2026-01-01T00:00:00"
    }
    with pytest.raises(ValidationError):
        observation(evidence=evidence)


def test_copied_model_cannot_skip_assessment_validation() -> None:
    forged = observation().model_copy(update={"facet": "execution"})
    inventory = PhysicalCapabilityInventory.model_construct(scope=SCOPE, observations=(forged,))
    with pytest.raises(ValidationError):
        assess_physical_capabilities(inventory, assessed_at=NOW)
