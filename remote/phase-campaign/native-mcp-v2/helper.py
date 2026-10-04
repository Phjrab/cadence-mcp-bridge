#!/usr/bin/env python
"""Versioned native adapter for the user's cumulative 500-attempt ceiling."""
from __future__ import with_statement

import imp
import json
import os
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/native-mcp-v2"
POLICY_SHA = "b534b0ade1d17c75cfa711911feca6b8625f2662dde91c621a60fb1fa43d9a8b"
N = imp.load_source("native_v2_preserved", ROOT + "/phase-campaign/native-mcp-v1/helper.py")
BASE = N.BASE
N.VERSION = VERSION
# The original native job directory/UUIDs remain the replay domain.


def authorization():
    policy = json.loads(BASE.read(VERSION + "/budget-policy.json", 4096))
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    if BASE.sha(canonical.encode("ascii")) != POLICY_SHA:
        raise ValueError("cumulative budget policy drift")
    activation = json.loads(BASE.read(VERSION + "/activation.private.json", 4096))
    if activation != {"schema_version": 1, "campaign_id": "AUTO-PHASE-01",
            "change_id": "SPECTRE-LIMIT-500-01", "policy_sha256": POLICY_SHA,
            "user_delegation": "explicit-in-current-task"}:
        raise ValueError("budget activation absent or changed")
    return policy


def validate_counter(counter, policy):
    if (set(counter) != set(("campaign_id", "count", "result_reserved_bytes"))
            or counter["campaign_id"] != "AUTO-PHASE-01"
            or type(counter["count"]) not in BASE.INTEGER_TYPES
            or not 32 <= counter["count"] < policy["max_spectre_attempts"]):
        raise ValueError("cumulative Spectre budget")
    if (type(counter["result_reserved_bytes"]) not in BASE.INTEGER_TYPES
            or not 3088056320 <= counter["result_reserved_bytes"]
                <= policy["max_new_results_bytes"] - BASE.RESERVATION):
        raise ValueError("unchanged cumulative result budget")


def audit_reservations(counter):
    if os.path.lexists(BASE.COUNTER + ".ade-tmp"):
        raise ValueError("uncertain cumulative ledger transaction")
    for name in os.listdir(N.JOBS):
        if name in ("control.lock", "active"):
            continue
        if not N.ID.match(name):
            raise ValueError("unexpected native replay entry")
        record = N.JOBS + "/" + name
        N.contained(record)
        marker = record + "/work/attempt-reserved"
        if os.path.lexists(marker):
            intent = json.loads(BASE.read(marker, 1024))
            if (set(intent) != set(counter) or intent["campaign_id"] != "AUTO-PHASE-01"
                    or type(intent["count"]) not in BASE.INTEGER_TYPES
                    or type(intent["result_reserved_bytes"]) not in BASE.INTEGER_TYPES
                    or not 1 <= intent["count"] <= counter["count"]
                    or not 0 <= intent["result_reserved_bytes"] <= counter["result_reserved_bytes"]):
                raise ValueError("unreconciled native reservation")


def preflight():
    policy = authorization()
    BASE.environment_preflight()
    BASE.snapshot()
    N.references()
    if BASE.state_facts()["variables_v"] != N.CAND.SAVED:
        raise ValueError("saved source settings drift")
    counter = json.loads(BASE.read(BASE.COUNTER, 1024))
    validate_counter(counter, policy)
    audit_reservations(counter)


def reserve():
    # The existing worker holds the shared EDA lock throughout this operation.
    policy = authorization()
    BASE.environment_preflight()
    BASE.verify_netlist()
    if os.path.lexists(BASE.JOB + "/attempt-reserved"):
        raise ValueError("simulation replay")
    counter = json.loads(BASE.read(BASE.COUNTER, 1024))
    validate_counter(counter, policy)
    audit_reservations(counter)
    counter["count"] += 1
    counter["result_reserved_bytes"] += BASE.RESERVATION
    BASE.save(BASE.JOB + "/attempt-reserved", counter)
    BASE.save(BASE.COUNTER + ".ade-tmp", counter)
    os.rename(BASE.COUNTER + ".ade-tmp", BASE.COUNTER)


N.preflight = preflight
BASE.reserve = reserve


if __name__ == "__main__":
    try:
        authorization()
        N.main()
    except (IOError, OSError, ValueError, KeyError, TypeError, UnicodeError, IndexError,
            ZeroDivisionError):
        sys.stderr.write("fixed native cumulative-budget operation failed\n")
        sys.exit(69)
