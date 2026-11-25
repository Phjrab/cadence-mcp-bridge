import hashlib
import io
import re
from pathlib import Path

import pytest

from cadence_mcp_bridge import _mos_cdf_call_contract as callback
from cadence_mcp_bridge import _registered_mos_edit_phase as guest


def _row(value, units=None):
    return dict(
        oa_type="string", oa_value=value, cdf_type="instData", cdf_units=units, cdf_value=value
    )


def _before():
    return {
        "w": _row("120n", "lengthMetric"),
        "fw": _row("120n", "lengthMetric"),
        "l": _row("100n", "lengthMetric"),
        "m": _row("1"),
        "fingers": _row("1"),
        "as": _row("69.6f"),
        "ad": _row("69.6f"),
        "ps": _row("1.16u", "lengthMetric"),
        "pd": _row("1.16u", "lengthMetric"),
        "nf": dict.fromkeys(("oa_type", "oa_value", "cdf_type", "cdf_units", "cdf_value")),
        "model": _row("gpdk090_nmos1v"),
        "dfm": _row("Minimum"),
    }


def test_native_sizing_checks_actual_new_length_and_fixed_properties():
    before = _before()
    expected = {"w": {"value": "120", "unit": "nm"}, "l": {"value": "250", "unit": "nm"}}
    observed = dict(before, l=_row("0.25u", "lengthMetric"))
    # Derived geometry is observed, and no anticipated after-tuple is loaded.
    observed["as"] = _row("72f")
    guest.sizing_readback(before, observed, expected)
    with pytest.raises(ValueError, match="sizing_dimension"):
        guest.sizing_readback(before, dict(observed, l=before["l"]), expected)
    with pytest.raises(ValueError, match="sizing_property_conservation"):
        guest.sizing_readback(before, dict(observed, m=_row("2")), expected)
    with pytest.raises(ValueError, match="sizing_geometry_persistence"):
        guest.sizing_readback(
            before, dict(observed, ad=dict(_row("72f"), oa_value="69.6f")), expected
        )


def test_callback_child_uses_fixed_digest_and_strict_frames(monkeypatch):
    raw = b"fixture()"
    pin = hashlib.sha256(raw).hexdigest().encode("ascii")
    monkeypatch.setattr(callback, "NMOS_LENGTH_CALLBACK_SHA256", pin)
    assert callback.check_length_callback(io.BytesIO(b"nmos1v|l|9\n" + raw + b"\nEND\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|w|9\n" + raw + b"\nEND\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|l|9\n" + raw + b"\nBAD\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|l|4097\n"))
    assert not callback.check_length_callback(io.BytesIO(b"nmos1v|l|9\nother()x!\nEND\n"))


def test_callback_child_uses_verified_phase_path_and_source_pin():
    work = "/home/buet/native-jobs/copy-1/edit/work"
    rendered = guest.render(guest.VERIFY_LENGTH_CALLBACK, {"@WORK@": work})
    assert b"@WORK@" not in rendered
    command = (
        b"/usr/bin/python -E -s -B " + work.encode("ascii") + b"/verify-nmos-length-callback.py"
    )
    assert command in rendered
    assert (
        hashlib.sha256(Path(callback.__file__).read_bytes()).hexdigest()
        == guest.SIZING_HASH_CHILD_SHA256
    )


def test_length_job_renders_complete_baseline_and_only_held_fields_afterward():
    job = guest.Source9MosJob.__new__(guest.Source9MosJob)
    job.sizing = (b"fixed adapter", b"fixed verifier")
    job.route = {"before": _before()}
    job.library = "CmosLongMosFixture"
    job.owned = "/home/buet/owned"
    job.source = "/home/buet/source"
    job.source_alias = guest.SOURCE
    job.operation = "00e78318-9c30-4064-9233-5d7d9827ff70"

    values = job.values("/home/buet/job/edit/work")
    before = set(re.findall(r'\("([a-z]+)"', values["@BEFORE@"]))
    after = set(re.findall(r'\("([a-z]+)"', values["@AFTER@"]))
    assert before == set(guest.PROPERTIES)
    assert after == before.difference(guest.SIZING_OVERRIDES)

    edit = guest.render(guest.COMMON + guest.EDIT, values)
    reopen = guest.render(guest.COMMON + guest.REOPEN, values)
    assert values["@BEFORE@"].encode("ascii") in edit
    assert values["@AFTER@"].encode("ascii") in edit
    assert values["@AFTER@"].encode("ascii") in reopen
    assert b"mcpMosApplyWL(inst)==t" in edit
    assert b"mcpMosApplyWL(" not in reopen
