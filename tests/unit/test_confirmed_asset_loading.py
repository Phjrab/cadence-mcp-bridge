"""Held-byte authority helper regressions; synthetic, no VM or real consent."""

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
