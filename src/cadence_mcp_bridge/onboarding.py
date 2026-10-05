"""Operator-only onboarding over existing contracts; never activates remote execution."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cadence_mcp_bridge.config import BridgeConfig
from cadence_mcp_bridge.designs import RegistryBase, load_design_registry
from cadence_mcp_bridge.environments import (
    EnvironmentProfile,
    load_environment,
    qualify_environment,
)
from cadence_mcp_bridge.pdk_adapters import PdkRegistry, load_pdk_registry


class OnboardingRejected(ValueError):
    """Closed reasons only; underlying validation messages are never returned."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _local_path(path: Path) -> Path:
    absolute = path.absolute()
    if any(p.is_symlink() or p.is_junction() for p in (absolute, *absolute.parents)):
        raise OnboardingRejected("local_path_invalid")
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in str(absolute)):
        raise OnboardingRejected("local_path_invalid")
    return absolute.resolve()


@dataclass(frozen=True)
class ContractSnapshot:
    environment: EnvironmentProfile
    designs: RegistryBase
    pdks: PdkRegistry
    environment_sha256: str
    design_sha256: str
    pdk_sha256: str

    def report(self) -> dict[str, object]:
        return {
            "status": "consistent_local_contracts",
            "environment_id": self.environment.environment_id,
            "design_count": len(self.designs.designs),
            "adapter_count": len(self.pdks.adapters),
            "contract_sha256": {
                "environment": self.environment_sha256,
                "design": self.design_sha256,
                "pdk": self.pdk_sha256,
            },
            "designs": [
                {
                    "design_id": design.design_id,
                    "pdk_status": self.pdks.resolve(
                        design.design_id, design.pdk_adapter_id, design.environment_id
                    ).status,
                    "analysis_contract_count": len(self.designs.analyses_for(design.design_id)),
                }
                for design in self.designs.designs
            ],
            "remote_contact": False,
            "generic_execution_qualified": False,
            "execution_authorized": False,
            "spec_evaluation": "not_evaluated",
            "server_execution_routing": "fixed_reference_compatibility_only",
        }


def load_contracts(profile: Path, designs: Path, pdks: Path) -> ContractSnapshot:
    """One environment per verification; every catalog design must resolve to it."""
    try:
        environment, env_bytes = load_environment(_local_path(profile))
        registry, design_bytes = load_design_registry(_local_path(designs))
        adapters, pdk_bytes = load_pdk_registry(_local_path(pdks))
    except (OSError, ValueError, RecursionError):
        raise OnboardingRejected("onboarding_contract_invalid") from None
    if not registry.designs:
        raise OnboardingRejected("design_catalog_empty")
    for design in registry.designs:
        if design.environment_id != environment.environment_id:
            raise OnboardingRejected("design_environment_mismatch")
        adapter = adapters.find(design.pdk_adapter_id)
        if adapter is None:
            raise OnboardingRejected("pdk_adapter_missing")
        if environment.environment_id not in adapter.environment_ids:
            raise OnboardingRejected("pdk_environment_mismatch")
        if not set(design.allowed_corners).issubset(adapter.process_corner_ids):
            raise OnboardingRejected("pdk_corner_mismatch")
        if not set(design.allowed_analyses).issubset(environment.requested_capabilities):
            raise OnboardingRejected("environment_analysis_mismatch")
    return ContractSnapshot(
        environment,
        registry,
        adapters,
        hashlib.sha256(env_bytes).hexdigest(),
        hashlib.sha256(design_bytes).hexdigest(),
        hashlib.sha256(pdk_bytes).hexdigest(),
    )


def verify_contracts(
    profile: Path, designs: Path, pdks: Path, *, remote_preflight: bool = False
) -> dict[str, object]:
    snapshot = load_contracts(profile, designs, pdks)
    result = snapshot.report()
    if remote_preflight:
        # The existing bounded probe reopens the file, so bind it before transport.
        result["environment_preflight"] = qualify_environment(
            profile, expected_profile_sha256=snapshot.environment_sha256
        )
        result["remote_contact"] = True
    return result


