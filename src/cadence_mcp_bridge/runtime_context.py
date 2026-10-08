"""Immutable operator runtime routing; configuration is not execution authority."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from cadence_mcp_bridge import __version__
from cadence_mcp_bridge.config import BridgeConfig, OperatorTransport
from cadence_mcp_bridge.designs import DesignRegistry, RegistryBase
from cadence_mcp_bridge.environments import Digest, EnvironmentModel, LogicalId, _closed_json
from cadence_mcp_bridge.errors import ConfigurationError
from cadence_mcp_bridge.onboarding import ContractSnapshot, _local_path, load_contracts
from cadence_mcp_bridge.pdk_adapters import PdkRegistry
from cadence_mcp_bridge.runtime_info import (
    JournalSelection,
    LoadedCatalogV2,
    RuntimeInfo,
    RuntimeInfoV2,
)
from cadence_mcp_bridge.variable_contracts import canonical_digest


class RuntimeRejected(ConfigurationError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("Operator runtime configuration rejected", details={"reason": reason})


class ContextBinding(EnvironmentModel):
    context_id: LogicalId
    environment_profile: Path
    environment_sha256: Digest
    design_registry: Path
    design_sha256: Digest
    pdk_registry: Path
    pdk_sha256: Digest
    runner_sha256: Digest
    authority_ref: LogicalId
    ledger_ref: LogicalId
    analysis_journal: Path
    sweep_journal: Path


class RuntimeSettings(EnvironmentModel):
    schema_version: Literal[1]
    resource_state_root: Path
    contexts: Annotated[tuple[ContextBinding, ...], Field(min_length=1, max_length=16)]


@dataclass(frozen=True)
class ExecutionContext:
    binding: ContextBinding
    contracts: ContractSnapshot
    transport: OperatorTransport
    resource_domain_sha256: str
    resource_state_root: Path
    context_sha256: str

    def resolve(self, design_id: str) -> ExecutionContext:
        self.contracts.designs.profile(design_id)
        return self

    @property
    def lock_path(self) -> Path:
        return self.resource_state_root / (self.resource_domain_sha256 + ".lock")

    def backend(self, factory: Callable[[OperatorTransport], Any]) -> Any:
        """Actual transport construction uses the frozen operator bindings."""
        return factory(self.transport)

    def observation(self) -> dict[str, object]:
        return {
            "status": "RUNNER_SETUP_REQUIRED",
            "context_id": self.binding.context_id,
            "context_sha256": self.context_sha256,
            "environment_id": self.contracts.environment.environment_id,
            "design_ids": [d.design_id for d in self.contracts.designs.designs],
            "capabilities": self.contracts.environment.requested_capabilities,
            "states": {
                "registration": "VALID_DESCRIPTION",
                "environment_preflight": "NOT_ASSESSED",
                "analysis_qualification": "NOT_ASSESSED",
                "execution_authority": "NOT_ASSESSED",
                "result_validation": "NOT_RUN",
            },
            "runner_expected_sha256": self.binding.runner_sha256,
            "runner_attestation": "NOT_VERIFIED",
            "authority_ref": self.binding.authority_ref,
            "authority_assessed": False,
            "ledger_ref": self.binding.ledger_ref,
            "ledger_assessed": False,
            "resource_domain_sha256": self.resource_domain_sha256,
            "resource_identity": "declared_host_requires_attestation",
            "execution_authorized": False,
            "legacy_fallback": False,
            "remote_contact": False,
            "journal_health_assessed": False,
            "build": build_provenance(),
        }


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_provenance() -> dict[str, object]:
    # Exact installed package bytes, not a guessed commit or loaded-memory attestation.
    package = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(package.glob("*.py")):
        digest.update(path.name.encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {
        "bridge_version": __version__,
        "package_source_sha256": digest.hexdigest(),
        "source_scope": "installed_package_files_on_disk",
        "commit_sha": None,
        "installation_attested": False,
    }


def _journal(path: Path) -> Path:
    value = _local_path(path)
    if not path.is_absolute() or not value.parent.is_dir():
        raise RuntimeRejected("journal_parent_required")
    if value.exists() and not value.is_file():
        raise RuntimeRejected("journal_invalid")
    return value


def load_runtime(path: Path) -> tuple[ExecutionContext, ...]:
    """Bounded, no-follow local snapshot. Never rewrites journals or budgets."""
    try:
        source = _local_path(path)
        if not path.is_absolute() or not source.is_file():
            raise RuntimeRejected("runtime_file_required")
        with source.open("rb") as stream:
            data = stream.read(65_537)
        _closed_json(data)
        settings = RuntimeSettings.model_validate_json(data)
        state_root = _local_path(settings.resource_state_root)
        if not settings.resource_state_root.is_absolute() or not state_root.is_dir():
            raise RuntimeRejected("resource_state_root_required")
        contexts: list[ExecutionContext] = []
        ids: set[str] = set()
        design_ids: set[str] = set()
        journals: set[Path] = set()
        inputs: set[Path] = {source}
        aliases: dict[str, str] = {}
        environments: dict[str, str] = {}
        domains: dict[str, tuple[str, object]] = {}
        for binding in settings.contexts:
            if binding.context_id in ids:
                raise RuntimeRejected("duplicate_context_id")
            ids.add(binding.context_id)
            paths = (binding.environment_profile, binding.design_registry, binding.pdk_registry)
            if any(not p.is_absolute() for p in paths):
                raise RuntimeRejected("absolute_contract_paths_required")
            inputs.update(_local_path(p) for p in paths)
            snapshot = load_contracts(*paths)
            if (snapshot.environment_sha256, snapshot.design_sha256, snapshot.pdk_sha256) != (
                binding.environment_sha256,
                binding.design_sha256,
                binding.pdk_sha256,
            ):
                raise RuntimeRejected("stale_contract_digest")
            profile = snapshot.environment
            for key, value, catalog in (
                (profile.ssh_alias, snapshot.environment_sha256, aliases),
                (profile.environment_id, snapshot.environment_sha256, environments),
            ):
                if key in catalog and catalog[key] != value:
                    raise RuntimeRejected("environment_alias_conflict")
                catalog[key] = value
            current_ids = {d.design_id for d in snapshot.designs.designs}
            if design_ids & current_ids:
                raise RuntimeRejected("ambiguous_design_id")
            design_ids.update(current_ids)
            # Alias, context ID, username and managed-root changes do not create extra capacity.
            domain = _digest(
                {"hostname": profile.host.hostname, "architecture": profile.host.architecture}
            )
            domain_binding = (binding.ledger_ref, profile.limits)
            if domain in domains and domains[domain] != domain_binding:
                raise RuntimeRejected("shared_resource_policy_conflict")
            domains[domain] = domain_binding
            analysis, sweep = _journal(binding.analysis_journal), _journal(binding.sweep_journal)
            if analysis == sweep or {analysis, sweep} & journals:
                raise RuntimeRejected("journal_context_conflict")
            journals.update((analysis, sweep))
            context_hash = _digest(
                {"binding": binding.model_dump(mode="json"), "resource_domain": domain}
            )
            contexts.append(
                ExecutionContext(
                    binding,
                    snapshot,
                    OperatorTransport(
                        profile.ssh_alias,
                        profile.paths.managed_root,
                        profile.paths.managed_root + "/bin/cadence-operator-runner",
                    ),
                    domain,
                    state_root,
                    context_hash,
                )
            )
        locks = {c.lock_path for c in contexts}
        if journals & inputs or locks & (inputs | journals) or state_root in inputs:
            raise RuntimeRejected("journal_contract_collision")
        return tuple(contexts)
    except RuntimeRejected:
        raise
    except (OSError, ValueError, RecursionError):
        raise RuntimeRejected("runtime_contract_invalid") from None


def select_context(config: BridgeConfig) -> ExecutionContext | None:
    if config.runtime_settings_path is None:
        if config.runtime_context_id is not None:
            raise RuntimeRejected("context_without_settings")
        return None
    contexts = load_runtime(config.runtime_settings_path)
    if config.runtime_context_id is None:
        raise RuntimeRejected("explicit_context_selection_required")
    for context in contexts:
        if context.binding.context_id == config.runtime_context_id:
            return context
    raise RuntimeRejected("unknown_context_id")


def runtime_observation(config: BridgeConfig) -> dict[str, object]:
    if config.runtime_mode == "legacy_reference":
        return {
            "status": "LEGACY_REFERENCE",
            "legacy_fallback": False,
            "execution_authority_assessed": False,
            "remote_contact": False,
            "build": build_provenance(),
        }
    context = select_context(config)
    if context is None:
        return {
            "status": "SETUP_REQUIRED",
            "execution_authorized": False,
            "legacy_fallback": False,
            "remote_contact": False,
            "build": build_provenance(),
        }
    return context.observation()


@contextmanager
def resource_lock(context: ExecutionContext) -> Iterator[None]:
    """Nonblocking OS lock shared by declared resource domain, not context."""
    descriptor = None
    locked = False
    try:
        try:
            path = _local_path(context.lock_path)
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            observed = os.fstat(descriptor)
            current = path.lstat()
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_nlink != 1
                or (observed.st_dev, observed.st_ino) != (current.st_dev, current.st_ino)
                or (
                    os.name != "nt"
                    and (
                        observed.st_uid != getattr(os, "getuid", lambda: -1)()
                        or observed.st_mode & 0o077
                    )
                )
            ):
                raise RuntimeRejected("resource_lock_file_invalid")
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError:
            raise RuntimeRejected("resource_domain_busy_or_invalid") from None
        yield
    finally:
        if descriptor is not None:
            if locked:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl = importlib.import_module("fcntl")

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


class OperatorService:
    """Serve local registered discovery; all unqualified execution paths deny."""

    def __init__(self, context: ExecutionContext | None, backend: Any = None) -> None:
        self.context = context
        self._backend = backend
        self.designs: RegistryBase = (
            DesignRegistry(schema_version=1, designs=())
            if context is None
            else context.contracts.designs
        )
        self.pdks = (
            PdkRegistry(schema_version=2, adapters=())
            if context is None
            else context.contracts.pdks
        )

    def __getattr__(self, name: str) -> Any:
        async def blocked(*args: Any, **kwargs: Any) -> Any:
            status = "SETUP_REQUIRED" if self.context is None else "RUNNER_SETUP_REQUIRED"
            raise ConfigurationError(
                status + ": review operator runtime settings and complete runner bootstrap"
            )

        return blocked

    async def list_designs(self) -> Any:
        return self.designs.listing()

    async def describe_design(self, design_id: str) -> Any:
        return self.designs.describe(design_id)

    async def list_design_variables(self, design_id: str) -> Any:
        return self.designs.variables(design_id)

    async def check_variable_values(self, request: Any) -> Any:
        return self.designs.check_variables(request)

    async def design_pdk_status(self, design_id: str) -> Any:
        design = self.designs.profile(design_id)
        return self.pdks.resolve(design_id, design.pdk_adapter_id, design.environment_id)

    async def list_pdk_adapters(self) -> Any:
        return self.pdks.listing()

    async def describe_pdk_adapter(self, adapter_id: str) -> Any:
        return self.pdks.describe(adapter_id)

    async def runtime_info_v2(self) -> RuntimeInfoV2:
        if self.context is None:
            raise ConfigurationError("SETUP_REQUIRED: no operator runtime journals are selected")
        return RuntimeInfoV2(
            bridge_version=__version__,
            designs=LoadedCatalogV2(
                source="operator_supplied",
                schema_version=self.designs.schema_version,
                entry_count=len(self.designs.designs),
                semantic_sha256=canonical_digest(self.designs),
            ),
            pdks=LoadedCatalogV2(
                source="operator_supplied",
                schema_version=self.pdks.schema_version,
                entry_count=len(self.pdks.adapters),
                semantic_sha256=canonical_digest(self.pdks),
            ),
            journals=JournalSelection(analysis="operator_supplied", sweep="operator_supplied"),
        )

    async def runtime_info(self) -> RuntimeInfo:
        report = await self.runtime_info_v2()
        if report.designs.schema_version > 7:
            raise RuntimeRejected("registry_v8_requires_runtime_info_v2")
        return RuntimeInfo.model_validate({**report.model_dump(), "schema_version": 1})


def create_operator_service(
    config: BridgeConfig,
    factory: Callable[[OperatorTransport], Any] | None = None,
) -> OperatorService:
    from cadence_mcp_bridge.ssh_backend import OpenSshBackend

    context = select_context(config)
    backend = (
        None if context is None else context.backend(OpenSshBackend if factory is None else factory)
    )
    return OperatorService(context, backend)
