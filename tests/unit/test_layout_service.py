"""Provider contract tests with an explicitly synthetic in-memory test double."""

from typing import Any

import pytest
from test_layout_models import fixture_instance_terminals, fixture_request, fixture_snapshot, reseal

from cadence_mcp_bridge.layout_engine import (
    LayoutRejected,
    build_plan,
    compute_diff,
    predict_snapshot,
    validate_plan,
)
from cadence_mcp_bridge.layout_models import (
    ZERO_DIGEST,
    LayoutApplyRequest,
    LayoutDiffRequest,
    LayoutEdit,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutInstanceTerminalQualification,
    LayoutNativeEdit,
    LayoutOrientationQualification,
    LayoutPlan,
    LayoutResult,
    LayoutSelectRequest,
    LayoutSnapshot,
    OrientEdit,
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
        self.orientation_qualification: LayoutOrientationQualification | None = None
        self.instance_terminal_qualification: LayoutInstanceTerminalQualification | None = None

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
            if self.orientation_qualification is not None and result.status == "EDIT_VERIFIED":
                validate_plan(
                    self.before, request, orientation_qualification=self.orientation_qualification
                )
            return result.model_copy(update={"executed": False, "replayed": True})
        validate_plan(
            self.current,
            request,
            orientation_qualification=self.orientation_qualification,
            instance_terminal_qualification=self.instance_terminal_qualification,
        )
        if self.unknown:
            result = LayoutResult(
                status="OUTCOME_UNKNOWN", binding=request.plan.request.binding, operation_id=op
            )
            self.receipts[op] = (identity, result)
            return result
        expected, _ = predict_snapshot(
            self.current,
            request.plan.request,
            orientation_qualification=self.orientation_qualification,
            instance_terminal_qualification=self.instance_terminal_qualification,
        )
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
async def test_instance_terminal_service_gate_and_qualified_replay() -> None:
    class InspectSpy(SyntheticProvider):
        inspections = 0

        async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
            self.inspections += 1
            return await super().inspect(request)

    before, request, qualification = fixture_instance_terminals()
    provider = InspectSpy()
    provider.before = provider.current = before
    provider.instance_terminal_qualification = qualification
    unqualified = LayoutService(provider)
    with pytest.raises(LayoutRejected, match="layout_instance_terminal_qualification_required"):
        await unqualified.plan(request)
    assert provider.inspections == 0
    service = LayoutService(provider, instance_terminal_qualification=qualification)
    plan = await service.plan(request)
    apply = LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    with pytest.raises(LayoutRejected, match="layout_instance_terminal_native_not_implemented"):
        await unqualified.apply(apply)
    assert provider.dispatches == 0
    result = await service.apply(apply)
    assert result.saved and result.reopened and result.status == "EDIT_VERIFIED"
    assert result.diff is not None and result.diff.instance_terminal_changes
    replay = await LayoutService(provider, instance_terminal_qualification=qualification).apply(
        apply
    )
    assert replay == result.model_copy(update={"executed": False, "replayed": True})
    assert provider.dispatches == provider.inspections == 1


@pytest.mark.asyncio
async def test_instance_terminal_service_rejects_geometry_only_receipt() -> None:
    class GeometryOnlyReceipt(SyntheticProvider):
        async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
            result = await super().apply(request)
            assert result.diff is not None
            return result.model_copy(
                update={"diff": result.diff.model_copy(update={"instance_terminal_changes": None})}
            )

    before, request, qualification = fixture_instance_terminals()
    provider = GeometryOnlyReceipt()
    provider.before = provider.current = before
    provider.instance_terminal_qualification = qualification
    service = LayoutService(provider, instance_terminal_qualification=qualification)
    plan = await service.plan(request)
    with pytest.raises(LayoutRejected, match="layout_readback_diff_mismatch"):
        await service.apply(LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256))


@pytest.mark.asyncio
async def test_instance_terminal_qualified_route_rejects_geometry_only_request() -> None:
    class UnexpectedProvider(SyntheticProvider):
        async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
            raise AssertionError("qualification must reject before inspection")

        async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
            raise AssertionError("qualification must reject before apply dispatch")

    before, _, qualification = fixture_instance_terminals()
    service = LayoutService(UnexpectedProvider(), instance_terminal_qualification=qualification)
    geometry = fixture_request(before)
    with pytest.raises(
        LayoutRejected, match="layout_instance_terminal_qualification_mapping_mismatch"
    ):
        await service.plan(geometry)
    plan = build_plan(before, geometry)
    with pytest.raises(
        LayoutRejected, match="layout_instance_terminal_qualification_mapping_mismatch"
    ):
        await service.apply(LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256))
    other = reseal(before, binding=before.binding.model_copy(update={"revision_id": "other-child"}))
    assert build_plan(other, fixture_request(other), instance_terminal_qualification=qualification)