def configured_registries_valid(config: BridgeConfig) -> bool:
    try:
        if config.design_registry_path is not None:
            load_design_registry(config.design_registry_path)
        if config.pdk_registry_path is not None:
            load_pdk_registry(config.pdk_registry_path)
    except (OSError, ValueError, RecursionError):
        return False
    return True


_PROMPT_TOOLS = (
    "cadence_submit_smoke",
    "cadence_cancel_job",
    "cadence_execute_design_write_validation",
    "cadence_submit_actual_diagnostic",
    "cadence_submit_native_diagnostic",
    "cadence_submit_sweep",
    "cadence_cancel_sweep",
    "cadence_submit_analysis",
)


def export_client_config(
    profile: Path,
    designs: Path,
    pdks: Path,
    journal: Path,
    output: Path,
    *,
    format: Literal["codex", "mcp-json", "claude-desktop"],
    sweep_journal: Path | None = None,
) -> dict[str, object]:
    """Create a new reviewed fragment; no global client config or journal writes."""
    snapshot = load_contracts(profile, designs, pdks)
    design_path, pdk_path, journal_path, output_path = (
        _local_path(p) for p in (designs, pdks, journal, output)
    )
    profile_path = _local_path(profile)
    inputs = (profile_path, design_path, pdk_path)
    if (
        journal_path in inputs
        or output_path in (*inputs, journal_path)
        or not journal_path.parent.is_dir()
        or (journal_path.exists() and not journal_path.is_file())
        or not output_path.parent.is_dir()
    ):
        raise OnboardingRejected("output_or_journal_invalid")
    if format not in ("codex", "mcp-json", "claude-desktop"):
        raise OnboardingRejected("client_format_invalid")
    sweep_path = None if sweep_journal is None else _local_path(sweep_journal)
    if sweep_path is not None and (
        sweep_path in (*inputs, journal_path, output_path)
        or not sweep_path.parent.is_dir()
        or (sweep_path.exists() and not sweep_path.is_file())
    ):
        raise OnboardingRejected("output_or_journal_invalid")
    # Freeze defaults explicitly, excluding inherited terminal CADENCE_MCP_* overrides.
    config = BridgeConfig(**{k: f.default for k, f in BridgeConfig.model_fields.items()})
    settings = config.model_dump(mode="json")
    settings.update(
        design_registry_path=str(design_path),
        pdk_registry_path=str(pdk_path),
        analysis_journal_path=str(journal_path),
        sweep_journal_path=None if sweep_path is None else str(sweep_path),
    )
    env = {"CADENCE_MCP_" + k.upper(): str(v) for k, v in settings.items() if v is not None}
    env["PYTHONUTF8"] = "1"
    server: dict[str, object] = {
        "command": str(_local_path(Path(sys.executable))),
        "args": ["-m", "cadence_mcp_bridge", "serve"],
        "env": env,
    }
    name = "cadence-mcp-bridge"
    if format in ("mcp-json", "claude-desktop"):
        content = json.dumps({"mcpServers": {name: server}}, indent=2, ensure_ascii=True) + "\n"
    else:
        quote = json.dumps
        lines = [
            "# Operator-owned private fragment. Review before installing.",
            "# Registration does not qualify generic execution or grant remote authority.",
            f"[mcp_servers.{name}]",
            f"command = {quote(server['command'])}",
            f"args = {quote(server['args'])}",
            "startup_timeout_sec = 20",
            "tool_timeout_sec = 180",
            "enabled = true",
            "required = true",
            'default_tools_approval_mode = "writes"',
            f"\n[mcp_servers.{name}.env]",
            *(f"{k} = {quote(v)}" for k, v in sorted(env.items())),
        ]
        for tool in _PROMPT_TOOLS:
            lines.extend([f"\n[mcp_servers.{name}.tools.{tool}]", 'approval_mode = "prompt"'])
        content = "\n".join(lines) + "\n"
    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return {
        **snapshot.report(),
        "status": "exported_local_only",
        "format": format,
        "client_config_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "client_installation": "operator_review_required",
        "journal_created": False,
    }
