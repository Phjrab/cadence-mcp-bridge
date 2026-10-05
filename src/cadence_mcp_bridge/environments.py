"""Operator-owned environment contracts and read-only qualification, outside MCP."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cadence_mcp_bridge import _environment_probe as probe
from cadence_mcp_bridge.ssh_backend import OpenSshBackend

LogicalId = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
Token = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Capability = Literal["ade_native", "dc", "ac", "tran", "psf_extraction"]


class EnvironmentRejected(ValueError):
    """Only a closed, non-sensitive remote rejection code may reach CLI output."""

    def __init__(self, reason: str) -> None:
        self.reason = reason if reason in probe.PUBLIC_REASONS else "environment_probe_failed"
        super().__init__(self.reason)


class EnvironmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def reject_boolean_version(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value


class HostRequirements(EnvironmentModel):
    hostname: Token
    user: Token
    os: Literal["Linux"]
    architecture: Token
    python_version: Token


class EnvironmentPaths(EnvironmentModel):
    workspace_root: str
    managed_root: str
    job_root: str
    result_root: str
    protected_roots: tuple[str, ...]


class ExecutableBinding(EnvironmentModel):
    path: str
    sha256: Digest
    version: Token


class CadenceExecutables(EnvironmentModel):
    virtuoso: ExecutableBinding
    spectre: ExecutableBinding
    ocean: ExecutableBinding


class EnvironmentLimits(EnvironmentModel):
    disk_floor_bytes: Annotated[int, Field(ge=2_147_483_648, le=1_099_511_627_776)]
    disk_floor_percent: Annotated[int, Field(ge=10, le=100)]
    spectre_attempts: Annotated[int, Field(ge=0, le=1_000_000)]
    result_reserved_bytes: Annotated[int, Field(ge=0, le=1_099_511_627_776)]
    eda_concurrency: Literal[1]
    paid_resources: Literal[0]

    @field_validator("eda_concurrency", "paid_resources", mode="before")
    @classmethod
    def integer_constants(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("integer resource limit required")
        return value


class EnvironmentProfile(EnvironmentModel):
    """A description is never registration or execution authority."""

    schema_version: Literal[1]
    environment_id: LogicalId
    ssh_alias: Token
    host: HostRequirements
    paths: EnvironmentPaths
    tools: CadenceExecutables
    limits: EnvironmentLimits
    requested_capabilities: tuple[Capability, ...]

    @model_validator(mode="after")
    def check_contract(self) -> Self:
        probe.validate_profile(self.model_dump(mode="json"))  # type: ignore[no-untyped-call]
        return self

    @property
    def probe_path(self) -> str:
        return f"{self.paths.managed_root}/environments/{self.environment_id}/v1/probe.py"


class ObservedTool(EnvironmentModel):
    available: bool
    sha256: Digest
    version: Token | None
    version_observed: bool


class ObservedTools(EnvironmentModel):
    virtuoso: ObservedTool
    spectre: ObservedTool
    ocean: ObservedTool


class LicenseFlags(EnvironmentModel):
    CDS_LIC_FILE: Literal["SET", "UNSET"]
    LM_LICENSE_FILE: Literal["SET", "UNSET"]


class EnvironmentObservation(EnvironmentModel):
    schema_version: Literal[1]
    environment_id: LogicalId
    profile_sha256: Digest
    probe_sha256: Digest
    nonce: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    observed_at: datetime
    host: HostRequirements
    tools: ObservedTools
    workspace_writable: bool
    writability_method: Literal["os_access_no_write_test"]
    root_containment: bool
    protected_roots_disjoint: bool
    free_bytes: Annotated[int, Field(ge=0, le=2**63 - 1)]
    total_bytes: Annotated[int, Field(gt=0, le=2**63 - 1)]
    license_environment: LicenseFlags


def _closed_json(data: bytes) -> None:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ValueError("nonfinite JSON")

    if len(data) > probe.PROFILE_LIMIT:
        raise ValueError("environment document too large")
    json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def load_environment(path: Path) -> tuple[EnvironmentProfile, bytes]:
    """Explicit local operator path; never accepted by an MCP execution tool."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular environment profile required")
    with path.open("rb") as stream:
        data = stream.read(probe.PROFILE_LIMIT + 1)
    _closed_json(data)
    return EnvironmentProfile.model_validate_json(data), data


def probe_bytes() -> bytes:
    return files("cadence_mcp_bridge").joinpath("_environment_probe.py").read_bytes()


