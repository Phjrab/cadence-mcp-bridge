"""Exact metadata payload/framing bounds using only in-memory synthetic state."""

from __future__ import annotations

import base64
import inspect
import json
import os
import sys
from pathlib import Path

import pytest

from cadence_mcp_bridge import _physical_metadata as native
from cadence_mcp_bridge import physical_metadata as host
from cadence_mcp_bridge.operator_transport import run_fixed


def synthetic_bootstrap(padding: int) -> tuple[str, bytes]:
    # Keep the actual collector run(), JSON serializer and bound. Only its OS,
    # setup/accounting and observations use a disposable in-memory filesystem.
    setup_source = b'''
import json, types
files = {}
directories = set()
counter = {"campaign_id":"synthetic","count":1,"result_reserved_bytes":0}
def inventory(assets, expected, known):
    files.clear()
    directories.clear()
    files.update(("/owned/runtime/"+expected+"/"+name, raw) for name,raw in assets.items())
    active = json.dumps({"manifest_sha256":expected}).encode("ascii")
    files["/owned/active-native-provider.json"] = active
    files["/owned/ledger.json"] = b"{}"
    return ({"profile_sha256":"a"*64}, {}, {"identity_manifest_sha256":"b"*64,"pdk_sha256":"c"*64})
def read(path):
    return files[path]
def private(*args):
    pass
def metadata(path):
    return {}
def directory(path, accounting):
    directories.add(path)
def closed(raw):
    return json.loads(raw)
def listdir(path):
    prefix = path+"/"
    names = (name[len(prefix):] for name in files if name.startswith(prefix))
    return sorted(name for name in names if "/" not in name)
def mkdir(path, mode):
    if path in directories:
        raise FileExistsError(path)
    directories.add(path)
def exclusive(path, raw):
    if path in files:
        raise FileExistsError(path)
    files[path] = raw
class Session:
    def __init__(self, root):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def observe(self, binding):
        return dict(counter), []
    def check(self):
        pass
def modules(assets):
    return (
        types.SimpleNamespace(
            ReservationSession=Session,LEDGER="ledger.json",sync_directory=lambda *a:None),
        types.SimpleNamespace(exclusive=exclusive),
        types.SimpleNamespace(validate_profile=lambda *a:None),
        types.SimpleNamespace(domain=lambda *a:("/owned",{},"synthetic",500)),
    )
'''
    collector_source = Path(inspect.getfile(native)).read_bytes() + (
        "\nimport types\n"
        "_actual_run=run\n"
        "def run(request, setup, assets, known, collector_source):\n"
        " global os,time,INITIAL_COLLECTOR_SHA256\n"
        " os=types.SimpleNamespace(name='posix',getuid=lambda:500,"
        "listdir=setup.listdir,mkdir=setup.mkdir)\n"
        " time=types.SimpleNamespace(time=lambda:1.0)\n"
        " INITIAL_COLLECTOR_SHA256=digest(collector_source)\n"
        " destination='/owned/physical-metadata-v1/'+digest(collector_source)\n"
        " try:\n"
        "  result=_actual_run(request,setup,assets,known,collector_source)\n"
        " except ValueError:\n"
        "  assert destination+'/collector.py' in setup.files\n"
        "  assert destination+'/request.json' in setup.files\n"
        "  assert destination+'/receipt.json' not in setup.files\n"
        "  raise\n"
        " assert setup.files[destination+'/receipt.json']==canonical(result)\n"
        " return result\n"
        "def enumerate_targets(profile,registration):\n"
        " return ['/synthetic'],['/synthetic/tool'],{}\n"
        "def observe(path,roots):\n"
        f" return {{'padding':'x'*{padding}}}\n"
        "def same_listings(listings):\n"
        " pass\n"
    ).encode("ascii")
    request = {
        "schema_version": 1,
        "operation": "physical-metadata-once-v1",
        "manifest_sha256": "d" * 64,
        "files": {"profile.json": base64.b64encode(b"{}").decode("ascii")},
    }
    envelope = native.canonical(
        {
            "request": request,
            "setup": base64.b64encode(setup_source).decode("ascii"),
            "collector": base64.b64encode(collector_source).decode("ascii"),
        }
    )
    bootstrap = host._bootstrap(
        {
            "request_sha256": native.digest(envelope),
            "setup_sha256": native.digest(setup_source),
            "collector_sha256": native.digest(collector_source),
            "known_native_sources": {},
        }
    )
    # The production target is POSIX. Emulate only its alarm and LF text mode in
    # this owned Windows child; no OS account, filesystem or runtime is changed.
    prelude = (
        "import sys,signal\n"
        "if not hasattr(signal,'alarm'): signal.alarm=lambda seconds:None\n"
        "sys.stdout.reconfigure(newline='\\n')\n"
    )
    return prelude + bootstrap, envelope


@pytest.fixture(scope="module")
def empty_observation_bytes() -> int:
    program, request = synthetic_bootstrap(0)
    code, stdout, stderr = run_fixed(
        [sys.executable, "-I", "-c", program],
        request,
        dict(os.environ),
        limit=native.LIMIT,
    )
    assert code == 0 and not stderr
    return len(native.canonical(json.loads(stdout)))


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_actual_collector_bootstrap_and_transport_share_exact_payload_bound(
    empty_observation_bytes: int, delta: int
) -> None:
    size = native.LIMIT + delta
    program, request = synthetic_bootstrap(size - empty_observation_bytes)
    code, stdout, stderr = run_fixed(
        [sys.executable, "-I", "-c", program],
        request,
        dict(os.environ),
        limit=native.LIMIT,
    )
    if delta > 0:
        assert code != 0 and b"physical_output_bound" in stderr
        assert stdout == b""
    else:
        assert code == 0 and not stderr
        assert len(stdout) == size
        assert stdout == native.canonical(json.loads(stdout))
        assert json.loads(stdout)["candidate_file_contents_read"] is False


def test_fixed_transport_still_rejects_one_byte_over_metadata_ceiling() -> None:
    with pytest.raises(ValueError, match="fixed_transport_output_limit"):
        run_fixed(
            [sys.executable, "-I", "-c", "import sys;sys.stdout.buffer.write(b'x'*1048577)"],
            b"",
            dict(os.environ),
            limit=native.LIMIT,
        )