@pytest.mark.asyncio
async def test_instance_terminal_fork_requires_the_verified_scope_transition() -> None:
    before, _, qualification = fixture_instance_terminals()
    child = reseal(
        before,
        provenance="native_readback",
        technology=before.technology.model_copy(update={"provenance": "native_observed"}),
    )
    parent = reseal(child, instance_terminals=None)

    class ForkProvider(SyntheticProvider):
        observed = child

        async def fork(self, request: LayoutForkRequest) -> LayoutResult:
            return LayoutResult(
                status="FORK_VERIFIED",
                binding=request.binding,
                operation_id=request.operation_id,
                snapshot=self.observed,
                diff=compute_diff(parent, self.observed),
                saved=True,
                reopened=True,
                source_unchanged=True,
            )

    provider = ForkProvider()
    service = LayoutService(provider, instance_terminal_qualification=qualification)
    request = LayoutForkRequest(
        binding=before.binding,
        operation_id=fixture_request().operation_id,
        expected_baseline_sha256=parent.semantic_sha256,
    )
    assert (await service.fork(request)).snapshot == child
    provider.observed = parent
    with pytest.raises(LayoutRejected, match="layout_instance_terminal_fork_evidence_mismatch"):
        await service.fork(request)


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
async def test_pin_label_rejects_before_any_provider_call() -> None:
    class InspectSpy(SyntheticProvider):
        inspect_calls = 0

        async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
            self.inspect_calls += 1
            return await super().inspect(request)

    provider = InspectSpy()
    service = LayoutService(provider)
    request = fixture_request(provider.before)
    # An unsafe in-process model_copy must also be rejected at service entry.
    pin = request.edits[-1].model_copy(update={"label": "OUT"})
    invalid = request.model_copy(update={"edits": (*request.edits[:-1], pin)})
    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(ValueError, match="layout_pin_label_not_supported"),
    ):
        await service.plan(invalid)
    assert provider.inspect_calls == provider.dispatches == 0
    plan = await service.plan(request)
    assert isinstance(plan.normalized_edits[-1], LayoutNativeEdit)
    assert plan.normalized_edits[-1].pin is not None
    assert plan.normalized_edits[-1].pin.label is None
    assert provider.inspect_calls == 1 and provider.dispatches == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["existing", "same_batch"])
async def test_pin_terminal_conflict_rejects_plan_before_write(conflict: str) -> None:
    provider = SyntheticProvider()
    service = LayoutService(provider)
    request = fixture_request(provider.before)
    pin = request.edits[-1]
    edits: tuple[LayoutEdit, ...]
    if conflict == "existing":
        edits = (pin.model_copy(update={"terminal_id": "terminal-old", "net_id": "net-old"}),)
    else:
        edits = (pin, pin.model_copy(update={"object_id": "pin-second"}))
    with pytest.raises(LayoutRejected, match="layout_pin_terminal_conflict"):
        await service.plan(request.model_copy(update={"edits": edits}))
    assert provider.dispatches == 0
    assert provider.current == provider.before


@pytest.mark.asyncio
async def test_new_pin_terminal_can_reuse_existing_net() -> None:
    provider = SyntheticProvider()
    service = LayoutService(provider)
    request = fixture_request(provider.before)
    pin = request.edits[-1].model_copy(update={"net_id": "net-old"})
    plan = await service.plan(request.model_copy(update={"edits": (pin,)}))
    result = await service.apply(
        LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    )
    assert result.status == "EDIT_VERIFIED"
    assert result.snapshot is not None
    added = next(p for p in result.snapshot.pins if p.object_id == "pin-new")
    assert added.net_id == "net-old" and added.terminal_id == "terminal-new"
    assert provider.dispatches == 1


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


async def _qualified_orientation() -> tuple[
    SyntheticProvider, LayoutOrientationQualification, LayoutApplyRequest
]:
    provider = SyntheticProvider()
    before = reseal(
        provider.before,
        provenance="native_readback",
        technology=provider.before.technology.model_copy(update={"provenance": "native_observed"}),
        capabilities=provider.before.capabilities.model_copy(update={"rotate": "not_verified"}),
    )
    provider.before = provider.current = before
    request = fixture_request(before).model_copy(
        update={
            "edits": (OrientEdit(kind="orient", object_id="inst-one", orientation="R90"),),
        }
    )
    qualification = LayoutOrientationQualification(
        binding=before.binding, orientations=("R0", "R90")
    )
    provider.orientation_qualification = qualification
    service = LayoutService(provider, orientation_qualification=qualification)
    plan = await service.plan(request)
    return (
        provider,
        qualification,
        LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256),
    )


