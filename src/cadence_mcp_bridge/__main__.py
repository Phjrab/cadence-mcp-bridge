"""Safe command-line entry point for local validation."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.designs import (
    DesignAnalysisRegistry,
    DesignContractRegistry,
    DesignMeasurementRegistry,
    DesignRegistry,
    RegistryBase,
    load_design_registry,
    register_designs,
)
from cadence_mcp_bridge.environments import (
    EnvironmentProfile,
    EnvironmentRejected,
    load_environment,
    prepare_environment,
    qualify_environment,
)
from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.onboarding import (
    OnboardingRejected,
    configured_registries_valid,
    export_client_config,
    verify_contracts,
)
from cadence_mcp_bridge.pdk_adapters import PdkRegistry, load_pdk_registry, register_pdk_adapters
from cadence_mcp_bridge.server import run_stdio_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cadence-mcp-bridge",
        description="Validate the local Cadence MCP bridge installation.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "config-check",
        help="Validate configuration without connecting to Cadence.",
    )
    subparsers.add_parser(
        "serve",
        help="Run the explicit legacy compatibility stdio launch.",
    )
    subparsers.add_parser(
        "serve-operator", help="Serve an explicit operator context; no legacy fallback."
    )
    runtime = subparsers.add_parser(
        "runtime", help="Operator-only local immutable context inspection."
    )
    runtime_actions = runtime.add_subparsers(dest="runtime_action", required=True)
    runtime_actions.add_parser("schema")
    for action in ("verify", "resolve"):
        command = runtime_actions.add_parser(action)
        command.add_argument("--settings", type=Path)
        command.add_argument("--context")
        if action == "resolve":
            command.add_argument("--design-id", required=True)
    operation = subparsers.add_parser("operation", help="Local authority and plan verification.")
    operation_actions = operation.add_subparsers(dest="operation_action", required=True)
    operation_actions.add_parser("grant-schema")
    operation_actions.add_parser("request-schema")
    journal_status = operation_actions.add_parser("journal-status")
    journal_status.add_argument("--settings", type=Path, required=True)
    journal_status.add_argument("--context", required=True)
    journal_status.add_argument("--operation-id", required=True)
    journal_status.add_argument("--expected-plan-sha256", required=True)
    for name in ("check-authority", "plan"):
        command = operation_actions.add_parser(name)
        command.add_argument("--settings", type=Path, required=True)
        command.add_argument("--context", required=True)
        command.add_argument("--grant", type=Path, required=True)
        command.add_argument("--expected-grant-sha256", required=True)
        if name == "plan":
            command.add_argument("--request", type=Path, required=True)
    ade = subparsers.add_parser("ade-input", help="Local ADE L artifacts; no native execution.")
    ade_actions = ade.add_subparsers(dest="ade_action", required=True)
    ade_actions.add_parser("schema")
    for name in ("compile", "verify-input"):
        command = ade_actions.add_parser(name)
        command.add_argument("--settings", type=Path, required=True)
        command.add_argument("--context", required=True)
        command.add_argument("--grant", type=Path, required=True)
        command.add_argument("--expected-grant-sha256", required=True)
        command.add_argument("--request", type=Path, required=True)
        command.add_argument("--registration", type=Path, required=True)
        command.add_argument("--expected-registration-sha256", required=True)
        command.add_argument("--operation-id", required=True)
        command.add_argument("--expected-plan-sha256", required=True)
        if name == "compile":
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--native-input", type=Path, required=True)
    runner = subparsers.add_parser(
        "runner", help="Fixed installed runner content workflow; no simulation."
    )
    actions = runner.add_subparsers(dest="runner_action", required=True)
    trust = actions.add_parser("trust")
    trust.add_argument("--profile", type=Path, required=True)
    trust.add_argument("--output", type=Path, required=True)
    prepare = actions.add_parser("bundle")
    prepare.add_argument("--profile", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    export = actions.add_parser("export-installer")
    export.add_argument("--output", type=Path, required=True)
    preflight = actions.add_parser("preflight")
    preflight.add_argument("--bundle", type=Path, required=True)
    preflight.add_argument("--expected-plan-sha256", required=True)
    for name in ("install", "verify"):
        command = actions.add_parser(name)
        command.add_argument("--target", type=Path, required=True)
        command.add_argument("--expected-plan-sha256", required=True)
        if name == "install":
            command.add_argument("--bundle", type=Path, required=True)
    subparsers.add_parser("doctor", help="Inspect local prerequisites without remote contact.")
    for name in ("verify", "client-config"):
        onboarding = subparsers.add_parser(name, help="Operator-only integrated onboarding.")
        onboarding.add_argument("--profile", type=Path, required=True)
        onboarding.add_argument("--design-registry", type=Path, required=True)
        onboarding.add_argument("--pdk-registry", type=Path, required=True)
        if name == "verify":
            onboarding.add_argument("--remote-preflight", action="store_true")
        else:
            onboarding.add_argument("--runtime-settings", type=Path)
            onboarding.add_argument("--context")
            onboarding.add_argument("--journal", type=Path, required=True)
            onboarding.add_argument("--sweep-journal", type=Path)
            onboarding.add_argument("--output", type=Path, required=True)
            onboarding.add_argument(
                "--format", choices=("codex", "mcp-json", "claude-desktop"), required=True
            )
    environment = subparsers.add_parser(
        "environment", help="Operator-only environment contracts; does not activate MCP execution."
    )
    actions = environment.add_subparsers(dest="environment_action", required=True)
    actions.add_parser("schema", help="Print the versioned environment JSON schema.")
    for action in ("validate", "prepare", "qualify"):
        command = actions.add_parser(action)
        command.add_argument("--profile", type=Path, required=True)
        if action == "prepare":
            command.add_argument("--output", type=Path, required=True)
    design = subparsers.add_parser("design", help="Operator-only local design registry contracts.")
    design_actions = design.add_subparsers(dest="design_action", required=True)
    schema = design_actions.add_parser(
        "schema", help="Print the versioned design registry JSON schema."
    )
    schema.add_argument("--schema-version", type=int, choices=(1, 2, 3, 4, 5, 6, 7, 8), default=1)
    for action in ("validate", "register"):
        command = design_actions.add_parser(action)
        command.add_argument("--registry", type=Path, required=True)
        if action == "register":
            command.add_argument("--output", type=Path, required=True)
    pdk = subparsers.add_parser("pdk", help="Operator-only local PDK capability contracts.")
    pdk_actions = pdk.add_subparsers(dest="pdk_action", required=True)
    pdk_actions.add_parser("schema", help="Print runtime PDK registry schema v2.")
    for action in ("validate", "register"):
        command = pdk_actions.add_parser(action)
        command.add_argument("--registry", type=Path, required=True)
        if action == "register":
            command.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "ade-input":
        from cadence_mcp_bridge.generic_ade import AdeExecutionRegistration, operator_inputs
        from cadence_mcp_bridge.operator_operations import OperationRejected

        try:
            if arguments.ade_action == "schema":
                ade_result = AdeExecutionRegistration.model_json_schema()
            else:
                ade_result = operator_inputs(
                    arguments.settings,
                    arguments.context,
                    arguments.grant,
                    arguments.expected_grant_sha256,
                    arguments.request,
                    arguments.registration,
                    arguments.expected_registration_sha256,
                    arguments.operation_id,
                    arguments.expected_plan_sha256,
                    getattr(arguments, "output", None),
                    getattr(arguments, "native_input", None),
                )
        except (
            OSError,
            ValueError,
            ConfigurationError,
            InvalidInputError,
            RecursionError,
        ) as failure:
            print(
                json.dumps(
                    {
                        "status": "ADE_INPUT_REJECTED",
                        "reason": failure.reason
                        if isinstance(failure, OperationRejected)
                        else "ade_document_invalid",
                        "execution_authorized": False,
                        "remote_contact": False,
                    }
                )
            )
            return 1
        print(json.dumps(ade_result, sort_keys=True))
        return 0
    if arguments.command == "operation":
        from cadence_mcp_bridge import operator_operations as operations
        from cadence_mcp_bridge.runtime_context import load_runtime

        try:
            if arguments.operation_action in ("grant-schema", "request-schema"):
                model = (
                    operations.OperatorGrant
                    if arguments.operation_action == "grant-schema"
                    else operations.OperationRequest
                )
                operation_result = model.model_json_schema()
            else:
                contexts = load_runtime(arguments.settings)
                context = next(
                    (c for c in contexts if c.binding.context_id == arguments.context), None
                )
                if context is None:
                    raise operations.OperationRejected("unknown_context_id")
                if arguments.operation_action == "journal-status":
                    from cadence_mcp_bridge.analysis_store import AnalysisStore
                    from cadence_mcp_bridge.operator_lifecycle import OperatorLifecycle

                    record = OperatorLifecycle(
                        context, AnalysisStore(context.binding.analysis_journal)
                    ).read(arguments.operation_id, arguments.expected_plan_sha256)
                    operation_result = {
                        "status": "LOCAL_DURABLE_OPERATION_OBSERVED",
                        "operation_id": record.operation_id,
                        "plan_sha256": record.plan.plan_sha256,
                        "progress": record.progress.model_dump(mode="json"),
                        "event_count": record.event_count,
                        "observation_scope": "LOCAL_LAST_OBSERVATION_NOT_CURRENT_REMOTE_STATUS",
                        "remote_contact": False,
                        "execution_authorized": False,
                    }
                elif arguments.operation_action == "plan":
                    operation_result = operations.inspect_plan(
                        context, arguments.grant, arguments.expected_grant_sha256, arguments.request
                    )
                else:
                    operation_result = operations.inspect_authority(
                        context, arguments.grant, arguments.expected_grant_sha256
                    )
        except (
            OSError,
            ValueError,
            ConfigurationError,
            InvalidInputError,
            RecursionError,
        ) as failure:
            print(
                json.dumps(
                    {
                        "status": "OPERATOR_OPERATION_REJECTED",
                        "reason": failure.reason
                        if isinstance(failure, operations.OperationRejected)
                        else "operator_document_invalid",
                        "execution_authorized": False,
                        "remote_contact": False,
                    }
                )
            )
            return 1
        print(json.dumps(operation_result, sort_keys=True))
        return 0
    if arguments.command == "runner":
        from cadence_mcp_bridge import bootstrap

        try:
            if arguments.runner_action == "trust":
                report = bootstrap.diagnose_trust(arguments.profile, arguments.output)
            elif arguments.runner_action == "bundle":
                report = bootstrap.bundle(arguments.profile, arguments.output)
            elif arguments.runner_action == "export-installer":
                report = bootstrap.export_installer(arguments.output)
            elif arguments.runner_action == "preflight":
                report = bootstrap.preflight(arguments.bundle, arguments.expected_plan_sha256)
            elif arguments.runner_action == "install":
                report = bootstrap.install(
                    arguments.bundle, arguments.target, arguments.expected_plan_sha256
                )
            else:
                report = bootstrap.verify(arguments.target, arguments.expected_plan_sha256)
        except (OSError, ValueError) as failure:
            print(
                json.dumps(
                    {
                        "status": "RUNNER_INSTALL_REJECTED",
                        "reason": failure.reason
                        if isinstance(failure, EnvironmentRejected)
                        else "runner_setup_invalid",
                        "execution_authorized": False,
                        "action": (
                            "administrator must verify executable and dependency trust; "
                            "no permission bypass"
                        )
                        if isinstance(failure, EnvironmentRejected)
                        and failure.reason == "executable_permissions"
                        else "verify reviewed hash, owner, paths and retained partial install",
                    }
                )
            )
            return 1
        print(json.dumps(report, sort_keys=True))
        return 0
    if arguments.command == "runtime":
        from cadence_mcp_bridge.runtime_context import (
            RuntimeRejected,
            RuntimeSettings,
            runtime_observation,
            select_context,
        )

        try:
            if arguments.runtime_action == "schema":
                observation = RuntimeSettings.model_json_schema()
            else:
                config = BridgeConfig(
                    **{
                        k: f.default
                        for k, f in BridgeConfig.model_fields.items()
                        if k not in ("runtime_mode", "runtime_settings_path", "runtime_context_id")
                    },
                    runtime_mode="operator",
                    runtime_settings_path=arguments.settings,
                    runtime_context_id=arguments.context,
                )
                if arguments.runtime_action == "resolve":
                    context = select_context(config)
                    if context is None:
                        raise RuntimeRejected("setup_required")
                    context.resolve(arguments.design_id)
                observation = runtime_observation(config)
        except (OSError, ValueError, ConfigurationError, InvalidInputError) as failure:
            print(
                json.dumps(
                    {
                        "status": "BLOCKED",
                        "execution_authorized": False,
                        "remote_contact": False,
                        "reason": failure.reason
                        if isinstance(failure, RuntimeRejected)
                        else "runtime_invalid",
                    }
                )
            )
            return 1
        print(json.dumps(observation, sort_keys=True))
        return 0
    if arguments.command in ("verify", "client-config"):
        try:
            paths = (arguments.profile, arguments.design_registry, arguments.pdk_registry)
            if arguments.command == "verify":
                onboarding_result = verify_contracts(
                    *paths, remote_preflight=arguments.remote_preflight
                )
            else:
                onboarding_result = export_client_config(
                    *paths,
                    arguments.journal,
                    arguments.output,
                    format=arguments.format,
                    sweep_journal=arguments.sweep_journal,
                    runtime_settings=arguments.runtime_settings,
                    context_id=arguments.context,
                )
        except (
            OSError,
            ConfigurationError,
            ValueError,
            RecursionError,
            TimeoutError,
            subprocess.SubprocessError,
        ) as failure:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "execution_authorized": False,
                        "reason": failure.reason
                        if isinstance(failure, (OnboardingRejected, EnvironmentRejected))
                        else "onboarding_operation_failed",
                    }
                )
            )
            return 1
        print(json.dumps(onboarding_result, sort_keys=True))
        return 0
    if arguments.command == "pdk":
        try:
            if arguments.pdk_action == "schema":
                pdk_result = PdkRegistry.model_json_schema()
            elif arguments.pdk_action == "register":
                pdk_result = register_pdk_adapters(arguments.registry, arguments.output)
            else:
                registry_pdks, _ = load_pdk_registry(arguments.registry)
                pdk_result = {
                    "status": "valid_description",
                    "adapter_count": len(registry_pdks.adapters),
                    "execution_authorized": False,
                }
        except (OSError, ValueError):
            print(json.dumps({"status": "blocked", "reason": "pdk_registry_invalid"}))
            return 1
        print(json.dumps(pdk_result, sort_keys=True))
        return 0
    if arguments.command == "doctor":
        config_valid = True
        try:
            config_valid = configured_registries_valid(BridgeConfig())
        except ValueError:
            config_valid = False
        print(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "host_os": {"win32": "Windows", "linux": "Linux", "darwin": "Darwin"}.get(
                        sys.platform, "unknown"
                    ),
                    "ssh_available": shutil.which("ssh.exe") is not None,
                    "legacy_config_valid": config_valid,
                    "configured_registries_valid": config_valid,
                    "remote_contact": False,
                    "execution_authorized": False,
                }
            )
        )
        return 0 if config_valid and shutil.which("ssh.exe") is not None else 1
    if arguments.command == "environment":
        try:
            action = arguments.environment_action
            if action == "schema":
                result = EnvironmentProfile.model_json_schema()
            elif action == "validate":
                profile, _ = load_environment(arguments.profile)
                result = {
                    "environment_id": profile.environment_id,
                    "status": "valid_description",
                    "execution_authorized": False,
                }
            elif action == "prepare":
                result = prepare_environment(arguments.profile, arguments.output)
            else:
                result = qualify_environment(arguments.profile)
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError) as failure:
            # Validation/transport messages may contain private operator configuration.
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": failure.reason
                        if isinstance(failure, EnvironmentRejected)
                        else "environment_contract_or_probe_failed",
                        "execution_authorized": False,
                    }
                )
            )
            return 1
        print(json.dumps(result, sort_keys=True))
        return 0
    if arguments.command == "design":
        try:
            if arguments.design_action == "schema":
                from cadence_mcp_bridge.analog_registry import DesignAnalogRegistry
                from cadence_mcp_bridge.measurement_bindings import DesignPowerSpecificationRegistry
                from cadence_mcp_bridge.specification_registry import DesignSpecificationRegistry
                from cadence_mcp_bridge.sweep_registry import DesignSweepRegistry

                registry_models: dict[int, type[RegistryBase]] = {
                    1: DesignRegistry,
                    2: DesignContractRegistry,
                    3: DesignAnalysisRegistry,
                    4: DesignMeasurementRegistry,
                    5: DesignSweepRegistry,
                    6: DesignAnalogRegistry,
                    7: DesignSpecificationRegistry,
                    8: DesignPowerSpecificationRegistry,
                }
                design_result = registry_models[arguments.schema_version].model_json_schema()
            elif arguments.design_action == "register":
                design_result = register_designs(arguments.registry, arguments.output)
            else:
                registry, _ = load_design_registry(arguments.registry)
                design_result = {
                    "status": "valid_description",
                    "design_count": len(registry.designs),
                    "execution_authorized": False,
                }
        except (OSError, ValueError):
            print(json.dumps({"status": "blocked", "reason": "design_registry_invalid"}))
            return 1
        print(json.dumps(design_result, sort_keys=True))
        return 0
    if arguments.command == "config-check":
        try:
            config = BridgeConfig()
            if config.runtime_mode == "operator":
                from cadence_mcp_bridge.runtime_context import runtime_observation

                print(json.dumps(runtime_observation(config), sort_keys=True))
                return 0
        except (ValueError, ConfigurationError):
            print("configuration: invalid operator runtime")
            return 1
        if config.pdk_registry_path is not None:
            try:
                load_pdk_registry(config.pdk_registry_path)
            except ValueError:
                print("configuration: invalid PDK registry")
                return 1
        if config.design_registry_path is not None:
            try:
                load_design_registry(config.design_registry_path)
            except ValueError:
                print("configuration: invalid design registry")
                return 1
        print("configuration: valid")
        return 0

    run_stdio_server(operator_mode=arguments.command in (None, "serve-operator"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
