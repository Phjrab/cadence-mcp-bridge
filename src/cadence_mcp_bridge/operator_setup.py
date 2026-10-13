"""Local operator setup assistance; never provisions a VM or grants execution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.onboarding import (
    ContractSnapshot,
    OnboardingRejected,
    _local_path,
    export_context_client_config,
    load_contracts,
)
from cadence_mcp_bridge.runtime_context import (
    ContextBinding,
    ExecutionContext,
    RuntimeRejected,
    RuntimeSettings,
    load_runtime,
    validate_runtime_document,
)

_LOCAL_ONLY = {
    "remote_contact": False,
    "execution_authorized": False,
    "generic_execution_qualified": False,
    "new_simulations": 0,
    "new_reservations": 0,
    "journal_created": False,
}

_GUIDANCE = {
    "setup_inputs_required": "Supply either all three contract files or settings and context.",
    "setup_output_exists": (
        "Preserve the existing file, including interrupted exports. Inspect it with check; "
        "use a new output filename if a replacement is needed."
    ),
    "setup_output_parent_required": "Create or select a private output directory first.",
    "setup_input_invalid": "Check argument types and complete bindings using this action's --help.",
    "setup_io_failed": (
        "Check local file access and disk space. Preserve any partial output; do not overwrite it."
    ),
    "local_path_invalid": "Use ordinary operator-owned paths without links or control characters.",
    "onboarding_contract_invalid": (
        "Validate each input with environment validate, design validate and pdk validate. "
        "Their schema commands describe the accepted fields."
    ),
    "design_catalog_empty": "Register at least one operator-owned circuit description.",
    "design_environment_mismatch": "Match circuit environment IDs to the selected profile.",
    "pdk_adapter_missing": "Register the PDK adapter referenced by the circuit.",
    "pdk_environment_mismatch": "Check the PDK adapter's registered environment IDs.",
    "pdk_corner_mismatch": "Check circuit corners against the licensed PDK registration.",
    "environment_analysis_mismatch": "Reconcile circuit analyses with environment capabilities.",
    "runtime_file_required": "Select an existing runtime settings file with an absolute path.",
    "unknown_context_id": "Select a context ID declared in the selected runtime settings file.",
    "runtime_contract_invalid": (
        "Check runtime schema and the referenced local files. Do not replace retained state."
    ),
    "resource_state_root_required": "Select an existing private resource state directory.",
    "journal_parent_required": "Select existing private journal directories; retain their paths.",
    "journal_invalid": "Preserve the journal and inspect its file type, links and access rights.",
    "journal_context_conflict": "Use distinct journals for each context and analysis/sweep role.",
    "journal_contract_collision": "Keep settings, contracts, journals and resource locks distinct.",
    "runtime_export_reserved_path": "Choose a new output outside input, journal and lock paths.",
    "output_or_journal_invalid": "Check private output/journal directories and distinct paths.",
    "runtime_export_mismatch": "Use the exact selected context's contracts and retained journals.",
    "stale_contract_digest": (
        "Review changed contracts against the retained settings. Export a new reviewed document "
        "only for intended changes; never silently refresh hashes or replace journals."
    ),
    "shared_resource_policy_conflict": (
        "Reconcile the same VM's policy and retained ledger identity; do not create new capacity."
    ),
    "environment_alias_conflict": "Reconcile conflicting descriptions of the same environment.",
    "ambiguous_design_id": "Use distinct circuit IDs across the selected runtime contexts.",
    "absolute_contract_paths_required": "Use absolute paths for every contract file.",
    "absolute_native_binding_paths_required": "Use absolute paths for native binding files.",
}


def add_setup_parser(subparsers: argparse._SubParsersAction[Any]) -> None:
    setup = subparsers.add_parser(
        "operator-setup", help="Stepwise local operator setup assistance."
    )
    actions = setup.add_subparsers(dest="setup_action", required=True)
    guide = actions.add_parser(
        "guide", help="Show fresh or retained setup steps without execution."
    )
    guide.add_argument("--mode", choices=("fresh", "existing"), required=True)
    check = actions.add_parser("check", help="Check contracts OR a selected runtime locally.")
    for name in ("profile", "design-registry", "pdk-registry", "settings"):
        check.add_argument("--" + name, type=Path)
    check.add_argument("--context")
    export = actions.add_parser("export-runtime", help="Create a new validated runtime document.")
    for name in (
        "profile",
        "design-registry",
        "pdk-registry",
        "resource-state-root",
        "journal",
        "sweep-journal",
        "output",
    ):
        export.add_argument("--" + name, type=Path, required=True)
    for name in ("context", "runner-sha256", "authority-ref", "ledger-ref"):
        export.add_argument("--" + name, required=True)
    for name in ("native-provider-binding", "operator-grant", "native-specifications"):
        export.add_argument("--" + name, type=Path)
    for name in (
        "native-provider-sha256",
        "operator-grant-sha256",
        "native-specifications-sha256",
    ):
        export.add_argument("--" + name)
    client = actions.add_parser("export-client", help="Export a fragment from an existing context.")
    client.add_argument("--settings", type=Path, required=True)
    client.add_argument("--context", required=True)
    client.add_argument("--output", type=Path, required=True)
    client.add_argument("--format", choices=("codex", "mcp-json", "claude-desktop"), required=True)


def setup_guide(mode: str) -> dict[str, object]:
    domain = "plan-fresh" if mode == "fresh" else "register-existing"
    steps = (
        (
            "install",
            "Install the package and export fictional examples; replace operator values.",
            (("operator-starter",),),
        ),
        (
            "contracts",
            "Validate your profile, circuit and licensed PDK descriptions locally.",
            (("operator-setup", "check"),),
        ),
        (
            "context",
            "Use explicit paths, references and hashes; retain journals and resource state.",
            (("operator-setup", "export-runtime"), ("operator-setup", "check")),
        ),
        (
            "environment",
            "Run explicit read-only VM qualification and executable trust checks.",
            (("verify",), ("runner", "trust"), ("runner", "repair-plan")),
        ),
        (
            "domain",
            (
                "Fresh provisioning needs evidence of no remote history; fresh mode is not proof."
                if mode == "fresh"
                else "Reuse settings and actual ledger/locks/journals. Never run apply-fresh "
                "to recover an existing VM. Register retained identity; review migration if needed."
            ),
            (("domain", domain),),
        ),
        (
            "registration",
            "Observe and assemble owned circuit/input/reader registration explicitly.",
            (("native-registration", "observe"), ("native-registration", "assemble")),
        ),
        (
            "activation",
            "Follow the starter guide for bundle, stage, operator authority, activation "
            "and preflight. Local settings do not authenticate native files or create a grant.",
            (
                ("native-runtime", "bundle"),
                ("native-runtime", "stage"),
                ("operator-authority", "confirm"),
                ("native-runtime", "activate"),
                ("native-runtime", "preflight"),
            ),
        ),
        (
            "first-job",
            "Export/review the client fragment, then use an approved bounded first job. "
            "Inspect status/result and same-ID recovery; only real execution proves acceptance.",
            (
                ("operator-setup", "export-client"),
                ("operation", "plan"),
                ("operation", "submit"),
                ("operation", "reconcile"),
                ("operation", "result"),
            ),
        ),
    )
    return {
        "status": "LOCAL_SETUP_GUIDE",
        "mode": mode,
        "steps": [
            {
                "step": number,
                "id": identity,
                "guidance": guidance,
                "state": "NOT_ASSESSED",
                "help_commands": [
                    ["cadence-mcp-bridge", *command, "--help"] for command in commands
                ],
            }
            for number, (identity, guidance, commands) in enumerate(steps, 1)
        ],
        "guide": "operator-starter exported README.md",
    }


def _notices(snapshot: ContractSnapshot) -> list[str]:
    notices = [
        "Local consistency does not qualify a VM, authenticate native bindings or authorize a job.",
        "Preserve budgets, journals, results and replay. New paths do not create capacity.",
    ]
    paths = snapshot.environment.paths
    expected = paths.managed_root + "/native-mcp-v1-jobs"
    if paths.job_root != expected or paths.result_root != expected:
        notices.append(
            "Native setup requires job_root and result_root at <managed_root>/native-mcp-v1-jobs. "
            "Review these profile fields before native provisioning; no profile was changed."
        )
    if snapshot.designs.schema_version < 4 or any(
        d.work_copy_policy != "owned_copy_only" for d in snapshot.designs.designs
    ):
        notices.append(
            "These descriptions do not establish native registration. The fictional starter uses "
            "read-only, unqualified examples. Enroll owned-copy circuits, schema 4+ variable and "
            "analysis contracts, and explicit reader definitions using the starter guide."
        )
    return notices


def _select(settings: Path, identity: str) -> ExecutionContext:
    contexts = load_runtime(_local_path(settings))
    context = next((c for c in contexts if c.binding.context_id == identity), None)
    if context is None:
        raise RuntimeRejected("unknown_context_id")
    return context


def _context_report(context: ExecutionContext) -> dict[str, object]:
    return {
        "context_id": context.binding.context_id,
        "context_sha256": context.context_sha256,
        "resource_domain_sha256": context.resource_domain_sha256,
        "native_bindings_authenticated": False,
        "ledger_assessed": False,
        "journal_health_assessed": False,
        "notices": _notices(context.contracts),
    }


def _check(arguments: argparse.Namespace) -> dict[str, object]:
    paths = (arguments.profile, arguments.design_registry, arguments.pdk_registry)
    if all(paths) and arguments.settings is None and arguments.context is None:
        snapshot = load_contracts(*paths)
        return {
            "status": "LOCAL_CONTRACTS_VALID",
            "contract_sha256": snapshot.report()["contract_sha256"],
            "notices": _notices(snapshot),
        }
    if not any(paths) and arguments.settings is not None and arguments.context is not None:
        return {
            "status": "LOCAL_CONTEXT_VALID",
            **_context_report(_select(arguments.settings, arguments.context)),
        }
    raise OnboardingRejected("setup_inputs_required")


def _export_runtime(arguments: argparse.Namespace) -> dict[str, object]:
    profile, designs, pdks = (
        _local_path(p)
        for p in (arguments.profile, arguments.design_registry, arguments.pdk_registry)
    )
    snapshot = load_contracts(profile, designs, pdks)
    output = _local_path(arguments.output)
    native: dict[str, Any] = {}
    for name in ("native_provider_binding", "operator_grant", "native_specifications"):
        value = getattr(arguments, name)
        native[name] = None if value is None else _local_path(value)
    for name in ("native_provider_sha256", "operator_grant_sha256", "native_specifications_sha256"):
        native[name] = getattr(arguments, name)
    if output in (profile, designs, pdks, *native.values()):
        raise OnboardingRejected("runtime_export_reserved_path")
    settings = RuntimeSettings(
        schema_version=1,
        resource_state_root=_local_path(arguments.resource_state_root),
        contexts=(
            ContextBinding(
                context_id=arguments.context,
                environment_profile=profile,
                environment_sha256=snapshot.environment_sha256,
                design_registry=designs,
                design_sha256=snapshot.design_sha256,
                pdk_registry=pdks,
                pdk_sha256=snapshot.pdk_sha256,
                runner_sha256=arguments.runner_sha256,
                authority_ref=arguments.authority_ref,
                ledger_ref=arguments.ledger_ref,
                analysis_journal=_local_path(arguments.journal),
                sweep_journal=_local_path(arguments.sweep_journal),
                **native,
            ),
        ),
    )
    data = (settings.model_dump_json(indent=2) + "\n").encode("utf-8")
    contexts = validate_runtime_document(output, data)
    if not output.parent.is_dir():
        raise OnboardingRejected("setup_output_parent_required")
    # Exactly one explicit local output. Existing/partial files are never removed or replaced.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": "LOCAL_RUNTIME_EXPORTED",
        "runtime_sha256": hashlib.sha256(data).hexdigest(),
        **_context_report(contexts[0]),
    }


def run_setup(arguments: argparse.Namespace) -> int:
    try:
        if arguments.setup_action == "guide":
            result = setup_guide(arguments.mode)
        elif arguments.setup_action == "check":
            result = _check(arguments)
        elif arguments.setup_action == "export-runtime":
            result = _export_runtime(arguments)
        else:
            result = export_context_client_config(
                arguments.settings,
                arguments.context,
                arguments.output,
                format=arguments.format,
            )
        result.update(_LOCAL_ONLY)
    except (OSError, ValueError, ConfigurationError, RecursionError) as failure:
        if isinstance(failure, (OnboardingRejected, RuntimeRejected)):
            reason = failure.reason
        elif isinstance(failure, FileExistsError):
            reason = "setup_output_exists"
        elif isinstance(failure, OSError):
            reason = "setup_io_failed"
        else:
            reason = "setup_input_invalid"
        result = {
            **_LOCAL_ONLY,
            "status": "BLOCKED",
            "reason": reason,
            "guidance": _GUIDANCE.get(reason, _GUIDANCE["setup_input_invalid"]),
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0
