from __future__ import annotations

import copy
import hashlib
import io
import json
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge import _environment_probe as probe
from cadence_mcp_bridge import environments as env
from cadence_mcp_bridge.config import BridgeConfig

NOW = datetime(2026, 1, 1, tzinfo=UTC)
NONCE = "1" * 32


def profile_data() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "environment_id": "fictional-lab",
        "ssh_alias": "fictional-host",
        "host": {
            "hostname": "fictional",
            "user": "operator",
            "os": "Linux",
            "architecture": "x86_64",
            "python_version": "3.12.1",
        },
        "paths": {
            "workspace_root": "/srv/project",
            "managed_root": "/srv/project/.cadence_mcp",
            "job_root": "/srv/project/.cadence_mcp/jobs",
            "result_root": "/srv/project/.cadence_mcp/jobs",
            "protected_roots": ["/opt/eda", "/srv/project/source", "/srv/project/pdk"],
        },
        "tools": {
            name: {"path": f"/opt/eda/bin/{name}", "sha256": "a" * 64, "version": "fictional-1.0"}
            for name in ("virtuoso", "spectre", "ocean")
        },
        "limits": {
            "disk_floor_bytes": 2_147_483_648,
            "disk_floor_percent": 10,
            "spectre_attempts": 0,
            "result_reserved_bytes": 0,
            "eda_concurrency": 1,
            "paid_resources": 0,
        },
        "requested_capabilities": ["ade_native", "dc", "ac", "tran", "psf_extraction"],
    }


def binding(data: dict[str, Any] | None = None) -> tuple[env.EnvironmentProfile, bytes]:
    encoded = json.dumps(profile_data() if data is None else data).encode()
    return env.EnvironmentProfile.model_validate_json(encoded), encoded


def observation(profile: env.EnvironmentProfile, data: bytes) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "environment_id": profile.environment_id,
        "profile_sha256": hashlib.sha256(data).hexdigest(),
        "probe_sha256": hashlib.sha256(env.probe_bytes()).hexdigest(),
        "nonce": NONCE,
        "observed_at": NOW.isoformat(),
        "host": profile.host.model_dump(mode="json"),
        "tools": {
            name: {
                "available": True,
                "sha256": "a" * 64,
                "version": "fictional-1.0" if name != "ocean" else None,
                "version_observed": name != "ocean",
            }
            for name in ("virtuoso", "spectre", "ocean")
        },
        "workspace_writable": True,
        "writability_method": "os_access_no_write_test",
        "root_containment": True,
        "protected_roots_disjoint": True,
        "free_bytes": 8 * 1024**3,
        "total_bytes": 16 * 1024**3,
        "license_environment": {"CDS_LIC_FILE": "SET", "LM_LICENSE_FILE": "UNSET"},
    }


def parsed(value: dict[str, Any]) -> env.EnvironmentObservation:
    return env.EnvironmentObservation.model_validate_json(json.dumps(value))


def test_qualification_is_not_simulation_authority() -> None:
    profile, data = binding()
    report = env.qualify_observation(
        profile, data, parsed(observation(profile, data)), NONCE, now=NOW
    )
    assert report["status"] == "qualified_environment_preflight"
    assert report["execution_authorized"] is False
    assert set(report["capabilities"].values()) == {"unqualified"}  # type: ignore[union-attr]
    assert report["license_status"] == "configured_entitlement_unqualified"
    assert "/srv/project" not in json.dumps(report)
    assert BridgeConfig().ssh_alias == "cadence-vm"


