"""Reviewed simulation profile registry and validation helpers."""

from __future__ import annotations

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import (
    ProfileList,
    ProfileSummary,
    ProfileVariableSpec,
    SimulationProfile,
)

FIXTURE_PROFILE_ID = "fixture-rc-transient"

FIXTURE_PROFILE = SimulationProfile(
    profile_id=FIXTURE_PROFILE_ID,
    classification="fixture",
    netlist_source="built-in-rc-template",
    analyses=("tran",),
    variables=(
        ProfileVariableSpec(
            name="resistance_ohm",
            unit="ohm",
            minimum=100.0,
            maximum=10_000.0,
            default=1_000.0,
        ),
        ProfileVariableSpec(
            name="capacitance_f",
            unit="F",
            minimum=1e-13,
            maximum=1e-10,
            default=1e-12,
        ),
        ProfileVariableSpec(
            name="stop_time_s",
            unit="s",
            minimum=1e-10,
            maximum=1e-7,
            default=1e-9,
        ),
    ),
    corners=("nominal",),
    outputs=("out",),
    timeout_seconds=60,
)


def list_profiles() -> ProfileList:
    return ProfileList(
        registry_version=1,
        profiles=(
            ProfileSummary(
                profile_id=FIXTURE_PROFILE.profile_id,
                classification=FIXTURE_PROFILE.classification,
                analyses=FIXTURE_PROFILE.analyses,
                corners=FIXTURE_PROFILE.corners,
                outputs=FIXTURE_PROFILE.outputs,
            ),
        ),
    )


def get_profile(profile_id: str) -> SimulationProfile:
    if profile_id != FIXTURE_PROFILE_ID:
        raise InvalidInputError("profile is outside the reviewed registry")
    return FIXTURE_PROFILE


def validate_corner(profile: SimulationProfile, corner: str) -> str:
    if corner not in profile.corners:
        raise InvalidInputError("corner is outside the profile allowlist")
    return corner
