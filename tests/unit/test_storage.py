from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from pydantic import ValidationError

from cadence_mcp_bridge import _storage_worker as worker
from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.server import create_server
from cadence_mcp_bridge.service import CadenceService
from cadence_mcp_bridge.storage import (
    CleanupRequest,
    StorageArtifact,
    StorageArtifactRequest,
    StoragePageRequest,
    StorageSelection,
    StorageSnapshot,
    StorageSupervisor,
    make_cleanup_plan,
    snapshot_digest,
)


def artifact(i: int, retention: str = "DELETE_CANDIDATE", **changes: Any) -> StorageArtifact:
    eligible = retention == "DELETE_CANDIDATE"
    raw = dict(
        artifact_id="sa-" + f"{i:064x}",
        storage_group_id="disposable" if eligible else "native",
        artifact_type="registered_intermediate" if eligible else "job_group",
        job_id=None,
        analysis_type="tran",
        size_bytes=100 * i,
        allocated_bytes=512 * i,
        retention_class=retention,
        replay_dependency=retention == "REPLAY_REQUIRED",
        evidence_dependency=retention == "EVIDENCE_REQUIRED",
        active_dependency=retention == "ACTIVE",
        measurement_extracted=True if eligible else None,
        deletion_status="ELIGIBLE" if eligible else "PROTECTED_OR_UNKNOWN",
        deletion_reason="reviewed_disposable_intermediate" if eligible else "dependency_unknown",
        fingerprint=f"{i:064x}",
    )
    return StorageArtifact.model_validate({**raw, **changes})


def snapshot(*items: StorageArtifact, **changes: Any) -> StorageSnapshot:
    value = StorageSnapshot(
        snapshot_id="0" * 64,
        artifacts=items,
        coverage_complete=True,
        group_coverage={"disposable": "SCANNED"},
        filesystem_free_bytes=4 * 1024**3,
        filesystem_total_bytes=20 * 1024**3,
        reserved_result_bytes=7114588160,
        spectre_attempts=62,
        active_eda=False,
        platform_delete_primitives=True,
    ).model_copy(update=changes)
    return value.model_copy(update={"snapshot_id": snapshot_digest(value)})


class Backend:
    def __init__(self, value: StorageSnapshot) -> None:
        self.value = value
        self.executions = 0

    async def storage_snapshot(self) -> StorageSnapshot:
        return self.value

    async def storage_cleanup(self, request: CleanupRequest) -> Any:
        self.executions += 1
        raise InvalidInputError("independent operator selection record absent")


@pytest.mark.parametrize(
    "retention",
    ["PROTECTED", "ACTIVE", "REPLAY_REQUIRED", "EVIDENCE_REQUIRED", "PROTECTED_OR_UNKNOWN"],
)
def test_protected_classes_never_eligible(retention: str) -> None:
    s = snapshot(artifact(1), artifact(2, retention))
    selection = StorageSelection(
        snapshot_id=s.snapshot_id, artifact_ids=tuple(a.artifact_id for a in s.artifacts)
    )
    p = make_cleanup_plan(s, selection)
    assert p.eligible_artifact_ids == (s.artifacts[0].artifact_id,)
    assert p.protected_exclusions == (s.artifacts[1].artifact_id,)
    assert p.estimated_reclaim_bytes == 100 and p.deleted is False
    assert p.replay_impact == p.evidence_impact == "none_permitted"


