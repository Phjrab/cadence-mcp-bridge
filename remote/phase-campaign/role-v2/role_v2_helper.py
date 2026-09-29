#!/usr/bin/env python
"""Bind the reviewed names-only parser to a fresh, private v2 runtime."""

from __future__ import with_statement

import imp
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
BASE = ROOT + "/phase-campaign/role-v1/wp14_role_discovery.py"
RUNTIME = ROOT + "/wp14-role-discovery-v2"

if len(sys.argv) != 2 or sys.argv[1] not in ("preflight", "gate", "complete"):
    sys.exit(64)

worker = imp.load_source("fixed_wp14_role_discovery", BASE)
worker.RUNTIME = RUNTIME
worker.BEFORE_PATH = RUNTIME + "/before.json"
sys.exit(worker.main())
