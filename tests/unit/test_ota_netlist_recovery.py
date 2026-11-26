import pytest

from cadence_mcp_bridge.ota_netlist_recovery import _comparison_lines, _ModelEquivalence


def test_port_permutation_requires_the_matching_call_and_preserves_other_lines() -> None:
    model = _ModelEquivalence(
        alias="/fixture/libs.oa22/gpdk090/../../models/spectre/gpdk090.scs",
        canonical_path="/fixture/models/spectre/gpdk090.scs",
        section="NN",
        device=1,
        inode=2,
        file_bytes=100,
        file_sha256="a" * 64,
        registered_model_leaf_count=7,
        registered_model_leaf_list_sha256="b" * 64,
    )
    cell = "self_cascode_ota_17mos"
    include = f'include "{model.alias}" section=NN'
    header = f"subckt {cell} VDD VSS inn inp out"
    call = f"DUT (vdd 0 inn inp out) {cell}"
    device = "NM0 (drain inp Vx VSS) gpdk090_nmos1v"
    original = [include, header, device, f"ends {cell}", call]
    projected = _comparison_lines(original, model)
    assert projected == [
        f'include "{model.canonical_path}" section=NN',
        f"subckt {cell} VDD VSS inp inn out",
        device,
        f"ends {cell}",
        f"DUT (vdd 0 inp inn out) {cell}",
    ]
    assert original[1] == header and original[-1] == call
    for unmatched in (
        [include, projected[1], device, f"ends {cell}", call],
        [include, header, device, f"ends {cell}", projected[-1]],
        original + [call],
        [include.replace("NN", "FF"), *original[1:]],
    ):
        with pytest.raises(ValueError, match="paired port mapping"):
            _comparison_lines(unmatched, model)