@pytest.mark.parametrize(
    "value",
    [
        "../p",
        "/srv/../p",
        "/srv//p",
        "/srv/./p",
        "/",
        "/srv/p;id",
        "/srv/p\n",
        "/srv/p$HOME",
        "/srv/p`id`",
        "/srv/p*",
        "/srv/한글",
    ],
)
def test_private_paths_reject_injection_and_noncanonical_roots(value: str) -> None:
    candidate = profile_data()
    candidate["paths"]["workspace_root"] = value
    with pytest.raises((ValueError, ValidationError)):
        binding(candidate)
    with pytest.raises(ValueError):
        probe.validate_profile(candidate)


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("ssh_alias", "-oProxyCommand=id"),
        ("ssh_alias", "host\n"),
        ("environment_id", "x/../../bin"),
        ("environment_id", "x\n"),
        ("command", "id"),
        ("execution_authorized", True),
    ],
)
def test_profile_is_closed_and_not_authority(key: str, value: Any) -> None:
    candidate = profile_data()
    candidate[key] = value
    with pytest.raises(ValueError):
        binding(candidate)
    with pytest.raises(ValueError):
        probe.validate_profile(candidate)


@pytest.mark.parametrize(
    "root",
    ["/srv", "/srv/project", "/srv/project/.cadence_mcp", "/srv/project/.cadence_mcp/jobs/pdk"],
)
def test_protected_roots_cannot_overlap_managed_writes(root: str) -> None:
    candidate = profile_data()
    candidate["paths"]["protected_roots"].append(root)
    with pytest.raises(ValueError):
        binding(candidate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("disk_floor_bytes", 1),
        ("disk_floor_percent", 9),
        ("eda_concurrency", 2),
        ("eda_concurrency", True),
        ("paid_resources", 1),
        ("paid_resources", False),
        ("spectre_attempts", -1),
        ("result_reserved_bytes", True),
    ],
)
def test_resource_description_cannot_weaken_minimum_guards(field: str, value: Any) -> None:
    candidate = profile_data()
    candidate["limits"][field] = value
    with pytest.raises(ValueError):
        binding(candidate)
    with pytest.raises(ValueError):
        probe.validate_profile(candidate)


@pytest.mark.parametrize("capabilities", [["shell"], ["dc", "dc"], ["monte_carlo"], ["stb"]])
def test_capability_requests_are_bounded_declarations(capabilities: list[str]) -> None:
    candidate = profile_data()
    candidate["requested_capabilities"] = capabilities
    with pytest.raises(ValueError):
        binding(candidate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("path", "/tmp/virtuoso"),
        ("path", "/opt/eda/bin/python"),
        ("sha256", "a" * 64 + "\n"),
        ("version", "1.0\n"),
        ("script", "exit()"),
    ],
)
def test_tool_bindings_are_allowlisted(field: str, value: str) -> None:
    candidate = profile_data()
    candidate["tools"]["virtuoso"][field] = value
    with pytest.raises(ValueError):
        binding(candidate)


@pytest.mark.parametrize(
    "field,value",
    [
        ("nonce", "2" * 32),
        ("profile_sha256", "b" * 64),
        ("probe_sha256", "c" * 64),
        ("environment_id", "other-lab"),
        ("root_containment", False),
        ("protected_roots_disjoint", False),
        ("workspace_writable", False),
        ("free_bytes", 100),
        ("free_bytes", 20 * 1024**3),
    ],
)
def test_invalid_observations_fail_closed(field: str, value: Any) -> None:
    profile, data = binding()
    obs = observation(profile, data)
    obs[field] = value
    with pytest.raises(ValueError):
        env.qualify_observation(profile, data, parsed(obs), NONCE, now=NOW)


@pytest.mark.parametrize("age", [-6, 61, 3600])
def test_stale_or_future_observations_rejected(age: int) -> None:
    profile, data = binding()
    obs = observation(profile, data)
    obs["observed_at"] = (NOW - timedelta(seconds=age)).isoformat()
    with pytest.raises(ValueError, match="stale"):
        env.qualify_observation(profile, data, parsed(obs), NONCE, now=NOW)


@pytest.mark.parametrize(
    "name,field,value",
    [
        ("spectre", "sha256", "b" * 64),
        ("virtuoso", "version", "wrong"),
        ("ocean", "version_observed", True),
        ("ocean", "available", False),
        ("spectre", "version_observed", False),
    ],
)
def test_observed_tools_require_exact_bindings(name: str, field: str, value: Any) -> None:
    profile, data = binding()
    obs = observation(profile, data)
    obs["tools"][name][field] = value
    with pytest.raises(ValueError):
        env.qualify_observation(profile, data, parsed(obs), NONCE, now=NOW)


