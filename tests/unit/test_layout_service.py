"""Provider contract tests with an explicitly synthetic in-memory test double."""

from typing import Any

import pytest
from test_layout_models import fixture_request, fixture_snapshot, reseal

from cadence_mcp_bridge.layout_engine import (
    LayoutRejected,
    compute_diff,
    predict_snapshot,
    validate_plan,
)
from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutResult,
    LayoutSelectRequest,
    LayoutSnapshot,
)
from cadence_mcp_bridge.layout_service import LayoutService
from cadence_mcp_bridge.variable_contracts import canonical_digest


class SyntheticProvider:
    """Journal semantics test double; labels simulate frames, never native evidence."""

    def __init__(self) -> None:
        self.before = fixture_snapshot()
        self.current = self.before
        self.receipts: dict[str, tuple[str, LayoutResult]] = {}
        self.dispatches = 0
        self.pin_association = "native_verified"
        self.unknown = False

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
        return self.current

    async def fork(self, request: LayoutForkRequest) -> LayoutResult:
        return LayoutResult(
            status="NOT_VERIFIED", binding=request.binding, operation_id=request.operation_id
        )

    async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
        identity = canonical_digest(request)
        op = request.plan.request.operation_id
        if op in self.receipts:
            digest, result = self.receipts[op]
            if digest != identity:
                raise LayoutRejected("operation_id_content_conflict")
            return result.model_copy(update={"executed": False, "replayed": True})
        validate_plan(self.current, request)
        if self.unknown:
            result = LayoutResult(
                status="OUTCOME_UNKNOWN", binding=request.plan.request.binding, operation_id=op
            )
            self.receipts[op] = (identity, result)
            return result
        expected, _ = predict_snapshot(self.current, request.plan.request)
        self.current = reseal(
            expected,
            provenance="native_readback",
            technology=(expected.technology.model_copy(update={"provenance": "native_observed"})),
            pins=tuple(
                p.model_copy(update={"association": self.pin_association}) for p in expected.pins
            ),
        )
        self.dispatches += 1
        result = LayoutResult(
            executed=True,
            status="EDIT_VERIFIED",
            binding=request.plan.request.binding,
            operation_id=op,
            diff=compute_diff(self.before, self.current, expected=expected),
            snapshot=self.current,
            saved=True,
            reopened=True,
            source_unchanged=True,
        )
        self.receipts[op] = (identity, result)
        return result

    async def diff(self, request: LayoutDiffRequest) -> LayoutResult:
        return LayoutResult(
            status="DIFF", binding=request.binding, diff=compute_diff(self.before, self.current)
        )

    async def select(self, request: LayoutSelectRequest) -> LayoutResult:
        return LayoutResult(status="SELECTED", binding=request.binding, snapshot=self.before)


@pytest.mark.asyncio
async def test_service_plan_apply_replay_conflict_and_stale_never_duplicate() -> None:
    provider = SyntheticProvider()
    service = LayoutService(provider)
    request = fixture_request(provider.before)
    plan = await service.plan(request)
    apply = LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    result = await service.apply(apply)
    assert result.status == "EDIT_VERIFIED" and result.saved and result.reopened
    assert result.physical_verification.drc == "NOT_RUN"
    assert provider.before == fixture_snapshot()
    assert provider.dispatches == 1
    replay = await LayoutService(provider).apply(apply)
    assert replay.replayed and not replay.executed and provider.dispatches == 1
    # Same operation ID with a different plan must reject even on a stale baseline.
    from cadence_mcp_bridge.layout_engine import build_plan

    conflict_request = request.model_copy(update={"edits": (request.edits[0],)})
    other = build_plan(provider.before, conflict_request)
    with pytest.raises(LayoutRejected, match="content_conflict"):
        await service.apply(LayoutApplyRequest(plan=other, expected_plan_sha256=other.plan_sha256))
    stale = plan.model_copy(
        update={
            "request": request.model_copy(
                update={"operation_id": "b51c1ccf-330e-4460-87d6-d3a0f948d544"}
            ),
            "plan_sha256": "0" * 64,
        }
    )
    from cadence_mcp_bridge.layout_models import LayoutPlan

    stale = LayoutPlan.model_validate_json(stale.model_dump_json())
    with pytest.raises(LayoutRejected, match="stale_layout"):
        await service.apply(LayoutApplyRequest(plan=stale, expected_plan_sha256=stale.plan_sha256))
    assert provider.dispatches == 1


@pytest.mark.asyncio
async def test_unknown_intent_is_retained_and_never_redispatched() -> None:
    provider = SyntheticProvider()
    provider.unknown = True
    service = LayoutService(provider)
    plan = await service.plan(fixture_request(provider.before))
    request = LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    first = await service.apply(request)
    provider.unknown = False
    repeated = await LayoutService(provider).apply(request)
    assert first.status == repeated.status == "OUTCOME_UNKNOWN"
    assert repeated.replayed and provider.dispatches == 0


@pytest.mark.asyncio
async def test_missing_actual_terminal_net_association_cannot_verify_edit() -> None:
    provider = SyntheticProvider()
    provider.pin_association = "requested"
    service = LayoutService(provider)
    plan = await service.plan(fixture_request(provider.before))
    with pytest.raises(LayoutRejected, match="native_pin_association_not_verified"):
        await service.apply(LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256))
    # Geometry is identical, but actual net/terminal evidence is independently required.
    assert provider.current.semantic_sha256 == plan.expected_semantic_sha256
    assert provider.dispatches == 1


@pytest.mark.asyncio
async def test_select_previous_revision_and_diff_are_read_only() -> None:
    provider = SyntheticProvider()
    service = LayoutService(provider)
    snapshot = provider.before
    selected = await service.select(
        LayoutSelectRequest(
            binding=snapshot.binding, expected_baseline_sha256=snapshot.semantic_sha256
        )
    )
    assert selected.status == "SELECTED" and not selected.executed
    diff = await service.diff(
        LayoutDiffRequest(
            binding=snapshot.binding,
            before_revision_id="parent",
            expected_before_sha256=snapshot.semantic_sha256,
        )
    )
    assert diff.diff is not None and not diff.diff.changes
    assert provider.dispatches == 0
    with pytest.raises(LayoutRejected, match="selection_baseline"):
        await service.select(
            LayoutSelectRequest(binding=snapshot.binding, expected_baseline_sha256="c" * 64)
        )


@pytest.mark.asyncio
async def test_wrong_hash_rejects_before_provider_dispatch() -> None:
    provider = SyntheticProvider()
    service = LayoutService(provider)
    plan = await service.plan(fixture_request(provider.before))
    with pytest.raises(LayoutRejected, match="expected_plan_digest"):
        await service.apply(LayoutApplyRequest(plan=plan, expected_plan_sha256="c" * 64))
    assert provider.dispatches == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"saved": False}, "native_reopen_evidence"),
        ({"reopened": False}, "native_reopen_evidence"),
        ({"source_unchanged": False}, "native_reopen_evidence"),
        ({"operation_id": "b51c1ccf-330e-4460-87d6-d3a0f948d544"}, "operation_id_mismatch"),
    ],
)
async def test_untrustworthy_provider_result_is_rejected(
    updates: dict[str, Any],
    reason: str,
) -> None:
    provider = SyntheticProvider()
    service = LayoutService(provider)
    plan = await service.plan(fixture_request(provider.before))
    request = LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    honest = await provider.apply(request)
    provider.receipts[plan.request.operation_id] = (
        canonical_digest(request),
        honest.model_copy(update=updates),
    )
    with pytest.raises(ValueError, match=reason):
        await service.apply(request)
