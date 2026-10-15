"""Read-only feature guidance from the loaded configuration, never execution proof."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from cadence_mcp_bridge.authenticated_provider import NativeProviderBinding
from cadence_mcp_bridge.designs import RegistryBase
from cadence_mcp_bridge.errors import BridgeError
from cadence_mcp_bridge.fixture_contracts import FixtureAnalysis
from cadence_mcp_bridge.operator_operations import (
    OperationRejected,
    OperatorGrant,
    ScopedOperatorGrant,
    bounded_document,
    load_grant,
    match_grant,
)
from cadence_mcp_bridge.pdk_adapters import PdkRegistry
from cadence_mcp_bridge.runtime_context import ExecutionContext, OperatorService

GUIDANCE_URI = "cadence://feature-guidance"


def _feature(state: str, reasons: list[str], next_steps: list[str]) -> dict[str, Any]:
    return {"state": state, "reasons": reasons, "next_steps": next_steps}


def _native_check(context: ExecutionContext) -> tuple[OperatorGrant | None, list[str]]:
    binding = context.binding
    if binding.native_provider_binding is None:
        return None, ["native_binding_missing"]
    try:
        raw = bounded_document(binding.native_provider_binding)
        if hashlib.sha256(raw).hexdigest() != binding.native_provider_sha256:
            return None, ["native_binding_changed_restart_required"]
        provider = NativeProviderBinding.model_validate_json(raw)
        if provider.runtime_manifest_sha256 != binding.runner_sha256:
            return None, ["native_runner_binding_mismatch"]
        assert binding.operator_grant is not None and binding.operator_grant_sha256 is not None
        grant, _ = load_grant(binding.operator_grant, binding.operator_grant_sha256)
        try:
            match_grant(context, grant, int(time.time()))
        except OperationRejected as exc:
            if exc.reason == "authority_inactive":
                return grant, ["authority_inactive"]
            raise
        return grant, []
    except OperationRejected as exc:
        # Expose only the closed authority failure relevant to this guide.
        reason = "authority_inactive" if exc.reason == "authority_inactive" else "authority_invalid"
        return None, [reason]
    except (OSError, ValueError, BridgeError):
        return None, ["native_binding_invalid"]


def guidance(
    registry: RegistryBase,
    pdks: PdkRegistry,
    *,
    mode: str,
    context: ExecutionContext | None = None,
    native_tools_registered: bool | None = False,
) -> dict[str, Any]:
    """Bounded path-free inventory. Local matches cannot assert live route qualification."""
    grant, native_reasons = (None, ["setup_required"])
    if context is not None:
        grant, native_reasons = _native_check(context)
    spec_designs: set[str] = set()
    spec_reason = "native_specifications_missing"
    if context is not None and context.binding.native_specifications is not None:
        from cadence_mcp_bridge.native_specifications import NativeSpecificationCatalog

        try:
            raw = bounded_document(context.binding.native_specifications)
            if hashlib.sha256(raw).hexdigest() != context.binding.native_specifications_sha256:
                raise ValueError("stale catalog")
            catalog = NativeSpecificationCatalog.model_validate_json(raw)
            for spec in catalog.specifications:
                context.resolve(spec.design_id)
                spec_designs.add(spec.design_id)
            spec_reason = "native_specification_not_registered_for_design"
        except (OSError, ValueError, BridgeError):
            spec_designs.clear()
            spec_reason = "native_specifications_invalid"
    circuits = []
    for profile in registry.designs:
        contracts = registry.analyses_for(profile.design_id)
        analyses = []
        for analysis in profile.allowed_analyses:
            contract = next((c for c in contracts if c.analysis == analysis), None)
            reasons = list(native_reasons)
            steps = ["operator-setup check", "native-registration inspect", "preflight"]
            state = "BLOCKED"
            route = "native"
            if isinstance(contract, FixtureAnalysis):
                state, route = "SYNTHETIC_ONLY", "synthetic_fixture"
                reasons = ["fixture_not_oa_pdk"]
                steps = ["cadence_describe_design"]
            elif mode == "legacy_reference":
                route = "legacy"
                adapter = pdks.find(profile.pdk_adapter_id)
                eligible = (
                    contract is not None
                    and contract.adapter_kind == "native-fixed-reference-v1"
                    and adapter is not None
                    and adapter.supports_native(profile.environment_id, analysis)
                    and adapter.binding_sha256 == contract.adapter_contract_sha256
                )
                state = "REFERENCE_ONLY" if eligible else "UNVERIFIED"
                reasons = ["fixed_reference_scope"] if eligible else ["legacy_adapter_unqualified"]
                steps = ["cadence_list_analyses", "cadence_plan_analysis"]
            elif contract is None:
                reasons.append("analysis_contract_missing")
            elif grant is not None:
                if profile.design_id not in grant.design_ids or "submit" not in grant.actions:
                    reasons.append("authority_scope_denied")
                if analysis not in grant.analyses or (
                    isinstance(grant, ScopedOperatorGrant)
                    and (profile.design_id, analysis)
                    not in {(s.design_id, s.analysis) for s in grant.design_analyses}
                ):
                    reasons.append("analysis_scope_denied")
                if native_tools_registered is False:
                    reasons.append("native_tools_not_loaded")
                if not reasons:
                    state = "REQUIRES_EXECUTION_CHECKS"
                    steps = ["cadence_plan_operation", "cadence_submit_operation"]
            analyses.append({
                "analysis": analysis,
                "analysis_id": None if contract is None else contract.analysis_id,
                "route": route,
                **_feature(state, reasons, steps),
            })
        has_native = any(a["state"] == "REQUIRES_EXECUTION_CHECKS" for a in analyses)
        # Match the registered-axis gate in NativeSweepSupervisor.plan; local
        # eligibility still leaves each point's numeric/grant checks mandatory.
        has_sweep_axis = any(
            variable.mutation_policy == "owned_copy_only"
            and variable.range_status == "qualified"
            for variable in registry.variables(profile.design_id).variables
        )
        sweep_reasons = [] if has_native else ["native_analysis_unavailable"]
        if not has_sweep_axis:
            sweep_reasons.append("qualified_mutable_sweep_axis_missing")
        result_available = grant is not None and native_tools_registered is not False
        circuits.append({
            "design_id": profile.design_id,
            "description_registered": True,
            "remote_route_qualification": "NOT_ASSESSED",
            "analyses": analyses,
            "features": {
                "describe": _feature("LOCAL_AVAILABLE", [], ["cadence_describe_design"]),
                "variables": _feature("LOCAL_AVAILABLE", [], ["cadence_list_design_variables"]),
                "native_result": _feature(
                    "REQUIRES_EXECUTION_CHECKS" if result_available else "BLOCKED",
                    [] if result_available else ["native_result_route_unavailable"],
                    ["cadence_operation_status", "cadence_operation_result"],
                ),
                "native_1d_sweep": _feature(
                    "REQUIRES_EXECUTION_CHECKS" if not sweep_reasons else "BLOCKED",
                    sweep_reasons, ["cadence_plan_native_sweep"],
                ),
                "native_specification": _feature(
                    "REQUIRES_EXECUTION_CHECKS"
                    if result_available and profile.design_id in spec_designs else "BLOCKED",
                    [] if result_available and profile.design_id in spec_designs
                    else [spec_reason],
                    ["cadence_evaluate_native_specification"],
                ),
                "legacy_measurements": _feature(
                    "UNVERIFIED" if mode == "legacy_reference" else "BLOCKED",
                    ["use_registered_legacy_contract_checks"] if mode == "legacy_reference"
                    else ["legacy_tools_not_supported_in_operator_mode"],
                    ["cadence_list_measurements"] if mode == "legacy_reference" else [],
                ),
            },
        })
    return {
        "schema_version": 1,
        "status": "LOCAL_FEATURE_GUIDANCE",
        "mode": mode,
        "context_id": None if context is None else context.binding.context_id,
        "native_tools_registered": native_tools_registered,
        "circuits": circuits,
        "setup": _feature(
            "LOCAL_AVAILABLE" if registry.designs else "BLOCKED",
            [] if registry.designs else ["setup_required"],
            ["operator-starter", "operator-setup guide", "operator-setup check"],
        ),
        "execution_checks": [
            "explicit_values_and_numeric_scope", "remote_route_and_reader_qualification",
            "operator_confirmation_and_revocation", "retained_ledger_and_disk_limits",
            "fixed_runner_integrity_and_preflight", "result_identity_and_provenance",
        ],
        "remote_contact": False,
        "execution_authorized": False,
        "new_simulations": 0,
        "new_reservations": 0,
        "journal_created": False,
        "remaining_budget": None,
    }


def service_guidance(service: Any) -> dict[str, Any]:
    # Do not introspect methods: OperatorService.__getattr__ synthesizes blocked calls.
    if isinstance(service, OperatorService):
        return guidance(
            service.designs, service.pdks,
            mode="unconfigured" if service.context is None else "operator",
            context=service.context,
            native_tools_registered=service.native_operations is not None,
        )
    return guidance(service._designs, service._pdks, mode="legacy_reference")


def add_features_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    command = subparsers.add_parser("operator-features", help="Read-only local feature guidance.")
    command.add_argument("--settings", type=Path, required=True)
    command.add_argument("--context", required=True)


def features_cli(arguments: argparse.Namespace) -> int:
    from cadence_mcp_bridge.operator_setup import _select

    try:
        context = _select(arguments.settings, arguments.context)
        result = guidance(
            context.contracts.designs, context.contracts.pdks,
            mode="operator", context=context,
            # This is a file inspection, not an observation of a running server.
            native_tools_registered=None,
        )
        result["native_tools_registered"] = None
        result["observation_source"] = "explicit_local_files"
        code = 0
    except (OSError, ValueError, BridgeError):
        result = {
            "status": "BLOCKED", "reason": "feature_context_invalid",
            "guidance": "Use operator-setup check with the same explicit settings and context.",
            "remote_contact": False, "execution_authorized": False,
            "new_simulations": 0, "new_reservations": 0,
        }
        code = 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return code
