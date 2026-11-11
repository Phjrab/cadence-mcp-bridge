"""Layout orchestration; production writes and durable admission belong to C1."""

from __future__ import annotations

from typing import Protocol

from cadence_mcp_bridge.layout_engine import (
    LayoutRejected,
    build_plan,
    qualified_instance_terminal_edits,
)
from cadence_mcp_bridge.layout_models import (
    LayoutApplyRequest,
    LayoutConnectTerminalNativeEdit,
    LayoutDiffRequest,
    LayoutForkRequest,
    LayoutInspectRequest,
    LayoutInstanceTerminalQualification,
    LayoutOrientationQualification,
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
    The native provider revalidates the plan against the current or retained
    before snapshot. The worker independently checks new applies under the
    existing lock, then saves/closes/reopens for readback comparison.
    """

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot: ...
    async def fork(self, request: LayoutForkRequest) -> LayoutResult: ...
    async def apply(self, request: LayoutApplyRequest) -> LayoutResult: ...
    async def diff(self, request: LayoutDiffRequest) -> LayoutResult: ...
    async def select(self, request: LayoutSelectRequest) -> LayoutResult: ...


class LayoutService:
    def __init__(
        self,
        provider: LayoutProvider,
        *,
        orientation_qualification: LayoutOrientationQualification | None = None,
        instance_terminal_qualification: LayoutInstanceTerminalQualification | None = None,
    ) -> None:
        """The registered provider factory supplies any pinned qualification."""
        self.provider = provider
        self._orientation_qualification = (
            LayoutOrientationQualification.model_validate(
                orientation_qualification.model_dump(warnings=False)
            )
            if orientation_qualification is not None
            else None
        )
        self._instance_terminal_qualification = (
            LayoutInstanceTerminalQualification.model_validate_json(
                instance_terminal_qualification.model_dump_json()
            )
            if instance_terminal_qualification is not None
            else None
        )

    async def inspect(self, request: LayoutInspectRequest) -> LayoutSnapshot:
        request = LayoutInspectRequest.model_validate_json(request.model_dump_json())
        snapshot = await self.provider.inspect(request)
        snapshot = LayoutSnapshot.model_validate_json(snapshot.model_dump_json())
        if snapshot.binding != request.binding:
            raise LayoutRejected("layout_inspect_binding_mismatch")
        return snapshot

    async def plan(self, request: LayoutPlanRequest) -> LayoutPlan:
        request = LayoutPlanRequest.model_validate_json(request.model_dump_json())
        qualified_instance_terminal_edits(request, self._instance_terminal_qualification)
        if self._orientation_qualification is None and any(
            edit.kind == "orient" for edit in request.edits
        ):
            raise LayoutRejected("layout_orientation_qualification_required")
        snapshot = await self.inspect(LayoutInspectRequest(binding=request.binding))
        return build_plan(
            snapshot,
            request,
            orientation_qualification=self._orientation_qualification,
            instance_terminal_qualification=self._instance_terminal_qualification,
        )

    async def fork(self, request: LayoutForkRequest) -> LayoutResult:
        request = LayoutForkRequest.model_validate_json(request.model_dump_json())
        result = self._result(await self.provider.fork(request), request.binding)
        if result.operation_id != request.operation_id:
            raise LayoutRejected("layout_operation_id_mismatch")
        if result.status == "FORK_VERIFIED":
            snapshot = result.snapshot
            if snapshot is None or not snapshot.owned or snapshot.read_only:
                raise LayoutRejected("fork_must_return_owned_working_revision")
            qualification = self._instance_terminal_qualification
            if qualification is not None and qualification.binding == request.binding:
                self._check_association_fork(request, result, snapshot, qualification)
        return result

    @staticmethod
    def _check_association_fork(
        request: LayoutForkRequest,
        result: LayoutResult,
        snapshot: LayoutSnapshot,
        qualification: LayoutInstanceTerminalQualification,
    ) -> None:
        rows = snapshot.instance_terminals or ()
        diff = result.diff
        if (
            {(row.key, row.master_id) for row in rows}
            != {(edit.key, edit.expected_master_id) for edit in qualification.edits}
            or any(row.present for row in rows)
            or diff is None
            or diff.before_sha256 != request.expected_baseline_sha256
            or diff.after_sha256 != snapshot.semantic_sha256
            or diff.changes
            or diff.unexpected_object_ids
            or diff.metadata_changes != ("instance_terminal_scope",)
            or diff.instance_terminal_changes != ()
        ):
            raise LayoutRejected("layout_instance_terminal_fork_evidence_mismatch")

    async def apply(self, request: LayoutApplyRequest) -> LayoutResult:
        request = LayoutApplyRequest.model_validate_json(request.model_dump_json())
        if request.expected_plan_sha256 != request.plan.plan_sha256:
            raise LayoutRejected("layout_expected_plan_digest_mismatch")
        association_commands = self._association_commands(request.plan)
        requested_orientations = tuple(
            (edit.object_id, edit.orientation)
            for edit in request.plan.request.edits
            if edit.kind == "orient"
        )
        normalized_orientations = tuple(
            (edit.object_id, edit.orientation)
            for edit in request.plan.normalized_edits
            if edit.kind == "orient"
        )
        qualification = self._orientation_qualification
        if requested_orientations or normalized_orientations:
            if qualification is None:
                raise LayoutRejected("layout_orientation_native_not_implemented")
            if qualification.binding != request.plan.request.binding:
                raise LayoutRejected("layout_orientation_qualification_binding_mismatch")
            if requested_orientations != normalized_orientations:
                raise LayoutRejected("layout_orientation_request_mismatch")
            if any(
                target not in qualification.orientations for _, target in requested_orientations
            ):
                raise LayoutRejected("unsupported_orientation")
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
            if (
                requested_orientations
                and qualification is not None
                and (
                    not result.snapshot.owned
                    or result.snapshot.read_only
                    or result.snapshot.capabilities.rotate != "not_verified"
                    or not set(qualification.orientations)
                    <= set(result.snapshot.technology.supported_orientations)
                )
            ):
                raise LayoutRejected("layout_orientation_qualification_snapshot_mismatch")
            if result.diff is None or (
                result.diff.before_sha256 != request.plan.baseline_sha256
                or result.diff.after_sha256 != result.snapshot.semantic_sha256
                or result.diff.unexpected_object_ids
                or result.diff.metadata_changes
                or result.diff.changes != request.plan.preview.predicted_diff.changes
                or result.diff.instance_terminal_changes
                != request.plan.preview.predicted_diff.instance_terminal_changes
            ):
                raise LayoutRejected("layout_readback_diff_mismatch")
            pins = {p.object_id: p for p in result.snapshot.pins}
            for edit in request.plan.normalized_edits:
                if edit.kind == "add_pin" and (
                    edit.object_id not in pins
                    or pins[edit.object_id].association != "native_verified"
                ):
                    raise LayoutRejected("native_pin_association_not_verified")
            if association_commands:
                self._check_association_snapshot(result.snapshot, association_commands)
        return result

    def _association_commands(
        self, plan: LayoutPlan
    ) -> tuple[LayoutConnectTerminalNativeEdit, ...]:
        commands = tuple(
            edit
            for edit in plan.normalized_edits
            if isinstance(edit, LayoutConnectTerminalNativeEdit)
        )
        diff = plan.preview.predicted_diff
        qualification = self._instance_terminal_qualification
        if (
            not commands
            and not diff.instance_terminal_changes
            and not any(edit.kind == "connect_terminal" for edit in plan.request.edits)
        ):
            qualified_instance_terminal_edits(plan.request, qualification)
            return ()
        if qualification is None:
            raise LayoutRejected("layout_instance_terminal_native_not_implemented")
        edits = qualified_instance_terminal_edits(plan.request, qualification)
        if (
            not edits
            or len(commands) != len(plan.normalized_edits)
            or tuple(edit.model_dump() for edit in edits)
            != tuple(
                command.model_dump(exclude={"before_sha256", "net_id", "terminal_id"})
                for command in commands
            )
        ):
            raise LayoutRejected("layout_instance_terminal_request_mismatch")
        if (
            diff.instance_terminal_changes is None
            or diff.before_sha256 != plan.baseline_sha256
            or diff.before_sha256 != plan.request.expected_baseline_sha256
            or diff.after_sha256 != plan.expected_semantic_sha256
            or diff.before_sha256 == diff.after_sha256
            or diff.changes
            or diff.metadata_changes
            or diff.unexpected_object_ids
            or diff.matches_plan is not True
        ):
            raise LayoutRejected("layout_instance_terminal_plan_diff_mismatch")
        changes = {change.after.key: change for change in diff.instance_terminal_changes}
        if changes.keys() != {command.key for command in commands} or any(
            (change := changes[command.key]).before.present
            or not change.after.present
            or change.after.master_id != command.expected_master_id
            or change.after.net_id != command.net_id
            or change.after.pin_object_id != command.pin_object_id
            for command in commands
        ):
            raise LayoutRejected("layout_instance_terminal_plan_diff_mismatch")
        return commands

    @staticmethod
    def _check_association_snapshot(
        snapshot: LayoutSnapshot, commands: tuple[LayoutConnectTerminalNativeEdit, ...]
    ) -> None:
        observed = {row.key: row for row in snapshot.instance_terminals or ()}
        pins = {pin.object_id: pin for pin in snapshot.pins}
        if (
            not snapshot.owned
            or snapshot.read_only
            or observed.keys() != {command.key for command in commands}
        ):
            raise LayoutRejected("layout_instance_terminal_readback_scope_mismatch")
        for command in commands:
            row = observed[command.key]
            pin = pins.get(command.pin_object_id)
            if (
                not row.present
                or row.master_id != command.expected_master_id
                or row.net_id != command.net_id
                or row.pin_object_id != command.pin_object_id
                or pin is None
                or pin.terminal_id != command.terminal_id
                or pin.association != "native_verified"
            ):
                raise LayoutRejected("layout_instance_terminal_readback_mismatch")

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