def test_profile_size_duplicate_fields_and_exclusive_bundle(tmp_path: Path) -> None:
    _, data = binding()
    path = tmp_path / "profile.json"
    path.write_bytes(data)
    report = env.prepare_environment(path, tmp_path / "bundle")
    assert report["execution_authorized"] is False
    assert (tmp_path / "bundle/profile.json").read_bytes() == data
    assert (tmp_path / "bundle/probe.py").read_bytes() == env.probe_bytes()
    with pytest.raises(FileExistsError):
        env.prepare_environment(path, tmp_path / "bundle")
    path.write_bytes(b'{"schema_version":1,' + data[1:])
    with pytest.raises(ValueError, match="duplicate"):
        env.load_environment(path)
    path.write_bytes(b" " * 32769)
    with pytest.raises(ValueError, match="large"):
        env.load_environment(path)


def test_operator_transport_has_no_execution_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile, data = binding()
    path = tmp_path / "private.json"
    path.write_bytes(data)
    obs = observation(profile, data)
    obs["observed_at"] = datetime.now(UTC).isoformat()
    child = MagicMock()
    child.stdout = io.BytesIO(json.dumps(obs).encode())
    child.stderr = io.BytesIO()
    child.wait.return_value = 0
    child.poll.return_value = 0
    factory = MagicMock(return_value=child)
    monkeypatch.setattr(env.shutil, "which", lambda _: "ssh.exe")
    monkeypatch.setattr(env.subprocess, "Popen", factory)
    monkeypatch.setattr(env, "uuid4", lambda: UUID(NONCE))
    report = env.qualify_environment(path)
    assert report["execution_authorized"] is False
    args, kwargs = factory.call_args
    assert args[0][-6:-3] == ["/usr/bin/python", "-B", profile.probe_path]
    assert args[0][-1] == NONCE
    assert "BatchMode=yes" in args[0] and "StrictHostKeyChecking=yes" in args[0]
    assert kwargs["shell"] is False and kwargs["stdin"] == env.subprocess.DEVNULL
    assert factory.call_count == 1


def test_errors_do_not_echo_private_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "private.json"
    path.write_text('{"license_secret":"never-return-this"}')
    assert cli.main(["environment", "validate", "--profile", str(path)]) == 1
    output = capsys.readouterr().out
    assert "never-return-this" not in output and str(path) not in output
    assert json.loads(output)["status"] == "blocked"


