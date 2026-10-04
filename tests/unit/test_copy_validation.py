"""Synthetic records only; real topology and dimensions stay private."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import copy_validation as verify  # noqa: E402


def test_exact_oa_difference() -> None:
    base = ["I|Qx|fixture|device|symbol", 'P|Qx|w|string|"3u"', "T|Qx|D|n1"]
    changed = [base[0], 'P|Qx|w|string|"6u"', base[2]]
    plan = {"Qx": {"w": ("3u", "6u")}}
    assert verify.oa_records(base, changed, plan) == 1
    for bad in (changed + [changed[0]], [changed[0], changed[1], "T|Qx|D|n2"], base):
        with pytest.raises(ValueError):
            verify.oa_records(base, bad, plan)


@pytest.mark.parametrize("preimage", ["P|Qx|w|float|3", 'P|Qx|w|string|"4u"'])
def test_oa_preimage_drift(preimage: str) -> None:
    with pytest.raises(ValueError):
        verify.oa_records([preimage], ['P|Qx|w|string|"6u"'], {"Qx": {"w": ("3u", "6u")}})


def test_native_continuations_and_exact_fields() -> None:
    base = (
        "// private fixture\nQx (n1 g 0 0) fixture w=(3u) \\\n"
        " l=2u ad=1p\nRz (n1 0) resistor r=5k\n"
    )
    changed = base.replace("w=(3u)", "w=(6u)").replace("ad=1p", "ad=2p")
    plan = {"Qx": {"w": ("(3u)", "(6u)"), "ad": ("1p", "2p")}}
    assert verify.native_circuit(base, changed, plan) == 2
    for bad in (
        changed.replace("n1 g", "n2 g"),
        changed.replace("r=5k", "r=4k"),
        changed.replace("l=2u", "l=3u"),
        changed.replace("fixture w", "other w"),
    ):
        with pytest.raises(ValueError):
            verify.native_circuit(base, bad, plan)


def test_missing_duplicate_or_extra_native_edit_fails() -> None:
    base = "Qx (n1 g 0 0) fixture w=(3u) l=2u\n"
    plan = {"Qx": {"w": ("(3u)", "(6u)")}}
    for old, new in (
        (base + base, base + base),
        (base.replace("Qx", "Qy"), base),
        (base, base + "Qy (n1 g 0 0) fixture w=(3u) l=2u\n"),
    ):
        with pytest.raises(ValueError):
            verify.native_circuit(old, new, plan)
