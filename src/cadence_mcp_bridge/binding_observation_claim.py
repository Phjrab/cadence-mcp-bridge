"""Internal one-shot intent, never approval or a remote execution entry point."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from cadence_mcp_bridge import physical_metadata as retained
from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentProfile

LEAF = "binding-observation-01.private.json"
_PREDECESSOR = frozenset({
    "predecessor_collector_sha256", "predecessor_plan_sha256",
    "predecessor_host_request_sha256", "predecessor_remote_request_sha256",
})
_EVIDENCE = frozenset({
    "approval_receipt_sha256", "plan_sha256", "request_sha256",
    "helper_sha256", "package_sha256",
})
_SLOT = frozenset({
    "status", "plan_sha256", "request_sha256", "slot", "invocation_id",
    "authorization_sha256", "collector_sha256",
})


def _digests(value: dict[str, str], keys: frozenset[str]) -> None:
    if type(value) is not dict or set(value) != keys or any(
        type(item) is not str or re.fullmatch(r"[0-9a-f]{64}", item) is None
        for item in value.values()
    ):
        raise ValueError("binding_claim_closed_digest_refs")


def _slots(pool: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for number in range(1, 11):
        path = pool / f"slot-{number:02d}.private.json"
        if not os.path.lexists(path):
            continue
        retained._intent_metadata(path, False)
        raw = retained._payload(path)
        # Match the existing closed slot shape; never reinterpret its authority.
        value = json.loads(raw)
        if type(value) is not dict or _canonical(value) != raw or set(value) != _SLOT or (
            value["status"] != "ATTEMPT_SPENT_NO_RETRY"
            or type(value["slot"]) is not int or value["slot"] != number
            or type(value["invocation_id"]) is not str
            or re.fullmatch(r"[0-9a-f]{32}", value["invocation_id"]) is None
            or any(type(value[key]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
                   for key in _SLOT if key.endswith("_sha256"))
        ):
            raise ValueError("binding_claim_invalid_physical_slot")
        result[path.name] = raw
    return result


def claim(
    environment: EnvironmentProfile, predecessor: dict[str, str], evidence: dict[str, str],
) -> None:
    """Spend a fixed account/campaign identity before any separately approved work.

    Evidence hashes refer to records of a separate finite approval; they are not
    approval themselves. This primitive has no transport and is not called by
    local prepare/export. Existing or partial markers can never be retried.
    """
    _digests(predecessor, _PREDECESSOR)
    _digests(evidence, _EVIDENCE)
    retained._local_predecessor(environment, predecessor)
    pool = retained._followup_pool(environment, True)
    ancestry = {path: retained._intent_metadata(path, True) for path in (pool, pool.parent)}
    descriptor, lock_guard = retained._lock_followup(pool)
    try:
        def guard() -> None:
            lock_guard()
            if any(retained._intent_metadata(path, True) != before
                   for path, before in ancestry.items()):
                raise ValueError("binding_claim_namespace_drift")
            retained._local_predecessor(environment, predecessor)

        guard()
        target = pool / LEAF
        if os.path.lexists(target):
            raise FileExistsError("binding_observation_spent_no_retry")
        before = _slots(pool)
        value = {
            "schema_version": 1,
            "status": "ATTEMPT_SPENT_NO_RETRY",
            "scope": "BINDING_OBSERVATION_01_SEPARATE_FINITE_APPROVAL_REQUIRED",
            "approval_is_external": True,
            "campaign_identity_sha256": retained._followup_identity(environment),
            "predecessor": predecessor,
            "evidence": evidence,
            "retained_physical_slot_sha256": {
                name: retained._sha(raw) for name, raw in before.items()
            },
        }
        retained._exclusive_intent(target, value)
        guard()
        if _slots(pool) != before:
            raise ValueError("binding_claim_physical_history_drift")
    finally:
        os.close(descriptor)
