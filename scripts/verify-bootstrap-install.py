"""Installed fixed bootstrap/content and operator-state preservation, synthetic only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("synthetic workspace link")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def preserve(workspace: Path) -> dict[str, object]:
    record = json.loads((workspace / "preservation.json").read_bytes())
    if snapshot(workspace / "state") != record["files"]:
        raise ValueError("operator state changed during reinstall/uninstall")
    return {
        "status": "PASS",
        "scope": "SYNTHETIC_OPERATOR_STATE",
        "preserved_files": len(record["files"]),
        "native_jobs": 0,
    }


def verify(workspace: Path, examples: Path) -> dict[str, object]:
    import cadence_mcp_bridge
    from cadence_mcp_bridge.analysis_store import AnalysisStore
    from cadence_mcp_bridge.sweeps import SweepStore

    if not Path(cadence_mcp_bridge.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise ValueError("verifier did not import installed wheel")
    workspace.mkdir(parents=False, exist_ok=False)
    state = workspace / "state"
    state.mkdir(mode=0o700)
    managed = state / "managed"
    managed.mkdir(mode=0o700)
    for name, data in (
        ("original-oa.synthetic", b"protected synthetic original"),
        ("ledger.synthetic.json", b'{"attempts":82,"reserved_bytes":9798942720}'),
        ("prior-replay.synthetic", b"retained prior replay"),
    ):
        (state / name).write_bytes(data)
    analysis_path = state / "analysis.sqlite3"
    identity = str(uuid4())
    analysis = AnalysisStore(analysis_path)
    assert analysis.admit(identity, "synthetic-design", "synthetic-dc", "a" * 64)
    assert not AnalysisStore(analysis_path).admit(
        identity, "synthetic-design", "synthetic-dc", "a" * 64
    )
    SweepStore(state / "sweep.sqlite3")
    before = snapshot(state)
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.upper().startswith("CADENCE_MCP_")
        and k.upper() not in ("PYTHONPATH", "PYTHONHOME")
    }

    def command(
        arguments: list[str], *, standalone: bool = False, accepted: bool = True
    ) -> dict[str, object]:
        prefix = [sys.executable, "-I", "-X", "utf8"]
        prefix += [str(workspace / "installer.py")] if standalone else ["-m", "cadence_mcp_bridge"]
        process = subprocess.run(
            [*prefix, *arguments], cwd=workspace, env=environment, capture_output=True, timeout=30
        )
        if (process.returncode == 0) != accepted:
            raise ValueError("unexpected fixed bootstrap outcome")
        if not accepted:
            return {}
        result = json.loads(process.stdout)
        if result.get("execution_authorized") is not False:
            raise ValueError("content workflow granted execution")
        return result

    command(["runner", "export-installer", "--output", str(workspace / "installer.py")])
    report = command(
        [
            "runner",
            "bundle",
            "--profile",
            str(examples / "environment.json"),
            "--output",
            str(workspace / "bundle"),
        ]
    )
    # Exported native lifecycle must reject the ordinary Windows staged tree.
    unbound = workspace / "unbound-managed"
    unbound.mkdir(mode=0o700)
    unbound_digest = str(report["manifest_sha256"])
    command([
        "runner", "install", "--bundle", str(workspace / "bundle"),
        "--target", str(unbound), "--expected-plan-sha256", unbound_digest,
    ])
    original = snapshot(unbound)
    command(["activate", str(unbound), unbound_digest], standalone=True, accepted=False)
    assert snapshot(unbound) == original and not (unbound / "bin").exists()

    def bind_synthetic_target(bundle: Path) -> str:
        # Explicitly synthetic hash-valid fixture, not an operator Linux profile.
        # Fixed installed runner/probe/launcher bytes remain untouched and unexecuted.
        profile_path = bundle / "profile.json"
        value = json.loads(profile_path.read_bytes())
        value["paths"]["managed_root"] = str(managed.resolve())
        profile_data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True).encode("ascii")
        profile_path.write_bytes(profile_data)
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        profile_hash = hashlib.sha256(profile_data).hexdigest()
        manifest["profile_sha256"] = profile_hash
        manifest["files"]["profile.json"] = {"sha256": profile_hash, "bytes": len(profile_data)}
        raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode("ascii")
        manifest_path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    digest = bind_synthetic_target(workspace / "bundle")
    args = ["--target", str(managed), "--expected-plan-sha256", digest]
    command(["runner", "install", "--bundle", str(workspace / "bundle"), *args])
    assert command(["runner", "install", "--bundle", str(workspace / "bundle"), *args])[
        "status"
    ] == ("EXISTING_EXACT_INSTALL")
    command(["runner", "verify", *args])
    command(["activate", str(managed), digest], standalone=True)
    active = (managed / "active-runner.json").read_bytes()
    # Stage a distinct content candidate; no active-pointer replacement is available.
    profile = workspace / "next-profile.json"
    next_profile = json.loads((examples / "environment.json").read_bytes())
    next_profile["environment_id"] = "synthetic-next-environment"
    profile.write_text(json.dumps(next_profile), encoding="utf-8")
    next_report = command(
        ["runner", "bundle", "--profile", str(profile), "--output", str(workspace / "next-bundle")]
    )
    assert next_report["execution_authorized"] is False
    candidate = bind_synthetic_target(workspace / "next-bundle")
    # A distinct candidate is simulated by differing profile identity.
    assert candidate != digest
    command(
        [
            "runner",
            "install",
            "--bundle",
            str(workspace / "next-bundle"),
            "--target",
            str(managed),
            "--expected-plan-sha256",
            candidate,
        ]
    )
    command(["activate", str(managed), candidate], standalone=True, accepted=False)
    assert (managed / "active-runner.json").read_bytes() == active
    # Incomplete candidates and active/unresolved markers are never overwritten.
    partial = managed / "runtime" / ("f" * 64)
    partial.mkdir()
    (partial / "runner.py").write_bytes(b"preserved partial installation")
    command(["verify", str(managed), "f" * 64], standalone=True, accepted=False)
    assert (partial / "runner.py").read_bytes() == b"preserved partial installation"
    command(["deactivate", str(managed), digest], standalone=True)
    assert (managed / "active-runner.json").read_bytes() == active
    assert (managed / "runner-revoked.json").exists()
    assert all(snapshot(state).get(name) == value for name, value in before.items())
    AnalysisStore(analysis_path).require(identity, "synthetic-design", "synthetic-dc", "a" * 64)
    (workspace / "preservation.json").write_text(
        json.dumps({"files": snapshot(state)}, sort_keys=True), encoding="utf-8"
    )
    return {
        "status": "PASS",
        "evidence": "INSTALLED_FIXED_BOOTSTRAP_SYNTHETIC",
        "content_install_repeat_verify": True,
        "activation_deactivation": True,
        "unbound_staged_activation_denied": True,
        "positive_lifecycle_fixture": "HASH_VALID_SYNTHETIC_TARGET_NOT_NATIVE_PROFILE",
        "staged_candidate_preserves_active_pointer": True,
        "semantic_version_upgrade": "NOT_TESTED",
        "live_migration": "UNSUPPORTED",
        "journal_replay_preserved": True,
        "remote_contact": False,
        "new_simulations": 0,
        "execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--examples", type=Path)
    parser.add_argument("--verify-preserved", action="store_true")
    arguments = parser.parse_args()
    if arguments.verify_preserved:
        result = preserve(arguments.workspace.resolve())
    else:
        if arguments.examples is None:
            parser.error("--examples is required for installed verification")
        result = verify(arguments.workspace.resolve(), arguments.examples.resolve())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
