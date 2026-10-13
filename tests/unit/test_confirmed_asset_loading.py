"""Held-byte authority helper regressions; synthetic, no VM or real consent."""

import subprocess
import sys
from importlib.resources import files
from types import SimpleNamespace

import pytest

from cadence_mcp_bridge import _native_dispatch as dispatch
from cadence_mcp_bridge import _native_setup as setup
from cadence_mcp_bridge import _operator_confirmation as confirmation

NAMES = ("reservations", "installer", "probe", "confirmation")


def test_unverified_standalone_authority_helpers_reject_cached_names(monkeypatch):
    monkeypatch.setattr(confirmation, "__package__", None)
    monkeypatch.setattr(confirmation, "_VERIFIED_HELPERS", None)
    for name in NAMES:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(marker="poisoned"))
    with pytest.raises(ValueError, match="confirmation_verified_helpers_required"):
        confirmation.helpers()


def test_confirmation_retains_verified_bytes_despite_cache_and_path_replacement(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(sys, "path", list(sys.path))
    directory = str(tmp_path.resolve())
    assets = {name + ".py": ("marker = " + repr(name) + "\n").encode("ascii")
              for name in NAMES}
    manifest = confirmation.canonical(dict(
        schema_version=1, kind=confirmation.KIND,
        files={name: dict(sha256=confirmation.digest(raw), bytes=len(raw))
               for name, raw in assets.items()},
    ))
    documents = {directory + "/" + name: raw for name, raw in assets.items()}
    documents[directory + "/manifest.json"] = manifest
    reads = []
    monkeypatch.setattr(confirmation, "__file__", directory + "/confirmation.py")
    monkeypatch.setattr(confirmation, "__package__", None)
    monkeypatch.setattr(confirmation, "_VERIFIED_HELPERS", None)
    monkeypatch.setattr(confirmation, "private", lambda *_a, **_kw: None)
    monkeypatch.setattr(confirmation.os, "listdir", lambda _p: list(confirmation.MEMBERS)
                        + ["manifest.json"])
    monkeypatch.setattr(confirmation, "read_private",
                        lambda path: reads.append(path) or documents[path])
    for name in NAMES:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(marker="poisoned"))
    expected = confirmation.digest(manifest)
    assert confirmation.validate_assets(expected) == expected
    assert len(reads) == 5
    for name in NAMES:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(marker="substituted"))
    def forbidden(_path):
        raise AssertionError("authenticated executable path reopened")
    monkeypatch.setattr(confirmation, "read_private", forbidden)
    helpers = confirmation.helpers()
    assert [m.marker for m in helpers] == ["reservations", "installer", "probe"]
    assert all(m.__file__.startswith(directory + "/") for m in helpers)


@pytest.mark.parametrize("loader", ["setup", "dispatch"])
def test_native_loader_explicitly_binds_confirmation_to_same_verified_helpers(monkeypatch, loader):
    monkeypatch.setattr(sys, "path", list(sys.path))
    assets = {name + ".py": files("cadence_mcp_bridge").joinpath(source).read_bytes()
              for name, source in {
                  "reservations": "_shared_reservations.py",
                  "installer": "_runner_bootstrap.py",
                  "probe": "_environment_probe.py",
                  "confirmation": "_operator_confirmation.py",
              }.items()}
    for name in NAMES:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(marker="poisoned"))
    if loader == "setup":
        monkeypatch.setattr(setup, "__package__", None)
        accounting, installer, probe, confirmed = setup.modules(assets)
    else:
        loaded = dispatch.verified_modules("/fixed/native", assets, NAMES)
        accounting, installer, probe, confirmed = (loaded[name] for name in NAMES)
    assert confirmed.helpers() == (accounting, installer, probe)
    for name in NAMES:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(marker="substituted"))
    assert confirmed.helpers() == (accounting, installer, probe)


def test_failed_confirmation_validation_cannot_reuse_previous_helper_binding(monkeypatch):
    monkeypatch.setattr(confirmation, "__package__", None)
    monkeypatch.setattr(confirmation, "_VERIFIED_HELPERS", (object(), object(), object()))
    with pytest.raises(ValueError, match="confirmation_helper_digest"):
        confirmation.validate_assets("invalid-digest")
    with pytest.raises(ValueError, match="confirmation_verified_helpers_required"):
        confirmation.helpers()


@pytest.mark.parametrize("source", ["_native_dispatch.py", "_native_setup.py",
                                     "_operator_confirmation.py"])
@pytest.mark.parametrize("shadow", ["json", "hashlib", "stat", "os"])
def test_direct_fixed_entry_rejects_early_script_directory_shadow(tmp_path, source, shadow):
    marker = tmp_path / "unreviewed-import-marker"
    entry = tmp_path / "fixed-entry.py"
    entry.write_bytes(files("cadence_mcp_bridge").joinpath(source).read_bytes())
    (tmp_path / (shadow + ".py")).write_text(
        "open(" + ascii(str(marker)) + ", 'w').write('unreviewed module executed')\n",
        encoding="ascii",
    )
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", str(entry)], input=b"", capture_output=True,
        cwd=tmp_path, timeout=10,
    )
    assert result.returncode in (0, 65)
    assert not marker.exists()


@pytest.mark.parametrize("loader", ["dispatch", "confirmation", "setup"])
def test_verified_loader_excludes_bundle_and_cwd_transitive_modules(tmp_path, monkeypatch, loader):
    directory = str(tmp_path.resolve())
    marker = tmp_path / "transitive-import-marker"
    (tmp_path / "platform.py").write_text(
        "open(" + ascii(str(marker)) + ", 'w').write('unreviewed platform executed')\n",
        encoding="ascii",
    )
    monkeypatch.setattr(sys, "path", [directory, "", *sys.path])
    monkeypatch.delitem(sys.modules, "platform", raising=False)
    assets = {name + ".py": ("marker = " + repr(name) + "\n").encode("ascii")
              for name in NAMES}
    assets["probe.py"] += b"import platform\n"
    for name in NAMES:
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(marker="poisoned"))
    if loader == "dispatch":
        loaded = dispatch.verified_modules(directory, assets, NAMES)
        probe = loaded["probe"]
    elif loader == "setup":
        monkeypatch.setattr(setup, "__package__", None)
        monkeypatch.setattr(setup, "__file__", directory + "/setup.py")
        probe = setup.modules(assets)[2]
    else:
        manifest = confirmation.canonical(dict(
            schema_version=1, kind=confirmation.KIND,
            files={name: dict(sha256=confirmation.digest(raw), bytes=len(raw))
                   for name, raw in assets.items()},
        ))
        documents = {directory + "/" + name: raw for name, raw in assets.items()}
        documents[directory + "/manifest.json"] = manifest
        monkeypatch.setattr(confirmation, "__file__", directory + "/confirmation.py")
        monkeypatch.setattr(confirmation, "__package__", None)
        monkeypatch.setattr(confirmation, "_VERIFIED_HELPERS", None)
        monkeypatch.setattr(confirmation, "private", lambda *_a, **_kw: None)
        monkeypatch.setattr(confirmation.os, "listdir", lambda _p: list(confirmation.MEMBERS)
                            + ["manifest.json"])
        monkeypatch.setattr(confirmation, "read_private", lambda path: documents[path])
        confirmation.validate_assets(confirmation.digest(manifest))
        probe = confirmation.helpers()[2]
    assert not marker.exists()
    assert probe.platform.__file__ != str(tmp_path / "platform.py")
    assert directory not in sys.path and "" not in sys.path
