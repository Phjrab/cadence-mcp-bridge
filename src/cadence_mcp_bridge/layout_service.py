"""Layout orchestration; production writes and durable admission belong to C1."""

from __future__ import annotations

from typing import Protocol

from cadence_mcp_bridge.layout_engine import LayoutRejected, build_plan
from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutPlan,
    LayoutPlanRequest,
    LayoutResult,
    LayoutSelectRequest,
    LayoutSnapshot,
)


class LayoutProvider(Protocol):
    """Registered provider, never dynamically loaded from a public request.

    fork/apply must first resolve operation ID in the EXISTING durable journal:
    same ID+request hash returns its retained receipt, conflicting hash rejects,
    uncertain/partial intent returns OUTCOME_UNKNOWN without another write.
    New apply calls layout_engine.validate_plan(current, request) while holding
    the existing native resource lock, then saves/closes/reopens and computes
    compute_diff(before, after, expected=predicted). No local result grants authority.
    """

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot: ...
    async def fork(self, request: LayoutForkRequest) -> LayoutResult: ...
    async def apply(self, request: LayoutApplyRequest) -> LayoutResult: ...
    async def diff(self, request: LayoutDiffRequest) -> LayoutResult: ...
    async def select(self, request: LayoutSelectRequest) -> LayoutResult: ...


class LayoutService:
    def __init__(self, provider: LayoutProvider) -> None:
        self.provider = provider

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
        request = LayoutInspectRequest.model_validate_json(request.model_dump_json())
        snapshot = await self.provider.inspect(request)
        snapshot = LayoutSnapshot.model_validate_json(snapshot.model_dump_json())
        if snapshot.binding != request.binding:
            raise LayoutRejected("layout_inspect_binding_mismatch")
        return snapshot

    async def plan(self, request: LayoutPlanRequest) -> LayoutPlan:
        request = LayoutPlanRequest.model_validate_json(request.model_dump_json())
        snapshot = await self.inspect(LayoutInspectRequest(binding=request.binding))
        return build_plan(snapshot, request)

    async def fork(self, request: LayoutForkRequest) -> LayoutResult:
        request = LayoutForkRequest.model_validate_json(request.model_dump_json())
        result = self._result(await self.provider.fork(request), request.binding)
        if result.operation_id != request.operation_id:
            raise LayoutRejected("layout_operation_id_mismatch")
        if result.status == "FORK_VERIFIED" and (
            result.snapshot is None or not result.snapshot.owned or result.snapshot.read_only
        ):
            raise LayoutRejected("fork_must_return_owned_working_revision")
        return result

    async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
        request = LayoutApplyRequest.model_validate_json(request.model_dump_json())
        if request.expected_plan_sha256 != request.plan.plan_sha256:
            raise LayoutRejected("layout_expected_plan_digest_mismatch")
        # Native provider checks durable operation identity BEFORE inspecting the
        # current baseline: successful replay must not fail as a stale new apply.
        result = self._result(await self.provider.apply(request), request.plan.request.binding)
        if result.operation_id != request.plan.request.operation_id:
            raise LayoutRejected("layout_operation_id_mismatch")
        if result.status == "EDIT_VERIFIED":
            if result.snapshot is None or (
                result.snapshot.semantic_sha256 != request.plan.expected_semantic_sha256
            ):
                raise LayoutRejected("layout_readback_does_not_match_plan")
            if result.diff is None or (
                result.diff.before_sha256 != request.plan.baseline_sha256
                or result.diff.after_sha256 != result.snapshot.semantic_sha256
                or result.diff.unexpected_object_ids
                or result.diff.metadata_changes
                or result.diff.changes != request.plan.preview.predicted_diff.changes
            ):
                raise LayoutRejected("layout_readback_diff_mismatch")
            pins = {p.object_id: p for p in result.snapshot.pins}
            for edit in request.plan.normalized_edits:
                if edit.kind == "add_pin" and (
                    edit.object_id not in pins
                    or pins[edit.object_id].association != "native_verified"
                ):
                    raise LayoutRejected("native_pin_association_not_verified")
        return result

    async def diff(self, request: LayoutDiffRequest) -> LayoutResult:
        request = LayoutDiffRequest.model_validate_json(request.model_dump_json())
        result = self._result(await self.provider.diff(request), request.binding)
        if result.diff is not None and result.diff.before_sha256 != request.expected_before_sha256:
            raise LayoutRejected("layout_diff_baseline_mismatch")
        return result

    async def select(self, request: LayoutSelectRequest) -> LayoutResult:
        request = LayoutSelectRequest.model_validate_json(request.model_dump_json())
        result = self._result(await self.provider.select(request), request.binding)
        if result.executed or result.status not in ("SELECTED", "REJECTED", "OUTCOME_UNKNOWN"):
            raise LayoutRejected("revision_selection_must_not_mutate")
        if result.status == "SELECTED" and (
            result.snapshot is None
            or result.snapshot.semantic_sha256 != request.expected_baseline_sha256
        ):
            raise LayoutRejected("layout_selection_baseline_mismatch")
        return result

    @staticmethod
    def _result(result: LayoutResult, binding: object) -> LayoutResult:
        result = LayoutResult.model_validate_json(result.model_dump_json())
        if result.binding != binding or (
            result.new_revision is not None and result.new_revision != binding
        ):
            raise LayoutRejected("layout_result_binding_mismatch")
        return result
