"""Reviewed simulation profile registry and validation helpers."""

from __future__ import annotations

from cadence_mcp_bridge.errors import InvalidInputError
from cadence_mcp_bridge.models import (
    AdeProfileMetadata,
    NoProfileVariables,
    ProfileList,
    ProfileSummary,
    ProfileVariables,
    ProfileVariableSpec,
    RcTransientVariables,
    SimulationProfile,
)

FIXTURE_PROFILE_ID = "fixture-rc-transient"
ACTUAL_PROFILE_ID = "actual-differential-amplifier-tb2-transient"

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

ACTUAL_PROFILE = SimulationProfile(
    profile_id=ACTUAL_PROFILE_ID,
    classification="actual",
    netlist_source="ade-l-state-netlist",
    analyses=("tran",),
    variables=(),
    corners=("NN",),
    outputs=(),
    timeout_seconds=300,
    allowed_warning_codes=("CMI-2477",),
    maximum_warning_count=2,
    ade=AdeProfileMetadata(
        library="MyDesignLib",
        cell="Differential_Amplifier_TB2",
        view="schematic",
        ade_product="ADE L",
        state="state1",
        pdk="gpdk090",
        pdk_version="4.6",
        model_section="NN",
        temperature_c=27.0,
        spectre_stop_time="4m",
        stop_time_s=0.004,
    ),
)

_PROFILES = {
    FIXTURE_PROFILE.profile_id: FIXTURE_PROFILE,
    ACTUAL_PROFILE.profile_id: ACTUAL_PROFILE,
}


def list_profiles() -> ProfileList:
    return ProfileList(
        registry_version=1,
        profiles=tuple(
            ProfileSummary(
                profile_id=profile.profile_id,
                classification=profile.classification,
                analyses=profile.analyses,
                corners=profile.corners,
                outputs=profile.outputs,
            )
            for profile in _PROFILES.values()
        ),
    )


def get_profile(profile_id: str) -> SimulationProfile:
    try:
        return _PROFILES[profile_id]
    except KeyError as exc:
        raise InvalidInputError("profile is outside the reviewed registry") from exc


def validate_corner(profile: SimulationProfile, corner: str) -> str:
    if corner not in profile.corners:
        raise InvalidInputError("corner is outside the profile allowlist")
    return corner


def validate_variables(
    profile: SimulationProfile, variables: ProfileVariables
) -> ProfileVariables:
    if profile.profile_id == FIXTURE_PROFILE_ID and not isinstance(
        variables, RcTransientVariables
    ):
        raise InvalidInputError("fixture profile requires its reviewed numeric variables")
    if profile.profile_id == ACTUAL_PROFILE_ID and not isinstance(
        variables, NoProfileVariables
    ):
        raise InvalidInputError("actual profile does not allow design variables")
    return variables
