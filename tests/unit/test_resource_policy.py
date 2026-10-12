"""Fresh observations cannot inherit the development campaign or a larger budget."""

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from cadence_mcp_bridge.power_measurements import RegisteredPowerCounter
from cadence_mcp_bridge.resource_policy import FreshResourceCounter
from cadence_mcp_bridge.storage import StorageSnapshot


def observation():
    campaign = str(uuid4())
    return dict(
        campaign_id=campaign, count=0, result_reserved_bytes=0,
        policy=dict(campaign_id=campaign, attempt_ceiling=2, result_ceiling_bytes=131072),
    )


@pytest.mark.parametrize(
    "change",
    ["missing-policy", "campaign", "count", "bytes", "bool", "missing-bytes", "orphan-bytes"],
)
def test_fresh_counter_rejects_missing_stale_or_exceeded_policy(change):
    value = observation()
    if change == "missing-policy":
        del value["policy"]
    elif change == "campaign":
        value["policy"]["campaign_id"] = str(uuid4())
    elif change == "count":
        value["count"] = 3
    elif change == "bytes":
        value["result_reserved_bytes"] = 131073
    elif change == "missing-bytes":
        value["count"] = 1
    elif change == "orphan-bytes":
        value["result_reserved_bytes"] = 1
    else:
        value["count"] = False
    with pytest.raises(ValidationError):
        TypeAdapter(RegisteredPowerCounter).validate_python(value)


def test_legacy_counter_serialization_stays_exact():
    value = dict(campaign_id="AUTO-PHASE-01", count=82, result_reserved_bytes=9798942720)
    assert TypeAdapter(RegisteredPowerCounter).validate_python(value).model_dump() == value
    with pytest.raises(ValidationError):
        FreshResourceCounter.model_validate(value)


def test_smaller_storage_ceiling_requires_v2_registered_policy():
    value = dict(
        snapshot_id="a" * 64, artifacts=[], coverage_complete=True, group_coverage={},
        filesystem_free_bytes=1000000, filesystem_total_bytes=10000000,
        reserved_result_bytes=0, result_ceiling_bytes=131072, spectre_attempts=0,
        active_eda=False, platform_delete_primitives=True,
    )
    with pytest.raises(ValidationError):
        StorageSnapshot.model_validate(value)
    value.update(contract_version=2, ledger_policy=observation()["policy"])
    assert StorageSnapshot.model_validate(value).result_ceiling_bytes == 131072
    value["reserved_result_bytes"] = 131073
    with pytest.raises(ValidationError):
        StorageSnapshot.model_validate(value)
