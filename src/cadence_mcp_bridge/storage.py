"""Path-free storage contracts; deletion consent is owned by the operator."""

import hashlib
import json
from typing import Annotated, Any, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, field_validator, model_serializer, model_validator

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.resource_policy import FreshResourceCounter, FreshResourcePolicy
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel

ArtifactId = Annotated[str, Field(pattern=r"^sa-[0-9a-f]{64}$")]
PlanId = Annotated[str, Field(pattern=r"^sc-[0-9a-f]{64}$")]
Retention = Literal[
    "PROTECTED",
    "ACTIVE",
    "REPLAY_REQUIRED",
    "EVIDENCE_REQUIRED",
    "DELETE_CANDIDATE",
    "PROTECTED_OR_UNKNOWN",
]
Analysis = Literal["dc", "ac", "tran", "sweep", "unknown"]
Bytes = Annotated[int, Field(strict=True, ge=0)]


class StorageArtifact(ContractModel):
    artifact_id: ArtifactId
    storage_group_id: Literal["legacy", "native", "diagnostic", "pvt", "headroom", "disposable"]
    artifact_type: Literal["job_group", "registered_intermediate"]
    job_id: Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")] | None
    job_count: Bytes = 0
    analysis_type: Analysis
    design_id: str | None = None
    created_at: None = None
    last_used_at: None = None
    size_bytes: Bytes
    allocated_bytes: Bytes
    retention_class: Retention
    replay_dependency: bool
    evidence_dependency: bool
    active_dependency: bool
    measurement_extracted: bool | None
    deletion_status: Literal["ELIGIBLE", "PROTECTED_OR_UNKNOWN"]
    deletion_reason: Literal[
        "active_or_unresolved",
        "replay_required",
        "evidence_required",
        "dependency_unknown",
        "reviewed_disposable_intermediate",
    ]
    fingerprint: Digest
    provenance: Literal["registered_metadata_snapshot_v1"] = "registered_metadata_snapshot_v1"

    @model_validator(mode="after")
    def eligible_dependencies(self) -> Self:
        if self.deletion_status == "ELIGIBLE" and (
            self.retention_class != "DELETE_CANDIDATE"
            or self.storage_group_id != "disposable"
            or self.artifact_type != "registered_intermediate"
            or self.replay_dependency
            or self.evidence_dependency
            or self.active_dependency
            or self.measurement_extracted is not True
        ):
            raise ValueError("protected dependency cannot be deletable")
        return self


class StorageSnapshot(ContractModel):
    contract_version: Literal[1, 2] = 1
    snapshot_id: Digest
    artifacts: Annotated[tuple[StorageArtifact, ...], Field(max_length=64)]
    coverage_complete: bool
    group_coverage: dict[str, Literal["SCANNED", "MISSING", "BLOCKED", "PARTIAL"]]
    group_coverage_reason: dict[
        str,
        Literal[
            "none",
            "missing",
            "io_unavailable",
            "scan_limit",
            "artifact_limit",
            "unsafe_or_unavailable_object",
            "directory_unavailable_or_bounded",
        ],
    ] = Field(default_factory=dict)
    scan_nodes: Annotated[int, Field(strict=True, ge=0, le=49152)] = 0
    excluded_scope: Literal["source_ADE_PDK_vendor_local_state_and_unregistered_roots"] = (
        "source_ADE_PDK_vendor_local_state_and_unregistered_roots"
    )
    filesystem_free_bytes: Bytes
    filesystem_total_bytes: Bytes
    reserved_result_bytes: Bytes
    result_ceiling_bytes: Annotated[int, Field(strict=True, ge=1, le=10_737_418_240)] = (
        10_737_418_240
    )
    ledger_policy: FreshResourcePolicy | None = None
    spectre_attempts: Annotated[int, Field(strict=True, ge=0, le=500)]
    active_eda: bool
    platform_delete_primitives: bool

    @model_validator(mode="after")
    def registered_policy(self) -> Self:
        if self.contract_version == 1:
            if self.ledger_policy is not None or self.result_ceiling_bytes != 10_737_418_240:
                raise ValueError("legacy snapshot policy is unchanged")
        elif (
            self.ledger_policy is None
            or self.result_ceiling_bytes != self.ledger_policy.result_ceiling_bytes
            or self.spectre_attempts > self.ledger_policy.attempt_ceiling
            or self.reserved_result_bytes > self.result_ceiling_bytes
        ):
            raise ValueError("fresh snapshot requires its registered policy")
        if self.ledger_policy is not None:
            FreshResourceCounter(
                campaign_id=self.ledger_policy.campaign_id,
                count=self.spectre_attempts,
                result_reserved_bytes=self.reserved_result_bytes,
                policy=self.ledger_policy,
            )
        return self

    @model_serializer(mode="wrap")
    def retain_legacy_shape(self, handler: Any) -> dict[str, Any]:
        value: dict[str, Any] = handler(self)
        if self.contract_version == 1:
            value.pop("ledger_policy", None)
        return value


