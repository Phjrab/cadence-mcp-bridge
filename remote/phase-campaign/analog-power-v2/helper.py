#!/usr/bin/env python
"""Read-only budget boundary adapter; retains the immutable v1 receipt."""
import imp
import json
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
P = imp.load_source("power_v1_preserved", ROOT + "/phase-campaign/analog-power-v1/helper.py")


def validate_read_counter(counter, policy):
    if (set(counter) != set(("campaign_id", "count", "result_reserved_bytes"))
            or counter["campaign_id"] != "AUTO-PHASE-01"
            or type(counter["count"]) not in P.B.INTEGER_TYPES
            or not 32 <= counter["count"] <= policy["max_spectre_attempts"]
            or type(counter["result_reserved_bytes"]) not in P.B.INTEGER_TYPES
            or not 3088056320 <= counter["result_reserved_bytes"] <= policy["max_new_results_bytes"]):
        raise ValueError("invalid cumulative read accounting")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "result":
        raise ValueError("fixed power read action")
    # No reservation is made; valid exhausted budgets must not block old reads.
    P.N.validate_counter = validate_read_counter
    current = P.snapshot()
    before = json.loads(P.B.read(P.RUNTIME + "/before.json", 32768))
    if dict((k, v) for k, v in current.items() if k != "counter") != dict(
            (k, v) for k, v in before.items() if k != "counter"):
        raise ValueError("preserved power source drift")
    data = json.loads(P.B.read(P.RUNTIME + "/result.json", 32768))
    if (data["input_sha256"] != P.INPUT_SHA or data["psf_sha256"] != P.PSF_SHA
            or data["frame_sha256"] != P.B.sha(P.B.read(P.RUNTIME + "/frame.txt", 8192))):
        raise ValueError("preserved power receipt drift")
    P.emit(data)
