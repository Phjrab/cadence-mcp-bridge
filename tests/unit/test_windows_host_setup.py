"""Host-only setup: disposable state, no VM calls, no claimed app qualification."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path
from unittest.mock import Mock

import pytest

from cadence_mcp_bridge import __main__ as cli
from cadence_mcp_bridge import onboarding
from cadence_mcp_bridge.windows_host import backend
from cadence_mcp_bridge.windows_host import configuration as cfg


@pytest.fixture
def layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    config = tmp_path / "코덱스 home" / "config.toml"
    config.parent.mkdir()
    history = tmp_path / "history"
    history.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(config.parent))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    return config, history


def entry(command: str = "C:/Users/운영자/Programs/version/CadenceMCPBridge.exe") -> dict:
    return {
        "command": command,
        "args": ["serve-operator"],
        "env": {"CADENCE_MCP_RUNTIME_MODE": "operator"},
    }


def test_add_preserves_comments_other_servers_and_provider(layout: tuple[Path, Path]) -> None:
    config, history = layout
    prefix = (
        '# 사용자 주석\nmodel = "user-model" # keep\n[model_providers.private]\nname = "mine"\n'
    )
    other = '[mcp_servers.other]\ncommand = "other.exe" # do not edit\n'
    config.write_text(prefix + other, encoding="utf-8")
    plan = cfg.preview(config, "cadence", entry())
    assert "user-model" not in plan["diff"] and "other.exe" not in plan["diff"]
    applied = cfg.apply(plan, history)
    text = config.read_text(encoding="utf-8")
    assert prefix in text and other in text
    assert tomllib.loads(text)["mcp_servers"]["cadence"] == entry()
    record = json.loads(Path(applied["receipt"]).read_text())
    assert Path(record["backup"]).read_text(encoding="utf-8") == prefix + other
    assert applied["actual_app_verified"] is False


def test_repeat_does_not_duplicate_or_write(layout: tuple[Path, Path]) -> None:
    config, history = layout
    cfg.apply(cfg.preview(config, "cadence", entry()), history)
    previous = config.stat().st_mtime_ns
    files = list(history.iterdir())
    assert cfg.apply(cfg.preview(config, "cadence", entry()), history)["changed"] is False
    assert config.stat().st_mtime_ns == previous and list(history.iterdir()) == files


def test_conflict_requires_choice_and_cancel_is_noop(layout: tuple[Path, Path]) -> None:
    config, history = layout
    cfg.apply(cfg.preview(config, "cadence", entry()), history)
    before = config.read_bytes()
    with pytest.raises(cfg.SetupRejected, match="name_conflict"):
        cfg.preview(config, "cadence", entry("other.exe"))
    assert config.read_bytes() == before
    cfg.preview(config, "cadence-other", entry("other.exe"))
    assert config.read_bytes() == before


def test_update_and_remove_only_selected_entry(layout: tuple[Path, Path]) -> None:
    config, history = layout
    cfg.apply(cfg.preview(config, "cadence", entry("old.exe")), history)
    result = cfg.apply(cfg.preview(config, "cadence", entry("new.exe"), replace=True), history)
    with config.open("a", encoding="utf-8") as stream:
        stream.write('\n[mcp_servers.later]\ncommand = "later.exe" # subsequent user edit\n')
    cfg.remove_managed(Path(result["receipt"]), history)
    parsed = tomllib.loads(config.read_text())
    assert parsed["mcp_servers"]["cadence"]["command"] == "old.exe"
    assert parsed["mcp_servers"]["later"]["command"] == "later.exe"
    assert "# subsequent user edit" in config.read_text()


def test_modified_managed_entry_is_preserved(layout: tuple[Path, Path]) -> None:
    config, history = layout
    result = cfg.apply(cfg.preview(config, "cadence", entry()), history)
    config.write_text(config.read_text().replace("serve-operator", "user-modified"))
    before = config.read_bytes()
    with pytest.raises(cfg.SetupRejected, match="managed_entry_changed"):
        cfg.remove_managed(Path(result["receipt"]), history)
    assert config.read_bytes() == before


def test_change_between_preview_and_apply_is_not_overwritten(layout: tuple[Path, Path]) -> None:
    config, history = layout
    plan = cfg.preview(config, "cadence", entry())
    config.write_text('# concurrent app change\nmodel = "new"\n')
    with pytest.raises(cfg.SetupRejected, match="configuration_changed"):
        cfg.apply(plan, history)
    assert "concurrent app change" in config.read_text()


def test_last_read_recheck_detects_change(layout: tuple[Path, Path], monkeypatch) -> None:
    config, history = layout
    real_snapshot = cfg.snapshot
    plan = cfg.preview(config, "cadence", entry())
    calls = 0

    def race(path: Path):
        nonlocal calls
        calls += 1
        if calls == 4:
            config.write_text('# late concurrent edit\nmodel = "late"\n')
        return real_snapshot(path)

    monkeypatch.setattr(cfg, "snapshot", race)
    with pytest.raises(cfg.SetupRejected, match="configuration_changed"):
        cfg.apply(plan, history)
    assert "late concurrent edit" in config.read_text()
    assert list(history.glob("*.before"))


def test_disk_full_preserves_original(layout: tuple[Path, Path], monkeypatch) -> None:
    config, history = layout
    config.write_text('model = "original"\n')
    plan = cfg.preview(config, "cadence", entry())
    monkeypatch.setattr(cfg.tempfile, "mkstemp", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        cfg.apply(plan, history)
    assert config.read_text() == 'model = "original"\n'
    assert list(history.glob("*.json"))  # Durable pre-change intent, not a success claim.


def test_replace_failure_preserves_recoverable_intent(layout: tuple[Path, Path], monkeypatch):
    config, history = layout
    plan = cfg.preview(config, "cadence", entry())
    monkeypatch.setattr(cfg.os, "replace", Mock(side_effect=PermissionError("file in use")))
    with pytest.raises(PermissionError):
        cfg.apply(plan, history)
    assert not config.exists()
    assert len(list(history.glob("*.json"))) == 1


@pytest.mark.parametrize("raw", [b"not TOML !", b'[[mcp_servers]]\ncommand="bad"'])
def test_invalid_toml_fails_before_write(layout, raw):
    config, history = layout
    config.write_bytes(raw)
    with pytest.raises((ValueError, TypeError)):
        cfg.preview(config, "cadence", entry())
    assert config.read_bytes() == raw and not list(history.iterdir())


def test_bom_and_unicode_preserved(layout):
    config, history = layout
    config.write_bytes(b"\xef\xbb\xbf" + '# 한글\nmodel="내 모델"\n'.encode())
    cfg.apply(cfg.preview(config, "cadence", entry()), history)
    assert config.read_bytes().startswith(b"\xef\xbb\xbf")
    assert tomllib.loads(config.read_text(encoding="utf-8-sig"))["model"] == "내 모델"


def test_codex_home_and_project_override_detection(layout, tmp_path):
    config, _ = layout
    project = tmp_path / "repo"
    (project / ".codex").mkdir(parents=True)
    (project / ".codex/config.toml").write_text("# project override")
    assert cfg.codex_config() == config
    plan = cfg.preview(config, "cadence", entry(), project=project)
    assert str(project / ".codex/config.toml") in plan["project_overrides"]
    assert not plan["client_connection_verified"]


def test_relative_codex_home_rejected(monkeypatch):
    monkeypatch.setenv("CODEX_HOME", "relative")
    with pytest.raises(cfg.SetupRejected, match="absolute"):
        cfg.codex_config()


def test_hardlink_config_rejected(layout, tmp_path):
    config, _ = layout
    config.write_text("# original")
    os.link(config, tmp_path / "another.toml")
    with pytest.raises(cfg.SetupRejected, match="ordinary_file"):
        cfg.preview(config, "cadence", entry())


@pytest.mark.parametrize("action", ["status", "guide", "save-connection"])
def test_default_setup_never_contacts_developer_vm(layout, monkeypatch, tmp_path, action):
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=AssertionError("no remote")))
    monkeypatch.setattr(subprocess, "Popen", Mock(side_effect=AssertionError("no remote")))
    request = {
        "action": action,
        "mode": "fresh",
        "alias": "my-vm",
        "host": "vm.example.invalid",
        "user": "student",
        "identity": "",
    }
    result = backend.dispatch(request, root=tmp_path / "user-data")
    assert result["remote_contact"] is False
    assert result["new_simulations"] == result["new_reservations"] == 0
    assert "buet" not in json.dumps(result)


def test_connection_requires_explicit_consent_and_existing_ssh(layout, monkeypatch, tmp_path):
    request = {
        "action": "connect",
        "alias": "mine",
        "host": "vm.example.invalid",
        "user": "student",
    }
    with pytest.raises(cfg.SetupRejected, match="consent"):
        backend.dispatch(request)
    monkeypatch.setattr(backend, "ssh_executable", lambda: None)
    with pytest.raises(cfg.SetupRejected, match="openssh_client_missing"):
        backend.dispatch({**request, "consent": True})


@pytest.mark.parametrize(
    "field,value",
    [("host", "host;touch x"), ("alias", "-oProxyCommand=x"), ("user", "root\nsecret")],
)
def test_connection_rejects_shell_and_option_injection(field, value):
    request = {"alias": "mine", "host": "vm.invalid", "user": "student", field: value}
    with pytest.raises(cfg.SetupRejected):
        backend.connection_draft(request)


def test_import_reuses_runtime_paths_and_never_creates_journals(layout, tmp_path, capsys):
    starter = tmp_path / "등록 입력"
    onboarding.export_starter(starter)
    args = [
        "operator-setup",
        "export-runtime",
        "--profile",
        str(starter / "environment.json"),
        "--design-registry",
        str(starter / "designs.json"),
        "--pdk-registry",
        str(starter / "pdks.json"),
        "--resource-state-root",
        str(starter),
        "--context",
        "my-context",
        "--runner-sha256",
        "b" * 64,
        "--authority-ref",
        "retained-authority",
        "--ledger-ref",
        "retained-ledger",
        "--journal",
        str(starter / "analysis.sqlite3"),
        "--sweep-journal",
        str(starter / "sweep.sqlite3"),
        "--output",
        str(starter / "runtime.json"),
    ]
    assert cli.main(args) == 0
    capsys.readouterr()
    before = {str(p): p.read_bytes() for p in starter.iterdir() if p.is_file()}
    report = backend.runtime_import(tmp_path / "user-data", starter / "runtime.json", "my-context")
    assert report["status"] == "LOCAL_CONTEXT_VALID"
    assert not report["journal_created"] and report["execution_status"] == "NOT_ASSESSED"
    assert before == {str(p): p.read_bytes() for p in starter.iterdir() if p.is_file()}
    launcher = tmp_path / "installed" / "CadenceMCPBridge.exe"
    launcher.parent.mkdir()
    launcher.write_bytes(b"synthetic launcher; never executed")
    (launcher.parent / "INSTALLATION.json").write_text(
        '{"version":"2.2.0a1","kind":"per-user"}', encoding="utf-8"
    )
    state = tmp_path / "user-data"
    plan = backend.dispatch(
        {
            "action": "preview",
            "settings": str(starter / "runtime.json"),
            "context": "my-context",
            "name": "cadence-test",
        },
        root=state,
        launcher=launcher,
    )
    applied = backend.dispatch(
        {"action": "apply", "consent": True, "after": plan["after"]}, root=state, launcher=launcher
    )
    assert applied["status"] == "CLIENT_CONFIGURED"
    assert not applied["actual_app_verified"]


def test_no_unmanaged_removal(layout, tmp_path):
    with pytest.raises(cfg.SetupRejected, match="unmanaged_receipt"):
        backend.dispatch(
            {"action": "remove", "consent": True, "receipt": "elsewhere"}, root=tmp_path / "data"
        )