class StoragePageRequest(VariableModel):
    snapshot_id: Digest
    offset: Annotated[int, Field(ge=0, le=64)] = 0
    limit: Annotated[int, Field(ge=1, le=20)] = 20


class StorageArtifactRequest(VariableModel):
    snapshot_id: Digest
    artifact_id: ArtifactId


class StorageSelection(VariableModel):
    snapshot_id: Digest
    artifact_ids: Annotated[tuple[ArtifactId, ...], Field(min_length=1, max_length=16)]

    @field_validator("artifact_ids", mode="before")
    @classmethod
    def json_array(cls, value: object) -> object:
        return tuple(value) if type(value) is list else value

    @model_validator(mode="after")
    def unique_selection(self) -> Self:
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("duplicate artifact identity")
        return self


class CleanupPlan(ContractModel):
    contract_version: Literal[1] = 1
    cleanup_plan_id: PlanId
    plan_sha256: Digest
    snapshot_id: Digest
    selected_artifact_ids: tuple[ArtifactId, ...]
    eligible_artifact_ids: tuple[ArtifactId, ...]
    protected_exclusions: tuple[ArtifactId, ...]
    estimated_reclaim_bytes: Bytes
    fingerprints: dict[str, Digest]
    replay_impact: Literal["none_permitted"] = "none_permitted"
    evidence_impact: Literal["none_permitted"] = "none_permitted"
    warnings: tuple[
        Literal["partial_inventory", "selected_items_protected", "user_selection_required"], ...
    ]
    deleted: Literal[False] = False


class CleanupRequest(VariableModel):
    selection: StorageSelection
    cleanup_plan_id: PlanId
    plan_sha256: Digest
    selected_artifact_ids: Annotated[tuple[ArtifactId, ...], Field(min_length=1, max_length=16)]
    operation_id: UUID
    dry_run: bool = True

    @field_validator("selected_artifact_ids", mode="before")
    @classmethod
    def json_array(cls, value: object) -> object:
        return tuple(value) if type(value) is list else value

    @field_validator("operation_id", mode="before")
    @classmethod
    def canonical_uuid(cls, value: object) -> UUID:
        if isinstance(value, UUID) and value.version == 4:
            return value
        if type(value) is str:
            parsed = UUID(value)
            if str(parsed) == value and parsed.version == 4:
                return parsed
        raise ValueError("canonical version-4 operation UUID required")

    @model_validator(mode="after")
    def selected_subset(self) -> Self:
        if len(set(self.selected_artifact_ids)) != len(self.selected_artifact_ids):
            raise ValueError("duplicate artifact identity")
        if not set(self.selected_artifact_ids).issubset(self.selection.artifact_ids):
            raise ValueError("selected artifacts outside plan")
        return self


