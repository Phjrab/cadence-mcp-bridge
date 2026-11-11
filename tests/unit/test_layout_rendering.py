"""Closed generated SKILL checks. No actual VM/API qualification is implied."""

import re
from decimal import localcontext

import pytest
from test_layout_models import fixture_request, fixture_snapshot

from cadence_mcp_bridge import _layout_rendering as rendering
from cadence_mcp_bridge.layout_engine import build_plan


def commands():
    snapshot = fixture_snapshot()
    request = fixture_request(snapshot)
    edits = tuple(
        e.model_copy(update={"label": None}) if e.kind == "add_pin" else e for e in request.edits
    )
    plan = build_plan(snapshot, request.model_copy(update={"edits": edits}))
    return snapshot.technology.model_dump(mode="json"), [
        c.model_dump(mode="json") for c in plan.normalized_edits
    ]


def test_exact_dbu_to_skill_with_small_decimal_context():
    with localcontext() as ctx:
        ctx.prec = 2
        assert rendering.coordinate(123456789, 1000) == "123456.789"
        assert rendering.coordinate(-5, 1000) == "-0.005"


@pytest.mark.parametrize("name", ['x") exit() ;', "metal1\nexit()", "../layout", "x|y", ""])
def test_name_injection_and_paths_reject(name):
    with pytest.raises(ValueError):
        rendering.inspect_script({"library": name, "cell": "Seed", "view": "layout"})


@pytest.mark.parametrize(
    "is_param_cell,super_master,expected_submaster",
    [(False, None, False), (True, None, False), (False, "observed-supermaster", True)],
    ids=["ordinary-master", "source-supermaster", "evaluated-submaster"],
)
def test_collector_projects_submaster_relationship(is_param_cell, super_master, expected_submaster):
    # Check the emitted attribute against observed native master categories;
    # this bounded projection is not a SKILL runtime or native qualification.
    script = rendering.inspect_script(
        {"library": "Observed", "cell": "Pair", "view": "layout"}
    ).decode("ascii")
    attributes = re.findall(r'if\(inst~>master~>([A-Za-z]+) then "1" else "0"\)', script)
    assert len(attributes) == 1
    observed_master = {"isParamCell": is_param_cell, "superMaster": super_master}
    assert bool(observed_master[attributes[0]]) is expected_submaster


def test_generated_operations_save_close_reopen_and_no_overwrite():
    technology, edits = commands()
    target = {"library": "Owned", "cell": "Revision2", "view": "layout"}
    source = dict(target, cell="Revision1")
    selectors = {"inst-one": {"kind": "instance", "name": "I0"}}
    script = rendering.write_script(source, target, selectors, technology).decode()
    assert 'dbCopyCellView(src "Owned" "Revision2" "layout" nil nil nil)' in script
    assert script.index("destination_already_exists") < script.index("dbCopyCellView")
    apply = rendering.apply_script(target, selectors, technology, edits).decode()
    assert "dbMoveFig" in apply and "dbCreateRect" in apply and "dbCreatePin" in apply
    assert "dbMoveFig(car(matches) nil" in apply
    assert apply.index("dbSave(cv)") < apply.index("dbClose(cv)")
    assert apply.rindex('"maskLayout" "r"') > apply.index("dbSave(cv)")
    assert "MCP_LAYOUT_SAVED_REOPENED|1" in apply
    assert "spectre" not in apply.lower()
    with pytest.raises(ValueError, match="distinct_cellview"):
        rendering.write_script(source, source, selectors, technology)


def test_unsupported_label_layer_grid_and_boolean_fail_before_render():
    technology, edits = commands()
    edits[-1]["pin"]["label"] = "OUT"
    with pytest.raises(ValueError, match="label_not_supported"):
        rendering.edits_script(edits, technology)
    edits[-1]["pin"]["label"] = None
    edits[1]["shape"]["layer"] = "guessedLayer"
    with pytest.raises(ValueError, match="layer_purpose"):
        rendering.edits_script(edits, technology)
    edits[1]["shape"]["layer"] = "metal1"
    edits[0]["dx_dbu"] = 1
    with pytest.raises(ValueError, match="off_grid"):
        rendering.edits_script(edits, technology)
    edits[0]["dx_dbu"] = True
    with pytest.raises(ValueError, match="integer_dbu"):
        rendering.edits_script(edits, technology)


def test_terminal_preflight_precedes_any_database_mutation():
    technology, edits = commands()
    target = {"library": "Owned", "cell": "Revision2", "view": "layout"}
    script = rendering.apply_script(target, {}, technology, edits).decode()
    assert script.index("terminal_already_exists") < script.index("dbCreateRect")
    assert script.index("terminal_already_exists") < script.index("dbMoveFig")
    with pytest.raises(ValueError, match="duplicate_terminal"):
        rendering.apply_script(target, {}, technology, edits + [edits[-1]])


def test_probe_and_seed_are_fixed_bounded_scripts_without_object_handle_output():
    technology, unused = commands()
    view = {"library": "ObservedTech", "cell": "Seed", "view": "layout"}
    probe = rendering.probe_script(["ObservedTech"], [view]).decode()
    assert 'then "1" else "0"' in probe and "=dbCreate" not in probe
    seed = rendering.seed_script(
        "Owned",
        "/managed/Owned",
        "ObservedTech",
        "RectMaster",
        "Seed",
        technology,
        technology["allowed_layer_purposes"][0],
    ).decode()
    assert seed.index("seed_library_already_exists") < seed.index("ddCreateLib")
    assert seed.index("seed_technology_observation_changed") < seed.index("dbCreateRect")
    assert "dbCreateInst" in seed and "MCP_LAYOUT_SAVED_REOPENED|1" in seed
    assert 'techGetDBUPerUU(tf "maskLayout")' in probe
    assert 'techGetLP(tf list(car(layer) "drawing"))' in probe
    assert 'techGetDBUPerUU(tf "maskLayout")' in seed
    assert 'techGetLP(tf list("metal1" "drawing"))' in seed
    assert seed.rindex('"maskLayout" "r"') > seed.index("dbSave(cv)")
    with pytest.raises(ValueError, match="scope_bound"):
        rendering.probe_script(["ObservedTech"] * 9, [])
    with pytest.raises(ValueError, match="observed_lpp"):
        rendering.seed_script(
            "Owned",
            "/managed/Owned",
            "ObservedTech",
            "RectMaster",
            "Seed",
            technology,
            {"layer": "guessed", "purpose": "drawing"},
        )


def test_runtime_program_catches_skill_errors_before_clean_exit():
    view = {"library": "Owned", "cell": "Seed", "view": "layout"}
    wrapped = rendering.execution_script(rendering.inspect_script(view)).decode()
    assert wrapped.index("procedure(mcpLayoutCollect") < wrapped.index("procedure(mcpLayoutRun")
    assert "errset(mcpLayoutRun() t)" in wrapped
    assert 'then exit(0) else mcpLayoutFail("skill_evaluation_failed")' in wrapped
    assert wrapped.count("exit()") == 0
    assert wrapped.index("dbClose(cv)") < wrapped.index("errset(mcpLayoutRun() t)")
    with pytest.raises(ValueError, match="fixed_program_shape"):
        rendering.execution_script(b"exit()\n")