def prepare_environment(path: Path, output: Path) -> dict[str, object]:
    profile, data = load_environment(path)
    # Exclusive creation prevents changing an existing approved bundle or evidence.
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, content in (("profile.json", data), ("probe.py", probe_bytes())):
        target = output / name
        with target.open("xb") as stream:
            stream.write(content)
        target.chmod(0o600)
    return {
        "environment_id": profile.environment_id,
        "status": "prepared_local_only",
        "profile_sha256": hashlib.sha256(data).hexdigest(),
        "probe_sha256": hashlib.sha256(probe_bytes()).hexdigest(),
        "execution_authorized": False,
    }


def qualify_observation(
    profile: EnvironmentProfile,
    data: bytes,
    observation: EnvironmentObservation,
    nonce: str,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Qualifies only bounded environment preflight; no capability or budget activation."""
    if (
        observation.environment_id != profile.environment_id
        or observation.profile_sha256 != hashlib.sha256(data).hexdigest()
        or observation.probe_sha256 != hashlib.sha256(probe_bytes()).hexdigest()
        or observation.nonce != nonce
        or observation.host != profile.host
    ):
        raise ValueError("environment observation binding mismatch")
    clock = datetime.now(UTC) if now is None else now
    if observation.observed_at.tzinfo is None or clock.tzinfo is None:
        raise ValueError("timezone required")
    age = (clock - observation.observed_at).total_seconds()
    if not -5 <= age <= 60:
        raise ValueError("environment observation is stale")
    if not all(
        (
            observation.root_containment,
            observation.protected_roots_disjoint,
            observation.workspace_writable,
        )
    ):
        raise ValueError("environment root checks failed")
    floor = max(
        profile.limits.disk_floor_bytes,
        (observation.total_bytes * profile.limits.disk_floor_percent + 99) // 100,
    )
    if observation.free_bytes > observation.total_bytes or observation.free_bytes < floor:
        raise ValueError("environment disk floor failed")
    for name in ("virtuoso", "spectre", "ocean"):
        expected: ExecutableBinding = getattr(profile.tools, name)
        actual: ObservedTool = getattr(observation.tools, name)
        if not actual.available or actual.sha256 != expected.sha256:
            raise ValueError("environment executable binding failed")
        if name != "ocean" and (not actual.version_observed or actual.version != expected.version):
            raise ValueError("environment executable version failed")
        if name == "ocean" and (actual.version_observed or actual.version is not None):
            raise ValueError("OCEAN version must remain unobserved by this probe")
    return {
        "environment_id": profile.environment_id,
        "status": "qualified_environment_preflight",
        "qualification_scope": "identity_runtime_binary_roots_disk",
        "observed_at": observation.observed_at.isoformat(),
        "profile_sha256": observation.profile_sha256,
        "probe_sha256": observation.probe_sha256,
        "ssh": "available",
        "license_status": "configured_entitlement_unqualified"
        if "SET"
        in (
            observation.license_environment.CDS_LIC_FILE,
            observation.license_environment.LM_LICENSE_FILE,
        )
        else "unconfigured_entitlement_unqualified",
        "ocean_version": "not_observed",
        "workspace_writability": observation.writability_method,
        "protected_roots": "disjoint_containment_checked_no_content_read",
        "capabilities": dict.fromkeys(profile.requested_capabilities, "unqualified"),
        "resource_limits": "declared_only_existing_ledger_not_reset_or_activated",
        "execution_authorized": False,
    }


def qualify_environment(path: Path) -> dict[str, object]:
    profile, data = load_environment(path)
    executable = shutil.which("ssh.exe")
    if executable is None:
        raise ValueError("Windows OpenSSH unavailable")
    nonce = uuid4().hex
    argv = [
        executable,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=2",
        profile.ssh_alias,
        "/usr/bin/python",
        "-B",
        profile.probe_path,
        hashlib.sha256(data).hexdigest(),
        hashlib.sha256(probe_bytes()).hexdigest(),
        nonce,
    ]
    # This operator-only call has exactly one fixed probe operation and no retries.
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        env=OpenSshBackend._ssh_environment(),
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    deadline = time.monotonic() + 45
    with ThreadPoolExecutor(max_workers=2) as pool:
        out = pool.submit(process.stdout.read, probe.PROFILE_LIMIT + 1)
        err = pool.submit(process.stderr.read, probe.PROFILE_LIMIT + 1)
        try:
            stdout = out.result(timeout=max(0.01, deadline - time.monotonic()))
            stderr = err.result(timeout=max(0.01, deadline - time.monotonic()))
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
            process.stderr.close()
    if code != 0 or stderr or len(stdout) > probe.PROFILE_LIMIT:
        if code == 1 and not stdout and len(stderr) < 128:
            raise EnvironmentRejected(stderr.decode("ascii", errors="replace").strip())
        raise ValueError("environment probe unavailable or rejected")
    _closed_json(stdout)
    observed = EnvironmentObservation.model_validate_json(stdout)
    return qualify_observation(profile, data, observed, nonce)
