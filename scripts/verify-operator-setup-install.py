"""Exercise guided setup from an installed package; preserve the synthetic workspace."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import cadence_mcp_bridge


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(workspace: Path) -> dict[str, str]:
    return {
        path.relative_to(workspace).as_posix(): digest(path)
        for path in sorted(workspace.rglob("*"))
        if path.is_file()
    }


def verify(workspace: Path) -> dict[str, object]:
    if not sys.flags.isolated or not sys.flags.utf8_mode:
        raise ValueError("invoke this verifier with -I -X utf8")
    origin = Path(cadence_mcp_bridge.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()) or "site-packages" not in origin.parts:
        raise ValueError("bridge import must originate from the isolated installed package")
    if importlib.metadata.version("cadence-mcp-bridge") != cadence_mcp_bridge.__version__:
        raise ValueError("installed distribution and runtime versions disagree")
    workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
    empty_path = workspace / "no-external-programs"
    empty_path.mkdir(mode=0o700)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("CADENCE_MCP_")
        and key.upper() not in ("PYTHONPATH", "PYTHONHOME", "PATH")
    }
    environment.update(
        {
            "PATH": str(empty_path),
            "CADENCE_MCP_RUNTIME_MODE": "legacy_reference",
            "CADENCE_MCP_RUNTIME_CONTEXT_ID": "inherited-wrong-context",
            "CADENCE_MCP_RUNTIME_SETTINGS_PATH": str(workspace / "inherited-missing.json"),
            "CADENCE_MCP_SSH_ALIAS": "untrusted-inherited-alias",
            "CADENCE_MCP_REMOTE_ROOT": "/untrusted/inherited/root",
        }
    )
    invocations: list[dict[str, object]] = []

    def cli(arguments: list[str], expected: str, *, rejected: str | None = None) -> dict[str, Any]:
        result = subprocess.run(
            [sys.executable, "-I", "-X", "utf8", "-m", "cadence_mcp_bridge", *arguments],
            cwd=workspace,
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != (1 if rejected else 0):
            raise ValueError(f"setup CLI failed: {result.stdout!r} {result.stderr!r}")
        value: dict[str, Any] = json.loads(result.stdout.decode("utf-8"))
        assert value["status"] == expected
        assert value["execution_authorized"] is False and value["remote_contact"] is False
        assert value["new_simulations"] == 0 and value["new_reservations"] == 0
        if rejected:
            assert value["reason"] == rejected and value["guidance"]
        elif arguments[0] == "operator-setup":
            assert value["generic_execution_qualified"] is False
            assert value["journal_created"] is False
        invocations.append({"command": arguments[:2], "status": expected, "reason": rejected})
        return value

    starter = workspace / "operator 한글 files"
    receipt = cli(
        ["operator-starter", "--output", str(starter)],
        "FICTIONAL_OPERATOR_STARTER_EXPORTED_NOT_AUTHORIZED",
    )
    assert set(receipt["files"]) == {"README.md", "environment.json", "designs.json", "pdks.json"}
    assert all(digest(starter / name) == value for name, value in receipt["files"].items())
    profile, designs, pdks = (
        starter / name for name in ("environment.json", "designs.json", "pdks.json")
    )
    original_environment = json.loads(profile.read_bytes())
    assert original_environment["limits"]["spectre_attempts"] == 0
    assert original_environment["limits"]["result_reserved_bytes"] == 0
    assert all(
        item["work_copy_policy"] == "read_only"
        for item in json.loads(designs.read_bytes())["designs"]
    )
    assert all(
        item["binding_kind"] == "unqualified" for item in json.loads(pdks.read_bytes())["adapters"]
    )
    retained = workspace / "retained-state"
    retained.mkdir(mode=0o700)
    analysis, sweep, ledger = (
        retained / name for name in ("analysis.sqlite3", "sweep.sqlite3", "ledger.json")
    )
    analysis.write_bytes(b"synthetic retained analysis evidence; not a database\n")
    sweep.write_bytes(b"synthetic retained sweep evidence; not a database\n")
    ledger.write_text('{"synthetic":true,"attempts":7,"reserved_bytes":123456}\n', encoding="utf-8")
    protected = inventory(workspace)
    for mode in ("fresh", "existing"):
        before = inventory(workspace)
        guide = cli(["operator-setup", "guide", "--mode", mode], "LOCAL_SETUP_GUIDE")
        assert guide["mode"] == mode
        domain = next(step for step in guide["steps"] if step["id"] == "domain")
        assert domain["state"] == "NOT_ASSESSED"
        expected = "plan-fresh" if mode == "fresh" else "register-existing"
        assert domain["help_commands"] == [["cadence-mcp-bridge", "domain", expected, "--help"]]
        assert inventory(workspace) == before
    contracts = [
        "--profile",
        str(profile),
        "--design-registry",
        str(designs),
        "--pdk-registry",
        str(pdks),
    ]
    before = inventory(workspace)
    checked = cli(["operator-setup", "check", *contracts], "LOCAL_CONTRACTS_VALID")
    assert inventory(workspace) == before
    runtime = workspace / "operator-runtime.json"
    context_id = "installed-synthetic-context"
    export = [
        "operator-setup",
        "export-runtime",
        *contracts,
        "--resource-state-root",
        str(retained),
        "--context",
        context_id,
        "--runner-sha256",
        "b" * 64,
        "--authority-ref",
        "synthetic-not-authorized",
        "--ledger-ref",
        "retained-synthetic-ledger",
        "--journal",
        str(analysis),
        "--sweep-journal",
        str(sweep),
        "--output",
        str(runtime),
    ]
    exported = cli(export, "LOCAL_RUNTIME_EXPORTED")
    assert exported["runtime_sha256"] == digest(runtime)
    document = json.loads(runtime.read_bytes())
    binding = document["contexts"][0]
    for field, path, key in (
        ("environment", profile, "environment_profile"),
        ("design", designs, "design_registry"),
        ("pdk", pdks, "pdk_registry"),
    ):
        assert binding[key] == str(path.resolve())
        assert binding[field + "_sha256"] == checked["contract_sha256"][field] == digest(path)
    assert binding["analysis_journal"] == str(analysis.resolve())
    assert binding["sweep_journal"] == str(sweep.resolve())
    assert binding["native_provider_binding"] is None and binding["operator_grant"] is None
    context = ["--settings", str(runtime), "--context", context_id]
    before = inventory(workspace)
    verified = cli(["operator-setup", "check", *context], "LOCAL_CONTEXT_VALID")
    assert (
        verified["native_bindings_authenticated"] is False and verified["ledger_assessed"] is False
    )
    assert inventory(workspace) == before
    features = cli(["operator-features", *context], "LOCAL_FEATURE_GUIDANCE")
    assert features["context_id"] == context_id
    assert features["mode"] == "operator" and features["native_tools_registered"] is None
    assert features["remaining_budget"] is None
    assert all(
        a["state"] == "BLOCKED" for c in features["circuits"] for a in c["analyses"]
    )
    assert str(workspace) not in json.dumps(features)
    assert inventory(workspace) == before
    for format, name in (("codex", "client.toml"), ("mcp-json", "client.json")):
        output = workspace / name
        arguments = [
            "operator-setup",
            "export-client",
            *context,
            "--format",
            format,
            "--output",
            str(output),
        ]
        client = cli(arguments, "exported_local_only")
        assert client["client_config_sha256"] == digest(output)
        configuration = (
            tomllib.loads(output.read_text(encoding="utf-8"))
            if format == "codex"
            else json.loads(output.read_bytes())
        )
        server = configuration["mcp_servers" if format == "codex" else "mcpServers"][
            "cadence-mcp-bridge"
        ]
        assert Path(server["command"]).resolve() == Path(sys.executable).resolve()
        assert server["args"] == ["-m", "cadence_mcp_bridge", "serve-operator"]
        assert server["env"]["CADENCE_MCP_RUNTIME_SETTINGS_PATH"] == str(runtime.resolve())
        assert server["env"]["CADENCE_MCP_RUNTIME_CONTEXT_ID"] == context_id
        assert server["env"]["CADENCE_MCP_RUNTIME_MODE"] == "operator"
        assert "untrusted-inherited-alias" not in json.dumps(configuration)
        assert "/untrusted/inherited/root" not in json.dumps(configuration)
        before = inventory(workspace)
        cli(arguments, "BLOCKED", rejected="setup_output_exists")
        assert inventory(workspace) == before
    before = inventory(workspace)
    cli(export, "BLOCKED", rejected="setup_output_exists")
    assert inventory(workspace) == before
    fresh_journals = (retained / "new-analysis.sqlite3", retained / "new-sweep.sqlite3")
    fresh_runtime = workspace / "fresh-local-runtime.json"
    fresh_export = export.copy()
    for option, path in (
        ("--journal", fresh_journals[0]),
        ("--sweep-journal", fresh_journals[1]),
        ("--output", fresh_runtime),
    ):
        fresh_export[fresh_export.index(option) + 1] = str(path)
    cli(fresh_export, "LOCAL_RUNTIME_EXPORTED")
    fresh_context = ["--settings", str(fresh_runtime), "--context", context_id]
    cli(["operator-setup", "check", *fresh_context], "LOCAL_CONTEXT_VALID")
    cli(
        [
            "operator-setup",
            "export-client",
            *fresh_context,
            "--format",
            "mcp-json",
            "--output",
            str(workspace / "fresh-client.json"),
        ],
        "exported_local_only",
    )
    assert all(not path.exists() for path in fresh_journals)
    stale_profile = workspace / "changed-environment.json"
    stale_profile.write_bytes(profile.read_bytes() + b"\n")
    stale_document = json.loads(runtime.read_bytes())
    stale_document["contexts"][0]["environment_profile"] = str(stale_profile)
    stale_runtime = workspace / "stale-runtime.json"
    stale_runtime.write_text(json.dumps(stale_document), encoding="utf-8")
    before = inventory(workspace)
    cli(
        ["operator-setup", "check", "--settings", str(stale_runtime), "--context", context_id],
        "BLOCKED",
        rejected="stale_contract_digest",
    )
    assert inventory(workspace) == before
    assert all(digest(workspace / name) == value for name, value in protected.items())
    assert set(path.name for path in retained.iterdir()) == {analysis.name, sweep.name, ledger.name}
    assert not list(workspace.rglob("*.lock"))
    report: dict[str, object] = {
        "status": "PASS",
        "evidence": "INSTALLED_PACKAGE_LOCAL_SETUP_SYNTHETIC",
        "package_version": cadence_mcp_bridge.__version__,
        "installed_origin_verified": True,
        "cli_invocations": len(invocations),
        "client_formats": ["codex", "mcp-json"],
        "preserved_files": len(protected),
        "fresh_existing_guides": True,
        "absent_journals_not_created": True,
        "exclusive_outputs_verified": True,
        "stale_binding_rejected": True,
        "fixture_authority": "UNQUALIFIED_ZERO_BUDGET",
        "remote_contact": False,
        "execution_authorized": False,
        "new_simulations": 0,
        "new_reservations": 0,
        "exported_clients_started": False,
    }
    (workspace / "verification-receipt.json").write_text(
        json.dumps(
            {
                "report": report,
                "invocations": invocations,
                "preserved_sha256": protected,
                "final_files_sha256": inventory(workspace),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.workspace.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