async def test_orientation_apply_default_gate_rejects_before_provider() -> None:
    provider, _, apply = await _qualified_orientation()
    service = LayoutService(provider)
    with pytest.raises(LayoutRejected, match="layout_orientation_qualification_required"):
        await service.plan(apply.plan.request)
    with pytest.raises(LayoutRejected, match="layout_orientation_native_not_implemented"):
        await service.apply(apply)
    assert provider.dispatches == 0 and provider.receipts == {}


async def test_orientation_apply_with_pinned_context_and_same_id_replay() -> None:
    provider, qualification, apply = await _qualified_orientation()
    service = LayoutService(provider, orientation_qualification=qualification)
    result = await service.apply(apply)
    assert result.status == "EDIT_VERIFIED" and result.executed and not result.replayed
    assert result.snapshot is not None and result.snapshot.instances[0].orientation == "R90"
    assert result.saved and result.reopened and result.source_unchanged
    assert provider.current.semantic_sha256 != apply.plan.baseline_sha256
    replay = await LayoutService(provider, orientation_qualification=qualification).apply(apply)
    assert replay.replayed and not replay.executed and provider.dispatches == 1
    other = qualification.model_copy(
        update={
            "binding": qualification.binding.model_copy(update={"revision_id": "other-child"}),
        }
    )
    with pytest.raises(LayoutRejected, match="layout_orientation_qualification_binding_mismatch"):
        await LayoutService(provider, orientation_qualification=other).apply(apply)
    with pytest.raises(LayoutRejected, match="layout_orientation_native_not_implemented"):
        await LayoutService(provider).apply(apply)
    # Capability labels are excluded from the semantic digest. Check the retained
    # receipt's qualification explicitly even if the geometry still matches.
    snapshot = reseal(result.snapshot, capabilities=fixture_snapshot().capabilities)
    assert snapshot.semantic_sha256 == result.snapshot.semantic_sha256
    provider.receipts[apply.plan.request.operation_id] = (
        canonical_digest(apply),
        result.model_copy(update={"snapshot": snapshot}),
    )
    with pytest.raises(LayoutRejected, match="layout_orientation_qualification_snapshot_mismatch"):
        await service.apply(apply)
    assert provider.dispatches == 1


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("digest", "layout_expected_plan_digest_mismatch"),
        ("pair", "unsupported_orientation"),
        ("command", "layout_orientation_request_mismatch"),
        ("bbox", "layout_plan_revalidation_mismatch"),
        ("pcell", "layout_orientation_pcell_submaster_unsupported"),
    ],
)
async def test_orientation_apply_rejects_invalid_plan_before_write(case: str, reason: str) -> None:
    provider, qualification, apply = await _qualified_orientation()
    service = LayoutService(provider, orientation_qualification=qualification)
    plan = apply.plan
    request = plan.request
    (command,) = plan.normalized_edits
    if case == "digest":
        apply = apply.model_copy(update={"expected_plan_sha256": ZERO_DIGEST})
    else:
        if case == "pair":
            request = request.model_copy(
                update={
                    "edits": (OrientEdit(kind="orient", object_id="inst-one", orientation="MX"),)
                }
            )
            command = command.model_copy(update={"orientation": "MX"})
        elif case == "command":
            command = command.model_copy(update={"orientation": "R0"})
        elif case == "bbox":
            command = command.model_copy(update={"bbox_dbu": provider.before.instances[0].bbox_dbu})
        elif case == "pcell":
            provider.current = reseal(
                provider.before,
                instances=(
                    provider.before.instances[0].model_copy(update={"pcell_submaster": True}),
                ),
            )
            request = request.model_copy(
                update={"expected_baseline_sha256": provider.current.semantic_sha256}
            )
        plan = LayoutPlan.model_validate_json(
            plan.model_copy(
                update={
                    "request": request,
                    "normalized_edits": (command,),
                    "plan_sha256": ZERO_DIGEST,
                }
            ).model_dump_json()
        )
        apply = LayoutApplyRequest(plan=plan, expected_plan_sha256=plan.plan_sha256)
    with pytest.raises(LayoutRejected, match=f"^{reason}$"):
        await service.apply(apply)
    assert provider.dispatches == 0 and provider.receipts == {}