def test_schema_and_doctor_do_not_connect(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(env.subprocess, "Popen", MagicMock(side_effect=AssertionError("transport")))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "ssh.exe")
    assert cli.main(["environment", "schema"]) == 0
    assert json.loads(capsys.readouterr().out)["additionalProperties"] is False
    assert cli.main(["doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["remote_contact"] is False


def test_guest_hash_limit_and_exact_regex(tmp_path: Path) -> None:
    value = tmp_path / "safe"
    value.write_bytes(b"fictional")
    assert probe.digest_file(str(value)) == hashlib.sha256(b"fictional").hexdigest()
    assert probe.matches(probe.TOKEN, "safe-host")
    assert not probe.matches(probe.TOKEN, "safe-host\n")
    assert not probe.matches(probe.TOKEN, 1)
    candidate = copy.deepcopy(profile_data())
    assert probe.validate_profile(candidate) == candidate


def mock_guest(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    candidate = profile_data()
    host = candidate["host"]
    for method, key in (
        ("node", "hostname"),
        ("system", "os"),
        ("machine", "architecture"),
        ("python_version", "python_version"),
    ):
        monkeypatch.setattr(probe.platform, method, lambda key=key: host[key])
    monkeypatch.setitem(
        sys.modules,
        "pwd",
        SimpleNamespace(getpwuid=lambda _: SimpleNamespace(pw_name=host["user"])),
    )
    monkeypatch.setattr(probe.os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(probe.os.path, "realpath", lambda value: value)
    monkeypatch.setattr(probe.os.path, "isdir", lambda _: True)
    monkeypatch.setattr(probe.os.path, "isfile", lambda _: True)
    monkeypatch.setattr(probe.os, "access", lambda *_: True)
    monkeypatch.setattr(
        probe.os,
        "stat",
        lambda value: SimpleNamespace(st_dev=1, st_ino=42, st_mode=stat.S_IFREG | 0o755),
    )
    monkeypatch.setattr(
        probe.os,
        "statvfs",
        lambda _: SimpleNamespace(f_bavail=8 * 1024**3, f_blocks=16 * 1024**3, f_frsize=1),
        raising=False,
    )
    monkeypatch.setattr(probe, "digest_file", lambda _: "a" * 64)
    monkeypatch.setattr(probe, "version_matches", lambda *_: True)
    monkeypatch.setenv("CDS_LIC_FILE", "DO_NOT_EXPOSE_THIS_LICENSE_VALUE")
    return candidate


def test_guest_observes_only_preflight_and_license_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = mock_guest(monkeypatch)
    versions = MagicMock(return_value=True)
    monkeypatch.setattr(probe, "version_matches", versions)
    result = probe.observe(candidate, "b" * 64, "c" * 64, NONCE)
    assert result["license_environment"]["CDS_LIC_FILE"] == "SET"
    assert "DO_NOT_EXPOSE_THIS_LICENSE_VALUE" not in json.dumps(result)
    assert "paths" not in result and result["writability_method"] == "os_access_no_write_test"
    assert versions.call_count == 2
    assert all(call.args[0].endswith(("virtuoso", "spectre")) for call in versions.call_args_list)
    assert result["tools"]["ocean"]["version_observed"] is False


@pytest.mark.parametrize(
    "failure",
    [
        "host",
        "root_symlink",
        "writable",
        "escape",
        "permissions",
        "parent_permissions",
        "hash",
        "version",
        "post_hash",
        "post_inode",
        "post_resolution",
        "disk",
    ],
)
def test_guest_preflight_rejects_real_observation_guards(
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    candidate = mock_guest(monkeypatch)
    versions = MagicMock(return_value=True)
    monkeypatch.setattr(probe, "version_matches", versions)
    if failure == "host":
        monkeypatch.setattr(probe.platform, "node", lambda: "different-host")
    elif failure == "root_symlink":
        monkeypatch.setattr(probe.os.path, "realpath", lambda value: "/different")
    elif failure == "writable":
        monkeypatch.setattr(probe.os, "access", lambda *_: False)
    elif failure == "escape":
        monkeypatch.setattr(
            probe.os.path,
            "realpath",
            lambda value: "/tmp/virtuoso" if value.endswith("virtuoso") else value,
        )
    elif failure in ("permissions", "parent_permissions"):
        monkeypatch.setattr(
            probe.os,
            "stat",
            lambda value: SimpleNamespace(
                st_dev=1,
                st_ino=42,
                st_mode=stat.S_IFREG
                | (
                    0o777
                    if value.endswith("virtuoso")
                    or (failure == "parent_permissions" and value == "/opt/eda/bin")
                    else 0o755
                ),
            ),
        )
        if failure == "parent_permissions":
            # Keep the executable safe; only the ancestor is writable.
            monkeypatch.setattr(
                probe.os,
                "stat",
                lambda value: SimpleNamespace(
                    st_dev=1,
                    st_ino=42,
                    st_mode=stat.S_IFREG | (0o777 if value == "/opt/eda/bin" else 0o755),
                ),
            )
    elif failure == "hash":
        monkeypatch.setattr(probe, "digest_file", lambda _: "0" * 64)
    elif failure == "version":
        versions.return_value = False
    elif failure == "post_hash":
        monkeypatch.setattr(
            probe, "digest_file", lambda _: "0" * 64 if versions.called else "a" * 64
        )
    elif failure == "post_inode":
        monkeypatch.setattr(
            probe.os,
            "stat",
            lambda value: SimpleNamespace(
                st_dev=1, st_ino=43 if versions.called else 42, st_mode=stat.S_IFREG | 0o755
            ),
        )
    elif failure == "post_resolution":
        monkeypatch.setattr(
            probe.os.path,
            "realpath",
            lambda value: "/opt/eda/other/virtuoso" if versions.called else value,
        )
    elif failure == "disk":
        monkeypatch.setattr(
            probe.os,
            "statvfs",
            lambda _: SimpleNamespace(f_bavail=1, f_blocks=16 * 1024**3, f_frsize=1),
        )
    with pytest.raises(ValueError):
        probe.observe(candidate, "b" * 64, "c" * 64, NONCE)
    if failure in ("permissions", "parent_permissions", "hash", "escape"):
        versions.assert_not_called()


@pytest.mark.parametrize("case", ["success", "overflow", "timeout", "nonzero", "descendant"])
def test_fixed_guest_version_reader_caps_and_closes_process_group(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    child = MagicMock()
    child.pid = 123
    child.poll.return_value = None if case == "timeout" else 0
    child.wait.return_value = 42 if case == "nonzero" else 0
    factory = MagicMock(return_value=child)
    monkeypatch.setattr(probe.subprocess, "Popen", factory)
    monkeypatch.setattr(probe.os, "setsid", lambda: None, raising=False)
    monkeypatch.setattr(probe.signal, "SIGKILL", 9, raising=False)
    killer = MagicMock()
    monkeypatch.setattr(probe.os, "killpg", killer, raising=False)
    if case in ("timeout", "descendant"):
        clock = iter([0, 0, 9])
        monkeypatch.setattr(probe.time, "time", lambda: next(clock))
        monkeypatch.setattr(probe.select, "select", lambda *_: ([], [], []))
    else:
        monkeypatch.setattr(probe.select, "select", lambda *_: ([child.stdout], [], []))
        chunks = iter([b"x" * 4097 if case == "overflow" else b"version fictional-1.0", b""])
        monkeypatch.setattr(probe.os, "read", lambda *_: next(chunks))
    if case == "success":
        assert probe.version_matches("/fictional/virtuoso", "fictional-1.0") is True
    else:
        with pytest.raises(ValueError):
            probe.version_matches("/fictional/virtuoso", "fictional-1.0")
    assert factory.call_args.args[0] == ["/fictional/virtuoso", "-W"]
    assert factory.call_args.kwargs["preexec_fn"] == probe.os.setsid
    killer.assert_called_once_with(123, probe.signal.SIGKILL)
    child.stdout.close.assert_called_once()


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("executable_permissions", "executable_permissions"),
        ("private-path-license-secret", "environment_probe_failed"),
    ],
)
def test_remote_rejection_codes_do_not_disclose_private_messages(
    reason: str, expected: str
) -> None:
    assert env.EnvironmentRejected(reason).reason == expected


@pytest.mark.parametrize(
    "size,code,stderr",
    [
        (32769, 0, b""),
        (0, 1, b"executable_permissions\n"),
        (0, 1, b"private-license-secret"),
        (0, 0, b"warning"),
    ],
)
def test_operator_transport_rejects_overflow_and_remote_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    size: int,
    code: int,
    stderr: bytes,
) -> None:
    _, data = binding()
    path = tmp_path / "private.json"
    path.write_bytes(data)
    child = MagicMock()
    child.stdout, child.stderr = io.BytesIO(b"X" * size), io.BytesIO(stderr)
    child.poll.return_value = code
    child.wait.return_value = code
    factory = MagicMock(return_value=child)
    monkeypatch.setattr(env.shutil, "which", lambda _: "ssh.exe")
    monkeypatch.setattr(env.subprocess, "Popen", factory)
    with pytest.raises(ValueError) as rejected:
        env.qualify_environment(path)
    assert "private-license-secret" not in str(rejected.value)
    assert factory.call_count == 1