class CleanupOutcome(ContractModel):
    operation_id: str
    cleanup_plan_id: PlanId
    state: Literal["DRY_RUN", "DENIED", "COMPLETE", "PARTIAL", "UNKNOWN"]
    selected_artifact_ids: tuple[ArtifactId, ...]
    removed_artifact_ids: tuple[ArtifactId, ...]
    blocked_artifact_ids: tuple[ArtifactId, ...]
    expected_bytes: Bytes
    removed_logical_bytes: Bytes
    filesystem_free_delta_bytes: int
    unlinked_allocated_bytes: Bytes
    actual_reclaimed_bytes: None = None
    reclaim_semantics: Literal["physical_reclaim_not_attributed_free_delta_reported"] = (
        "physical_reclaim_not_attributed_free_delta_reported"
    )
    audit_recorded: bool
    reservation_refunded_bytes: Literal[0] = 0


class StoragePage(ContractModel):
    snapshot_id: Digest
    artifacts: tuple[StorageArtifact, ...]
    next_offset: int | None
    coverage_complete: bool


class StorageSummary(ContractModel):
    snapshot_id: Digest
    total_managed_bytes: Bytes
    allocated_managed_bytes: Bytes
    bytes_by_retention: dict[str, int]
    bytes_by_analysis: dict[str, int]
    potential_reclaim_bytes: Bytes
    artifact_count: int
    job_count: int
    largest_artifacts: tuple[StorageArtifact, ...]
    oldest_candidates: tuple[StorageArtifact, ...] = ()
    age_metadata: Literal["unavailable_not_inferred_from_mtime"] = (
        "unavailable_not_inferred_from_mtime"
    )
    filesystem_free_bytes: Bytes
    reserved_result_bytes: Bytes
    result_ceiling_bytes: Literal[10_737_418_240] = 10_737_418_240
    spectre_attempts: int
    disk_floor_bytes: Bytes
    disk_floor_status: Literal["OK", "LOW_STORAGE"]
    coverage_complete: bool
    group_coverage: dict[str, str]
    group_coverage_reason: dict[str, str]
    scan_nodes: int
    excluded_scope: str
    platform_delete_primitives: bool


def storage_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()


def snapshot_digest(snapshot: StorageSnapshot) -> str:
    """Disk-free telemetry fluctuates independently of artifact/ledger identity."""
    return storage_digest(
        snapshot.model_dump(
            exclude={
                "snapshot_id",
                "filesystem_free_bytes",
                "filesystem_total_bytes",
            }
        )
    )


def make_cleanup_plan(snapshot: StorageSnapshot, request: StorageSelection) -> CleanupPlan:
    if request.snapshot_id != snapshot.snapshot_id:
        raise InvalidInputError("Storage snapshot changed; inspect and replan")
    artifacts = {a.artifact_id: a for a in snapshot.artifacts}
    if any(i not in artifacts for i in request.artifact_ids):
        raise InvalidInputError("Unknown registered storage artifact")
    selected = tuple(sorted(request.artifact_ids))
    eligible = tuple(
        i
        for i in selected
        if snapshot.coverage_complete and artifacts[i].deletion_status == "ELIGIBLE"
    )
    excluded = tuple(i for i in selected if i not in eligible)
    warnings: list[
        Literal["partial_inventory", "selected_items_protected", "user_selection_required"]
    ] = ["user_selection_required"]
    if not snapshot.coverage_complete:
        warnings.append("partial_inventory")
    if excluded:
        warnings.append("selected_items_protected")
    payload = dict(
        contract_version=1,
        snapshot_id=snapshot.snapshot_id,
        selected_artifact_ids=selected,
        eligible_artifact_ids=eligible,
        protected_exclusions=excluded,
        estimated_reclaim_bytes=sum(artifacts[i].size_bytes for i in eligible),
        fingerprints={i: artifacts[i].fingerprint for i in selected},
        replay_impact="none_permitted",
        evidence_impact="none_permitted",
        warnings=tuple(warnings),
        deleted=False,
    )
    digest = storage_digest(payload)
    return CleanupPlan(cleanup_plan_id="sc-" + digest, plan_sha256=digest, **payload)  # type: ignore[arg-type]


