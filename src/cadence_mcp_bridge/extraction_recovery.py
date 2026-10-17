"""Operator-only extraction recovery; no default MCP tool or source rewrite."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.native_service import NativeOperationService
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_lifecycle import ProviderObservation
from cadence_mcp_bridge.operator_operations import (
    OperationPlan,
    OperationRejected,
    OperationRequest,
    bounded_document,
    prepare_plan,
)
from cadence_mcp_bridge.runtime_context import ExecutionContext, load_runtime, resource_lock
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel


class RecoveryReference(VariableModel):
    original_operation_id: OperationId
    original_plan_sha256: Digest
    original_tree_fingerprint: Digest


class RecoveryPlan(OperationPlan):
    recovery: RecoveryReference


class RecoverySource(RecoveryReference):
    original_terminal_sha256: Digest
    native_input_sha256: Digest
    psf_tree_fingerprint: Digest


class ExtractionRecoveryService:
    def __init__(self, context: ExecutionContext) -> None:
        self.native = NativeOperationService(context)

    def validate(self, plan: RecoveryPlan) -> None:
        self.native.current()
        expected = prepare_plan(
            self.native.context, self.native.grant, self.native.grant_sha256,
            plan.request, int(time.time()), action="recover_extraction",
        )
        if expected.model_dump(mode="json") != plan.model_dump(mode="json", exclude={"recovery"}):
            raise OperationRejected("recovery_plan_current_scope_mismatch")

    async def plan(
        self, request: OperationRequest, original_operation_id: str, original_plan_sha256: str,
    ) -> RecoveryPlan:
        self.native.current()
        prepared = prepare_plan(
            self.native.context, self.native.grant, self.native.grant_sha256,
            request, int(time.time()), action="recover_extraction",
        )
        probe = RecoveryPlan.model_validate_json(_canonical({
            **prepared.model_dump(mode="json"),
            "recovery": {
                "original_operation_id": original_operation_id,
                "original_plan_sha256": original_plan_sha256,
                "original_tree_fingerprint": "0" * 64,
            },
        }))
        payload = await self.native.provider._call("recovery_source", probe, original_operation_id)
        source = RecoverySource.model_validate_json(_canonical(payload))
        if (source.original_operation_id, source.original_plan_sha256) != (
            original_operation_id, original_plan_sha256,
        ):
            raise OperationRejected("recovery_original_identity_mismatch")
        return RecoveryPlan.model_validate_json(_canonical({
            **prepared.model_dump(mode="json"),
            "recovery": source.model_dump(mode="json", include={
                "original_operation_id", "original_plan_sha256", "original_tree_fingerprint",
            }),
        }))

    async def observe(
        self, operation_id: str, plan: RecoveryPlan, *, submit: bool = False,
    ) -> ProviderObservation | None:
        self.native.current()
        from pydantic import TypeAdapter

        TypeAdapter(OperationId).validate_python(operation_id)
        if operation_id == plan.recovery.original_operation_id:
            raise OperationRejected("recovery_identity_must_be_distinct")
        # Repeated IDs remain lookup-only even after consent expiry or exhaustion.
        existing = await self.native.provider.lookup(operation_id, plan)
        if existing is not None:
            return existing
        store = self.native.lifecycle.store
        # A distinct analysis marker cannot be adopted as a simulation lifecycle.
        # The exact recovery hash includes its original job and retained PSF binding.
        identity = (plan.request.design_id, "extraction-recovery:" + plan.request.analysis_id,
                    plan.plan_sha256)

        def check_local() -> None:
            if not store.path.exists():
                return
            with store.connection(create=False, read_only=True) as connection:
                row = connection.execute(
                    "SELECT design_id,analysis_id,plan_hash FROM admissions WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if row is not None:
                    if row == identity:
                        raise OperationRejected("recovery_local_intent_unknown_no_resend")
                    raise OperationRejected("recovery_local_identity_occupied")
                if not store.native_sweep_identity_available(connection, operation_id):
                    raise OperationRejected("recovery_local_identity_occupied")

        check_local()
        if not submit:
            return None
        with resource_lock(self.native.context):
            check_local()
            self.validate(plan)
            accounting = await self.native.provider.authorize(plan, self.native.grant)
            accounting.check(self.native.context, self.native.grant, plan)
            try:
                first = store.admit(operation_id, *identity)
            except InvalidInputError:
                raise OperationRejected("recovery_local_identity_occupied") from None
            if not first:
                raise OperationRejected("recovery_local_intent_unknown_no_resend")
            # The existing admission table atomically excludes every parent/child
            # claim before sending. Loss after this commit stays UNKNOWN; even an
            # absent remote lookup never authorizes resending or refunding it.
            return await self.native.provider._observation("recover_extraction", operation_id, plan)

    async def result(self, operation_id: str, plan: RecoveryPlan) -> dict[str, object]:
        self.native.current()
        observed, projected = await self.native.provider.result(operation_id, plan)
        projected.update(
            operation_id=observed.operation_id, plan_sha256=plan.plan_sha256,
            original_operation_id=plan.recovery.original_operation_id,
            original_plan_sha256=plan.recovery.original_plan_sha256,
            recovery_mode="OCEAN_EXTRACTION_ONLY_NO_NETLIST_OR_SPECTRE",
        )
        return projected


def add_recovery_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    parser = subparsers.add_parser(
        "operator-recovery", help="Explicit experimental extraction-only recovery; no simulation.",
    )
    actions = parser.add_subparsers(dest="recovery_action", required=True)
    for name in ("plan", "submit", "status", "result"):
        action = actions.add_parser(name)
        action.add_argument("--settings", type=Path, required=True)
        action.add_argument("--context", required=True)
        if name == "plan":
            action.add_argument("--request", type=Path, required=True)
            action.add_argument("--original-operation-id", required=True)
            action.add_argument("--original-plan-sha256", required=True)
            action.add_argument("--output", type=Path, required=True)
        else:
            action.add_argument("--plan", type=Path, required=True)
            action.add_argument("--expected-plan-sha256", required=True)
            action.add_argument("--operation-id", required=True)
        if name == "submit":
            action.add_argument("--experimental-recovery", action="store_true", required=True)


def recovery_cli(arguments: argparse.Namespace) -> int:
    async def perform() -> dict[str, object]:
        settings = _local_path(arguments.settings)
        contexts = load_runtime(settings)
        context = next((c for c in contexts
                        if c.binding.context_id == arguments.context), None)
        if context is None:
            raise OperationRejected("unknown_context_id")
        if arguments.recovery_action == "plan":
            target = _local_path(arguments.output)
            reserved = {settings}
            for loaded in contexts:
                reserved.add(loaded.lock_path)
                for field in type(loaded.binding).model_fields:
                    value = getattr(loaded.binding, field)
                    if isinstance(value, Path):
                        reserved.add(_local_path(value))
                for journal in (loaded.binding.analysis_journal, loaded.binding.sweep_journal):
                    journal = _local_path(journal)
                    for suffix in ("-wal", "-shm", "-journal"):
                        reserved.add(journal.with_name(journal.name + suffix))
            if target in reserved:
                raise OperationRejected("recovery_plan_output_reserved")
            if target.exists() or not target.parent.is_dir():
                raise OperationRejected("recovery_plan_new_output_required")
            # Reject collisions across every configured context before contacting
            # the source provider; a fresh journal name is still retained state.
            service = ExtractionRecoveryService(context)
            plan = await service.plan(
                OperationRequest.model_validate_json(bounded_document(arguments.request)),
                arguments.original_operation_id, arguments.original_plan_sha256,
            )
            # Never replace operator inputs, previous evidence or an existing plan.
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(_canonical(plan.model_dump(mode="json")))
                stream.flush()
                os.fsync(stream.fileno())
            return {
                "status": "RECOVERY_PLAN_PREPARED_NOT_SUBMITTED",
                "plan_sha256": plan.plan_sha256, "remote_contact": True,
                "admission_created": False, "new_reservations": 0,
            }
        service = ExtractionRecoveryService(context)
        plan = RecoveryPlan.model_validate_json(bounded_document(arguments.plan))
        if plan.plan_sha256 != arguments.expected_plan_sha256:
            raise OperationRejected("recovery_plan_digest_mismatch")
        if arguments.recovery_action == "result":
            return await service.result(arguments.operation_id, plan)
        observation = await service.observe(
            arguments.operation_id, plan, submit=arguments.recovery_action == "submit",
        )
        return {
            "status": "RECOVERY_NOT_ADMITTED" if observation is None else "RECOVERY_OBSERVED",
            "observation": None if observation is None else observation.model_dump(mode="json"),
            "simulation_retry": False, "budget_reset_or_refund": False,
        }

    try:
        print(json.dumps(asyncio.run(perform()), sort_keys=True))
        return 0
    except (OSError, ValueError, ConfigurationError, RecursionError) as failure:
        print(json.dumps({
            "status": "OPERATOR_RECOVERY_REJECTED",
            "reason": failure.reason if isinstance(failure, OperationRejected)
            else "operator_document_invalid",
            "simulation_retry": False,
        }))
        return 1
