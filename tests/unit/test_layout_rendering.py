"""Closed generated SKILL checks. No actual VM/API qualification is implied."""

import re
from decimal import localcontext

import pytest
from test_layout_engine import _orient_snapshot
from test_layout_models import fixture_request, fixture_snapshot
from test_layout_worker import orientation_request

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


def test_registered_layer_policy_checks_technology_before_writes_and_on_reopen():
    technology, edits = commands()
    target = {"library": "Owned", "cell": "Revision2", "view": "layout"}
    policy = {"technology_library": "Tech", "layer_purposes": technology["allowed_layer_purposes"]}
    verify = 'mcpLayoutCheckLayerPolicy(cv "Tech" list('
    collect = 'mcpLayoutCollectPolicy(cv "Tech" list('
    inspect = rendering.inspect_script(target, policy).decode("ascii")
    assert "eq(tf techGetTechFile(lib))" in inspect and "techGetLP(tf lpp)" in inspect
    assert "if(library then" in inspect and "else\n      foreach(lp cv~>lpps" in inspect
    assert collect in inspect and "mcpLayoutCollect(cv)\ndbClose(cv)" not in inspect
    script = rendering.apply_script(target, {}, technology, edits, policy).decode("ascii")
    assert script.index(verify) < script.index("dbMoveFig") < script.index("dbSave(cv)")
    assert script.index(collect) > script.rindex('"maskLayout" "r"')
    source = dict(target, cell="Revision1")
    fork = rendering.write_script(source, target, {}, technology, policy=policy).decode("ascii")
    assert fork.index('mcpLayoutCheckLayerPolicy(src "Tech"') < fork.index("dbCopyCellView")
    assert fork.index(collect) > fork.rindex('"maskLayout" "r"')
    empty = rendering.inspect_script(target, dict(policy, layer_purposes=[]))
    assert b'mcpLayoutCollectPolicy(cv "Tech" nil)' in empty
    with pytest.raises(ValueError, match="layout_layer_purpose_not_registered"):
        rendering.apply_script(target, {}, technology, edits, dict(policy, layer_purposes=[]))


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


@pytest.mark.parametrize("target", ["R90", "MX", "MYR90"])
def test_orientation_absolute_assignment_and_save_reopen_preservation_guards(target):
    snapshot = _orient_snapshot()
    edits = orientation_request(snapshot, target)["plan"]["normalized_edits"]
    technology = snapshot.technology.model_dump(mode="json")
    cellview = {"library": "Owned", "cell": "Revision2", "view": "layout"}
    script = rendering.execution_script(
        rendering.apply_script(cellview, {}, technology, edits)
    ).decode("ascii")
    assert script.index("procedure(mcpLayoutOrientVerify") < script.index("procedure(mcpLayoutRun")
    assert f'fig~>orient="{target}"' in script
    assert script.index("mcpLayoutOrientState(fig)") < script.index("fig~>orient=")
    before_save = script.index("mcpLayoutOrientVerify(cv orientChecks 1000)")
    assert before_save < script.index("dbSave(cv)") < script.index("unless(dbClose(cv)")
    after_reopen = script.rindex("mcpLayoutOrientVerify(cv orientChecks 1000)")
    assert after_reopen > script.rindex('"maskLayout" "r"')
    assert after_reopen < script.index('printf("MCP_LAYOUT_SAVED_REOPENED')
    assert (
        "orientation_origin_changed" in script
        and "orientation_preservation_or_bbox_mismatch" in script
    )
    assert "inst~>master~>superMaster || inst~>master~>isParamCell" in script
    assert "p~>name p~>valueType p~>value" in script
    assert "orientation_property_type_unsupported" in script
    assert "fig~>xy=" not in script and "fig~>master=" not in script
    assert "dbMoveFig" not in script and "dbCreateParamInst" not in script
    with pytest.raises(ValueError, match="orientation_requires_owned_apply"):
        rendering.write_script(dict(cellview, cell="Revision1"), cellview, {}, technology, edits)


@pytest.mark.parametrize("fault", ["extra", "orientation", "origin", "bbox", "hash"])
def test_orientation_renderer_rejects_malformed_command(fault):
    snapshot = _orient_snapshot()
    edits = orientation_request(snapshot)["plan"]["normalized_edits"]
    if fault == "extra":
        edits[0]["pivot"] = {"x": 0, "y": 0}
    elif fault == "orientation":
        edits[0]["orientation"] = 'R90") exit()'
    elif fault == "origin":
        edits[0]["origin_dbu"]["x"] = True
    elif fault == "bbox":
        edits[0]["bbox_dbu"]["upper_right"]["x"] = 2147483648
    else:
        edits[0]["before_sha256"] = "f" * 63
    with pytest.raises(ValueError):
        rendering.edits_script(edits, snapshot.technology.model_dump(mode="json"))