class StorageBackend(Protocol):
    async def storage_snapshot(self) -> StorageSnapshot: ...

    async def storage_cleanup(self, request: CleanupRequest) -> CleanupOutcome: ...


class StorageSupervisor:
    def __init__(self, backend: StorageBackend) -> None:
        self.backend = backend

    async def snapshot(self, expected: str | None = None) -> StorageSnapshot:
        value = await self.backend.storage_snapshot()
        if len({a.artifact_id for a in value.artifacts}) != len(value.artifacts):
            raise InvalidInputError("Duplicate storage artifact identity")
        if value.snapshot_id != snapshot_digest(value) or (
            expected is not None and expected != value.snapshot_id
        ):
            raise InvalidInputError("Storage snapshot changed or invalid")
        return value

    async def summary(self) -> StorageSummary:
        s = await self.snapshot()
        retention: dict[str, int] = {}
        analyses: dict[str, int] = {}
        for a in s.artifacts:
            retention[a.retention_class] = retention.get(a.retention_class, 0) + a.size_bytes
            analyses[a.analysis_type] = analyses.get(a.analysis_type, 0) + a.size_bytes
        floor = max(2_147_483_648, (s.filesystem_total_bytes + 9) // 10)
        return StorageSummary(
            snapshot_id=s.snapshot_id,
            total_managed_bytes=sum(a.size_bytes for a in s.artifacts),
            allocated_managed_bytes=sum(a.allocated_bytes for a in s.artifacts),
            bytes_by_retention=retention,
            bytes_by_analysis=analyses,
            potential_reclaim_bytes=sum(
                a.size_bytes for a in s.artifacts if a.deletion_status == "ELIGIBLE"
            )
            if s.coverage_complete
            else 0,
            artifact_count=len(s.artifacts),
            job_count=sum(a.job_count for a in s.artifacts),
            largest_artifacts=tuple(
                sorted(s.artifacts, key=lambda a: (-a.size_bytes, a.artifact_id))[:5]
            ),
            filesystem_free_bytes=s.filesystem_free_bytes,
            reserved_result_bytes=s.reserved_result_bytes,
            spectre_attempts=s.spectre_attempts,
            disk_floor_bytes=floor,
            disk_floor_status="OK" if s.filesystem_free_bytes >= floor else "LOW_STORAGE",
            coverage_complete=s.coverage_complete,
            group_coverage={k: str(v) for k, v in s.group_coverage.items()},
            group_coverage_reason={k: str(v) for k, v in s.group_coverage_reason.items()},
            scan_nodes=s.scan_nodes,
            excluded_scope=s.excluded_scope,
            platform_delete_primitives=s.platform_delete_primitives,
        )

    async def page(self, request: StoragePageRequest) -> StoragePage:
        s = await self.snapshot(request.snapshot_id)
        end = request.offset + request.limit
        return StoragePage(
            snapshot_id=s.snapshot_id,
            artifacts=s.artifacts[request.offset : end],
            next_offset=end if end < len(s.artifacts) else None,
            coverage_complete=s.coverage_complete,
        )

    async def describe(self, request: StorageArtifactRequest) -> StorageArtifact:
        s = await self.snapshot(request.snapshot_id)
        for a in s.artifacts:
            if a.artifact_id == request.artifact_id:
                return a
        raise InvalidInputError("Unknown registered storage artifact")

    async def plan(self, request: StorageSelection) -> CleanupPlan:
        return make_cleanup_plan(await self.snapshot(request.snapshot_id), request)

    async def execute(self, request: CleanupRequest) -> CleanupOutcome:
        # Remote worker revalidates the entire plan under the same EDA lock.
        # It also owns durable repeat/uncertain outcomes, even after items disappear.
        result = await self.backend.storage_cleanup(request)
        if (
            result.operation_id != str(request.operation_id)
            or result.cleanup_plan_id != request.cleanup_plan_id
            or result.selected_artifact_ids != request.selected_artifact_ids
        ):
            raise InvalidInputError("Storage cleanup response identity mismatch")
        return result
