import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("case", ["valid", "malformed", "arguments"])
def test_fixed_diagnostic_with_fake_transport(monkeypatch, capsys, case):
    path = Path(__file__).resolve().parents[2] / "scripts/diagnose-wp14-preflight.py"
    spec = importlib.util.spec_from_file_location("diagnostic", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def fake(command, expiry):
        calls.append(command)
        assert "cadence-runner version" not in command
        assert "mkdir" not in command and "chmod" not in command
        if case == "malformed":
            return b"unexpected raw result"
        labels = [
            "HOST",
            "USER",
            "NO_CADENCE_PROCESS",
            "ROOT",
            "RUNNER_EXECUTABLE",
            "SNAPSHOT_ABSENT",
            *["PARENT_" + str(i) for i in range(6, 12)],
        ]
        return ("\n".join(label + "=PASS" for label in labels) + "\n").encode()

    loader = SimpleNamespace(exec_module=lambda m: setattr(m, "_invoke_bounded_ssh", fake))
    monkeypatch.setattr(
        module.importlib.util,
        "spec_from_file_location",
        lambda *args: SimpleNamespace(loader=loader),
    )
    monkeypatch.setattr(module.importlib.util, "module_from_spec", lambda spec: SimpleNamespace())
    monkeypatch.setattr(
        module.sys, "argv", ["diagnostic"] + (["bad"] if case == "arguments" else [])
    )
    result = module.main()
    assert result == {"valid": 0, "malformed": 1, "arguments": 2}[case]
    assert len(calls) == (0 if case == "arguments" else 1)
    assert "unexpected raw result" not in capsys.readouterr().out