@pytest.mark.parametrize(
    "changes",
    [
        dict(replay_dependency=True),
        dict(evidence_dependency=True),
        dict(active_dependency=True),
        dict(measurement_extracted=False),
        dict(storage_group_id="native"),
        dict(artifact_type="job_group"),
    ],
)
def test_measurement_does_not_override_dependencies(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        artifact(1, **changes)


def test_partial_inventory_cannot_authorize_cleanup() -> None:
    s = snapshot(artifact(1), coverage_complete=False)
    p = make_cleanup_plan(
        s, StorageSelection(snapshot_id=s.snapshot_id, artifact_ids=(s.artifacts[0].artifact_id,))
    )
    assert not p.eligible_artifact_ids and p.estimated_reclaim_bytes == 0
    assert "partial_inventory" in p.warnings


def test_plan_stability_and_worker_hash_agree() -> None:
    s = snapshot(artifact(1), artifact(2))
    a = StorageSelection(
        snapshot_id=s.snapshot_id, artifact_ids=tuple(i.artifact_id for i in s.artifacts)
    )
    b = a.model_copy(update={"artifact_ids": tuple(reversed(a.artifact_ids))})
    p = make_cleanup_plan(s, a)
    assert p == make_cleanup_plan(s, b)
    assert p.model_dump(mode="json") == worker.plan(
        s.model_dump(mode="json"), a.model_dump(mode="json")
    )
    for field in ("fingerprint", "size_bytes", "retention_class"):
        changed = s.artifacts[0].model_copy(
            update={
                field: "f" * 64
                if field == "fingerprint"
                else 101
                if field == "size_bytes"
                else "PROTECTED"
            }
        )
        if field == "retention_class":
            changed = changed.model_copy(update={"deletion_status": "PROTECTED_OR_UNKNOWN"})
        altered = snapshot(changed, s.artifacts[1])
        with pytest.raises(InvalidInputError):
            make_cleanup_plan(altered, a)


def test_free_space_telemetry_does_not_invalidate_identity() -> None:
    s = snapshot(artifact(1))
    changed = s.model_copy(update={"filesystem_free_bytes": s.filesystem_free_bytes + 4096})
    assert snapshot_digest(changed) == s.snapshot_id


def test_unknown_and_duplicate_artifact_rejection() -> None:
    s = snapshot(artifact(1))
    with pytest.raises(InvalidInputError):
        make_cleanup_plan(
            s, StorageSelection(snapshot_id=s.snapshot_id, artifact_ids=("sa-" + "f" * 64,))
        )
    with pytest.raises(ValidationError):
        StorageSelection(snapshot_id=s.snapshot_id, artifact_ids=(s.artifacts[0].artifact_id,) * 2)


@pytest.mark.parametrize("bad", ["../", "/tmp/a", "sa-" + "A" * 64, "x;rm", "sa-" + "0" * 65])
def test_path_like_and_noncanonical_ids_denied(bad: str) -> None:
    with pytest.raises(ValidationError):
        StorageArtifactRequest(snapshot_id="0" * 64, artifact_id=bad)


@pytest.mark.parametrize(
    "changes",
    [dict(offset=-1), dict(limit=21), dict(limit=True), dict(path="/tmp"), dict(approved=True)],
)
def test_closed_strict_requests(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        StoragePageRequest.model_validate({"snapshot_id": "0" * 64, **changes})


def test_exact_selection_and_uuid_contract() -> None:
    s = snapshot(artifact(1), artifact(2))
    selection = StorageSelection(
        snapshot_id=s.snapshot_id, artifact_ids=(s.artifacts[0].artifact_id,)
    )
    p = make_cleanup_plan(s, selection)
    raw = dict(
        selection=selection.model_dump(mode="json"),
        cleanup_plan_id=p.cleanup_plan_id,
        plan_sha256=p.plan_sha256,
        selected_artifact_ids=list(selection.artifact_ids),
        operation_id=str(uuid4()),
    )
    request = CleanupRequest.model_validate_json(json.dumps(raw))
    assert request.dry_run is True
    for change in (
        dict(operation_id="../"),
        dict(selected_artifact_ids=[s.artifacts[1].artifact_id]),
        dict(approved=True),
        dict(dry_run="false"),
    ):
        with pytest.raises(ValidationError):
            CleanupRequest.model_validate_json(json.dumps({**raw, **change}))


@pytest.mark.asyncio
async def test_bounded_summary_paging_and_no_reservation_refund() -> None:
    s = snapshot(*(artifact(i) for i in range(1, 25)), artifact(25, "REPLAY_REQUIRED"))
    backend = Backend(s)
    service = StorageSupervisor(backend)
    summary = await service.summary()
    assert summary.total_managed_bytes == sum(i.size_bytes for i in s.artifacts)
    assert summary.potential_reclaim_bytes == sum(i.size_bytes for i in s.artifacts[:-1])
    assert summary.reserved_result_bytes == 7114588160 and summary.spectre_attempts == 62
    assert len(summary.largest_artifacts) == 5 and len(summary.model_dump_json()) < 65536
    page = await service.page(StoragePageRequest(snapshot_id=s.snapshot_id))
    assert len(page.artifacts) == 20 and page.next_offset == 20
    assert (
        len(
            (await service.page(StoragePageRequest(snapshot_id=s.snapshot_id, offset=20))).artifacts
        )
        == 5
    )
    assert (
        await service.describe(
            StorageArtifactRequest(
                snapshot_id=s.snapshot_id, artifact_id=s.artifacts[0].artifact_id
            )
        )
    ) == s.artifacts[0]
    backend.value = snapshot(*s.artifacts, reserved_result_bytes=7114588160 + 128 * 1024**2)
    with pytest.raises(InvalidInputError):
        await service.page(StoragePageRequest(snapshot_id=s.snapshot_id))


@pytest.mark.asyncio
async def test_forged_or_duplicate_remote_snapshot_denied() -> None:
    s = snapshot(artifact(1))
    for value in (
        s.model_copy(update={"snapshot_id": "f" * 64}),
        snapshot(artifact(1), artifact(1)),
    ):
        with pytest.raises(InvalidInputError):
            await StorageSupervisor(Backend(value)).summary()


@pytest.mark.asyncio
async def test_low_disk_and_partial_coverage_reported() -> None:
    summary = await StorageSupervisor(
        Backend(snapshot(artifact(1), coverage_complete=False, filesystem_free_bytes=100))
    ).summary()
    assert summary.disk_floor_status == "LOW_STORAGE" and summary.potential_reclaim_bytes == 0
    assert summary.coverage_complete is False


@pytest.mark.asyncio
async def test_actual_typed_mcp_storage_calls_and_malformed_boundary() -> None:
    s = snapshot(artifact(1), artifact(2, "EVIDENCE_REQUIRED"))
    backend = Backend(s)
    server = create_server(CadenceService(backend))  # type: ignore[arg-type]
    async with Client(server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert len(tools) == 69
        summary = await client.call_tool("cadence_storage_summary", {})
        assert not summary.is_error and summary.structured_content["snapshot_id"] == s.snapshot_id
        page = await client.call_tool(
            "cadence_list_storage_artifacts", {"request": {"snapshot_id": s.snapshot_id}}
        )
        assert not page.is_error and len(page.structured_content["artifacts"]) == 2
        selection = {"snapshot_id": s.snapshot_id, "artifact_ids": [s.artifacts[0].artifact_id]}
        p = await client.call_tool("cadence_plan_storage_cleanup", {"request": selection})
        assert not p.is_error and p.structured_content["deleted"] is False
        bad = await client.call_tool(
            "cadence_list_storage_artifacts",
            {"request": {"snapshot_id": s.snapshot_id, "path": "/tmp"}},
        )
        assert bad.is_error
        raw = dict(
            selection=selection,
            cleanup_plan_id=p.structured_content["cleanup_plan_id"],
            plan_sha256=p.structured_content["plan_sha256"],
            selected_artifact_ids=selection["artifact_ids"],
            operation_id=str(uuid4()),
            dry_run=False,
        )
        denied = await client.call_tool("cadence_execute_storage_cleanup", {"request": raw})
        assert denied.is_error and backend.executions == 1
        assert tools["cadence_execute_storage_cleanup"].annotations.destructive_hint
        assert not tools["cadence_execute_storage_cleanup"].annotations.read_only_hint
        for name in (
            "cadence_list_storage_artifacts",
            "cadence_describe_storage_artifact",
            "cadence_plan_storage_cleanup",
            "cadence_execute_storage_cleanup",
        ):
            assert tools[name].input_schema["additionalProperties"] is False
