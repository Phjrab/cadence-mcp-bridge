from __future__ import annotations

import pytest

from cadence_mcp_bridge.errors import ConfigurationError, InvalidInputError
from cadence_mcp_bridge.write_policy import (
    classify_write_target,
    get_write_readiness,
    require_write_ready,
)


def test_write_readiness_contains_only_the_approved_contract() -> None:
    readiness = get_write_readiness()

    assert readiness.status == "ready"
    assert readiness.work_library == "MCP_WorkLib"
    assert readiness.allowed_mutations == (
        "set_cellview_property:mcpMutationTest=validated-v1",
    )
    assert readiness.dry_run_available is True
    assert readiness.apply_available is True
    assert readiness.rollback_available is True
    assert readiness.release_ready is False


@pytest.mark.parametrize("library", ["analogLib", "basic", "gpdk090", "gpdk090_v46"])
def test_pdk_and_shared_libraries_are_permanently_read_only(library: str) -> None:
    classification = classify_write_target(library)

    assert classification.classification == "pdk-or-shared"
    assert classification.writable is False
    with pytest.raises(InvalidInputError, match="read-only"):
        require_write_ready(library)


@pytest.mark.parametrize("library", ["MyDesignLib", "MyFirstDesign"])
def test_source_libraries_require_a_copy(library: str) -> None:
    classification = classify_write_target(library)

    assert classification.classification == "source"
    assert classification.writable is False
    with pytest.raises(InvalidInputError, match="copy"):
        require_write_ready(library)


def test_only_configured_work_library_is_write_eligible() -> None:
    classification = classify_write_target("MCP_WorkLib")

    assert classification.classification == "work"
    assert classification.writable is True
    require_write_ready("MCP_WorkLib")

    with pytest.raises(ConfigurationError, match="blocked"):
        require_write_ready("CadenceMCPWork")


@pytest.mark.parametrize("library", ["../MyDesignLib", "gpdk090;rm", "line\nbreak", "*"])
def test_library_identifier_rejects_path_and_shell_syntax(library: str) -> None:
    with pytest.raises(InvalidInputError, match="identifier"):
        classify_write_target(library)
