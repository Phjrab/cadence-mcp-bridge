"""Disposable actual Windows installation, protocol and preservation checks. No VM."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters


def run(
    args: list[str],
    env: dict[str, str],
    cwd: Path,
    *,
    code: int | None = 0,
    request: dict | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        timeout=timeout,
        input=None if request is None else json.dumps(request).encode(),
    )
    if code is not None and result.returncode != code:
        raise AssertionError(
            (Path(args[0]).name, result.returncode, result.stdout[-1200:], result.stderr[-1200:])
        )
    return result


async def protocol(launcher: Path, env: dict[str, str]) -> dict[str, object]:
    async with Client(
        StdioServerParameters(command=str(launcher), args=["serve-operator"], env=env)
    ) as client:
        listed = await client.list_tools()
        names = [tool.name for tool in listed.tools]
        assert "cadence_runtime_info_v2" in names
        result = await client.call_tool("cadence_runtime_info_v2", {})
        assert not result.is_error
        serialized = json.dumps(result.model_dump(mode="json"))
        assert "loaded_local_configuration" in serialized
        return {
            "tool_count": len(names),
            "runtime_info_read": True,
            "actual_app_verified": False,
            "remote_contact": False,
        }


def verify(installer: Path, root: Path) -> dict[str, object]:
    if os.name != "nt" or root.exists():
        raise ValueError("Windows and a new disposable root required")
    root.mkdir(parents=True)
    install = root / "한글 사용자" / "Programs with spaces" / "2.2.0a1"
    clean_cwd = root / "no-checkout"
    clean_cwd.mkdir()
    user = root / "user-data"
    user.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("CADENCE_MCP_")
        and key.upper() not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
    }
    env.update(
        PATH=str(Path(os.environ["SYSTEMROOT"]) / "System32"),
        CODEX_HOME=str(user / "codex-home"),
        LOCALAPPDATA=str(user),
        APPDATA=str(user),
        USERPROFILE=str(user),
        PYTHONPATH=str(root / "poison"),
        PYTHONHOME=str(root / "missing-system-python"),
        PYTHONUTF8="1",
    )
    for tool in ("python", "git", "uv", "pip"):
        assert shutil.which(tool, path=env["PATH"]) is None
    options = [
        str(installer),
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/CURRENTUSER",
        "/NOICONS",
        "/DIR=" + str(install),
    ]
    run([*options, "/LOG=" + str(root / "install.log")], env, clean_cwd)
    launcher = install / "CadenceMCPBridge.exe"
    python = install / "runtime/python.exe"
    assert run([str(launcher), "--version"], env, clean_cwd).stdout.strip() == b"2.2.0a1"
    assert (
        run([str(launcher), "--host-verify"], env, clean_cwd).stdout.strip()
        == b"HOST_PAYLOAD_VERIFIED"
    )
    doctor = json.loads(run([str(launcher), "doctor"], env, clean_cwd, code=None).stdout)
    assert doctor["remote_contact"] is False and not doctor["ssh_available"]
    bare = run([str(launcher)], env, clean_cwd, code=None)
    # Bare launch is a stdio server: EOF exits silently, not a diagnostic stream.
    assert bare.returncode == 0 and not bare.stdout
    unset = json.loads(
        run(
            [str(launcher), "config-check"],
            {**env, "CADENCE_MCP_RUNTIME_MODE": "operator"},
            clean_cwd,
        ).stdout
    )
    assert unset["status"] == "SETUP_REQUIRED" and unset["remote_contact"] is False
    backend = [
        str(python),
        "-I",
        "-B",
        "-X",
        "utf8",
        "-m",
        "cadence_mcp_bridge.windows_host.backend",
    ]
    status = json.loads(run(backend, env, clean_cwd, request={"action": "status"}).stdout)
    assert status["isolated"] and status["version"] == "2.2.0a1"
    starter = user / "registered-inputs"
    run([str(launcher), "operator-starter", "--output", str(starter)], env, clean_cwd)
    runtime = user / "runtime.json"
    journal, sweep = user / "analysis.sqlite3", user / "sweep.sqlite3"
    run(
        [
            str(launcher),
            "operator-setup",
            "export-runtime",
            "--profile",
            str(starter / "environment.json"),
            "--design-registry",
            str(starter / "designs.json"),
            "--pdk-registry",
            str(starter / "pdks.json"),
            "--resource-state-root",
            str(user),
            "--context",
            "fixture-context",
            "--runner-sha256",
            "b" * 64,
            "--authority-ref",
            "fixture-not-authorized",
            "--ledger-ref",
            "retained-fixture-only",
            "--journal",
            str(journal),
            "--sweep-journal",
            str(sweep),
            "--output",
            str(runtime),
        ],
        env,
        clean_cwd,
    )
    before_runtime = runtime.read_bytes()
    imported = json.loads(
        run(
            backend,
            env,
            clean_cwd,
            request={"action": "runtime", "settings": str(runtime), "context": "fixture-context"},
        ).stdout
    )
    assert imported["status"] == "LOCAL_CONTEXT_VALID"
    assert runtime.read_bytes() == before_runtime and not journal.exists() and not sweep.exists()
    config = Path(env["CODEX_HOME"]) / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '# retained user comment\nmodel = "user-choice"\n'
        '[mcp_servers.other]\ncommand="other.exe"\n',
        encoding="utf-8",
    )
    plan = json.loads(
        run(
            backend,
            env,
            clean_cwd,
            request={
                "action": "preview",
                "settings": str(runtime),
                "context": "fixture-context",
                "name": "cadence-setup-test",
            },
        ).stdout
    )
    result = json.loads(
        run(
            backend,
            env,
            clean_cwd,
            request={"action": "apply", "consent": True, "after": plan["after"]},
        ).stdout
    )
    assert result["status"] == "CLIENT_CONFIGURED" and not result["actual_app_verified"]
    selected = tomllib.loads(config.read_text(encoding="utf-8"))["mcp_servers"][
        "cadence-setup-test"
    ]
    assert selected["command"] == str(launcher)
    protocol_result = asyncio.run(protocol(launcher, {**env, **selected["env"]}))
    # Protocol startup may create local fixture journals; all must survive updates.
    retained = {
        str(path.relative_to(user)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in user.rglob("*")
        if path.is_file()
    }
    run([*options, "/LOG=" + str(root / "reinstall.log")], env, clean_cwd)
    assert retained == {
        str(path.relative_to(user)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in user.rglob("*")
        if path.is_file()
    }
    # Corruption and extra import-hook rejection occur before Python can start.
    target = install / "runtime/Lib/site-packages/cadence_mcp_bridge/__init__.py"
    original = target.read_bytes()
    target.write_bytes(original + b"\n# disposable corruption\n")
    rejected = run([str(launcher), "--version"], env, clean_cwd, code=2)
    assert b"HOST_PAYLOAD_REJECTED" in rejected.stderr
    target.write_bytes(original)
    hook = install / "runtime/Lib/site-packages/unexpected.pth"
    hook.write_text("import pathlib; raise AssertionError('must never execute')\n")
    assert (
        run([str(launcher), "--version"], env, clean_cwd, code=2).stderr.strip()
        == b"HOST_PAYLOAD_REJECTED"
    )
    hook.unlink()
    # A later unrelated user edit must survive automatic exact-entry uninstall.
    with config.open("a", encoding="utf-8") as stream:
        stream.write('\n[mcp_servers.later]\ncommand="later.exe" # preserve me\n')
    protected = {
        str(path.relative_to(user)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in user.rglob("*")
        if path.is_file() and path != config
    }
    run(
        [
            str(install / "unins000.exe"),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/LOG=" + str(root / "uninstall.log"),
        ],
        env,
        clean_cwd,
    )
    assert not launcher.exists()
    after = tomllib.loads(config.read_text(encoding="utf-8"))
    assert "cadence-setup-test" not in after["mcp_servers"]
    assert (
        after["model"] == "user-choice" and after["mcp_servers"]["later"]["command"] == "later.exe"
    )
    assert "# retained user comment" in config.read_text(encoding="utf-8")
    for name, sha in protected.items():
        assert hashlib.sha256((user / name).read_bytes()).hexdigest() == sha
    return {
        "status": "PASS",
        "installer_sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
        "isolation": "PATH hides Python/Git/uv/pip; cwd has no checkout; poisoned PYTHONPATH/HOME",
        "actual_clean_os_image": False,
        "unicode_install": True,
        "reinstall_preserves_data": True,
        "uninstall_preserves_data": True,
        "pre_python_corruption_rejected": True,
        "protocol": protocol_result,
        "remote_contact": False,
        "new_simulations": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    options = parser.parse_args()
    report = verify(options.installer.resolve(strict=True), options.workspace.resolve())
    (options.workspace / "RESULT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
