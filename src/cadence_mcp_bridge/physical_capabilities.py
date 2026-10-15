"""Path-free physical-tool observations; inventory is never execution qualification.

This local contract consumes operator evidence. It neither probes a host nor
executes a tool, and deliberately cannot produce VERIFIED in M2-FOUNDATION-01.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$", max_length=64)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", max_length=64)]
Version = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")]
Capability = Literal[
    "layout-db", "pcell", "technology-library", "dbu", "layer-purpose", "via", "drc", "lvs", "pex"
]
Facet = Literal["installation", "interface", "deck", "license", "execution"]
ObservationReason = Literal[
    "presence_observed",
    "not_assessed",
    "no_approved_read_interface",
    "registered_binding_missing",
    "unsupported_registered_combination",
    "read_error",
    "permission_denied",
    "timeout",
    "malformed_response",
    "not_found_in_bounded_scope",
]
AssessmentReason = Literal[
    "presence_observed",
    "not_assessed",
    "no_approved_read_interface",
    "registered_binding_missing",
    "unsupported_registered_combination",
    "read_error",
    "permission_denied",
    "timeout",
    "malformed_response",
    "not_found_in_bounded_scope",
    "synthetic_evidence_only",
    "repository_contract_only",
    "stale_observation",
    "observation_after_assessment",
]
ObservationStatus = Literal[
    "INSTALLED_OBSERVED",
    "INTERFACE_OBSERVED",
    "DECK_OBSERVED",
    "LICENSE_UNVERIFIED",
    "EXECUTION_UNVERIFIED",
    "BLOCKED",
    "UNKNOWN",
]
CAPABILITIES: tuple[Capability, ...] = (
    "layout-db",
    "pcell",
    "technology-library",
    "dbu",
    "layer-purpose",
    "via",
    "drc",
    "lvs",
    "pex",
)
FACETS: tuple[Facet, ...] = ("installation", "interface", "deck", "license", "execution")


class PhysicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class PhysicalScope(PhysicalModel):
    """Exact operator environment and PDK bindings, never filesystem locations."""

    environment_id: Identifier
    environment_sha256: Digest
    pdk_id: Identifier
    pdk_sha256: Digest


class PhysicalEvidence(PhysicalModel):
    evidence_id: Identifier
    scope: PhysicalScope
    origin: Literal["current_vm", "retained_vm", "synthetic_fixture", "repository_contract"]
    observed_at: AwareDatetime
    evidence_sha256: Digest
    source_sha256: Digest


class PhysicalCapabilityObservation(PhysicalModel):
    capability: Capability
    facet: Facet
    outcome: Literal["present", "not_assessed", "blocked", "error"]
    reason: ObservationReason
    evidence: PhysicalEvidence
    subject_sha256: Digest | None = None
    interface_id: Identifier | None = None
    observed_version: Version | None = None

    @model_validator(mode="after")
    def closed_observation(self) -> Self:
        if self.outcome == "present":
            if self.reason != "presence_observed":
                raise ValueError("presence requires observed evidence")
            if self.facet not in ("installation", "interface", "deck"):
                raise ValueError("read-only inventory cannot establish license or execution")
            if self.subject_sha256 is None:
                raise ValueError("presence requires an exact subject binding")
            if self.facet == "interface" and self.interface_id is None:
                raise ValueError("interface observation requires its logical identity")
        else:
            permitted = {
                "not_assessed": {"not_assessed", "no_approved_read_interface"},
                "blocked": {"registered_binding_missing", "unsupported_registered_combination"},
                "error": {
                    "read_error",
                    "permission_denied",
                    "timeout",
                    "malformed_response",
                    "not_found_in_bounded_scope",
                },
            }
            if self.reason not in permitted[self.outcome]:
                raise ValueError("observation reason does not match its outcome")
            if any(
                v is not None
                for v in (self.subject_sha256, self.interface_id, self.observed_version)
            ):
                raise ValueError("unobserved outcomes cannot claim observed subject metadata")
        if self.interface_id is not None and self.facet != "interface":
            raise ValueError("interface identity is only valid for an interface observation")
        if self.observed_version is not None and self.facet not in ("installation", "interface"):
            raise ValueError("version is only valid for installed tools or observed interfaces")
        return self


class PhysicalCapabilityInventory(PhysicalModel):
    schema_version: Literal[1] = 1
    scope: PhysicalScope
    observations: Annotated[tuple[PhysicalCapabilityObservation, ...], Field(max_length=45)] = ()

    @model_validator(mode="after")
    def one_scoped_observation_per_facet(self) -> Self:
        seen: set[tuple[Capability, Facet]] = set()
        for observation in self.observations:
            key = observation.capability, observation.facet
            if key in seen:
                raise ValueError(
                    "duplicate capability facet; retain histories as separate inventories"
                )
            seen.add(key)
            if observation.evidence.scope != self.scope:
                raise ValueError("physical evidence environment or PDK binding differs")
        return self


class PhysicalFacetAssessment(PhysicalModel):
    facet: Facet
    status: ObservationStatus
    reason: AssessmentReason
    evidence_id: Identifier | None = None


class PhysicalCapabilityAssessment(PhysicalModel):
    capability: Capability
    facets: tuple[PhysicalFacetAssessment, ...]
    execution_qualified: Literal[False] = False
    signoff_qualified: Literal[False] = False


class PhysicalCapabilitiesAssessment(PhysicalModel):
    schema_version: Literal[1] = 1
    scope: PhysicalScope
    assessed_at: AwareDatetime
    maximum_observation_age_seconds: Annotated[int, Field(ge=0, le=31_536_000)]
    inventory_sha256: Digest
    capabilities: tuple[PhysicalCapabilityAssessment, ...]
    observations: tuple[PhysicalCapabilityObservation, ...]
    execution_authorized: Literal[False] = False
    remote_contact: Literal[False] = False
    verification_scope: Literal["read_only_inventory_assessment"] = "read_only_inventory_assessment"


def _assessment(
    facet: Facet,
    observation: PhysicalCapabilityObservation | None,
    assessed_at: datetime,
    maximum_age: int,
) -> PhysicalFacetAssessment:
    default: ObservationStatus = "UNKNOWN"
    if facet == "license":
        default = "LICENSE_UNVERIFIED"
    elif facet == "execution":
        default = "EXECUTION_UNVERIFIED"
    if observation is None:
        return PhysicalFacetAssessment(facet=facet, status=default, reason="not_assessed")
    reason: AssessmentReason = observation.reason
    status = default
    age = (assessed_at - observation.evidence.observed_at).total_seconds()
    if observation.evidence.origin == "synthetic_fixture":
        reason = "synthetic_evidence_only"
    elif observation.evidence.origin == "repository_contract":
        reason = "repository_contract_only"
    elif age < 0:
        reason = "observation_after_assessment"
    elif age > maximum_age:
        reason = "stale_observation"
    elif observation.outcome == "present":
        if facet == "installation":
            status = "INSTALLED_OBSERVED"
        elif facet == "interface":
            status = "INTERFACE_OBSERVED"
        elif facet == "deck":
            status = "DECK_OBSERVED"
    elif observation.outcome == "blocked":
        status = "BLOCKED"
    elif observation.outcome == "error":
        status = "UNKNOWN"
    return PhysicalFacetAssessment(
        facet=facet, status=status, reason=reason, evidence_id=observation.evidence.evidence_id
    )


def assess_physical_capabilities(
    inventory: PhysicalCapabilityInventory,
    *,
    assessed_at: datetime,
    maximum_observation_age_seconds: int = 86_400,
) -> PhysicalCapabilitiesAssessment:
    """Assess existing evidence locally; no host probes, writes, grants or tool runs.

    Freshness is explicit and measured against the supplied assessment time.
    Historical/stale and synthetic evidence remains in the result without being
    promoted into a current VM observation. Hashes bind evidence, not its truth.
    """
    inventory = PhysicalCapabilityInventory.model_validate_json(inventory.model_dump_json())
    if assessed_at.tzinfo is None or assessed_at.utcoffset() is None:
        raise ValueError("assessment time requires a timezone")
    if type(maximum_observation_age_seconds) is not int or not (
        0 <= maximum_observation_age_seconds <= 31_536_000
    ):
        raise ValueError("invalid observation age bound")
    assessed_at = assessed_at.astimezone(UTC)
    index = {(o.capability, o.facet): o for o in inventory.observations}
    canonical = json.dumps(inventory.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return PhysicalCapabilitiesAssessment(
        scope=inventory.scope,
        assessed_at=assessed_at,
        maximum_observation_age_seconds=maximum_observation_age_seconds,
        inventory_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        capabilities=tuple(
            PhysicalCapabilityAssessment(
                capability=capability,
                facets=tuple(
                    _assessment(
                        facet,
                        index.get((capability, facet)),
                        assessed_at,
                        maximum_observation_age_seconds,
                    )
                    for facet in FACETS
                ),
            )
            for capability in CAPABILITIES
        ),
        observations=inventory.observations,
    )
