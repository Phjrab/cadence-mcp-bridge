# Controlled Design Write Policy

## Current status

WP-11 design writes are **blocked after an incomplete real validation**. The user approved the
dedicated `MCP_WorkLib` library, the exact source and destination, and the sole string property
mutation. The bridge now exposes one read-only plan tool and one confirmation-gated validation
tool, for a total of twenty-two public tools.

The first real run created the approved destination copy
`MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST/schematic`, then stopped before dry-run completion
because IC6.1.5 does not provide the attempted `dbFindPropByName` helper. No property apply,
backup, rollback, tag, or release occurred. That V1 target and its recovery artifacts remain
untouched.

The user subsequently approved a clean V2 target and backup. Runner 0.9.0 binds the canonical plan
to `Differential_Amplifier_TB2_MCP_TEST_V2` and
`Differential_Amplifier_TB2_MCP_TEST_V2_BACKUP`, uses the IC6.1.5-compatible `dbFindProp`, restores
the target from the actual backup, compares logical baseline fingerprints, and fingerprints the
preserved V1 target. The V2 plan and read-only SKILL compatibility preflight passed, but the final
pre-apply gate found an active OA lock on the read-only source owned by Virtuoso PID 25425. The
user's lock policy therefore blocks the actual V2 copy; both V2 cell names remain absent.

## Permanent protections

- PDK libraries, including `gpdk090`, are permanently read-only.
- shared Cadence libraries such as `analogLib` and `basic` are permanently read-only.
- reviewed source libraries `MyDesignLib` and `MyFirstDesign` remain read-only.
- the original cellview and ADE state must never be modified.
- arbitrary paths, file contents, SKILL/OCEAN text, and generic shell/SSH commands remain forbidden.

`write_policy.py` classifies the known protected and source library names, designates only
`MCP_WorkLib` as eligible, and lists only
`set_cellview_property:mcpMutationTest=validated-v1`. The remote plan independently checks that
the fixed source and preserved V1 target exist and both V2 target and backup do not exist. The
execution tool additionally requires the exact `APPROVE_MCP_WRITE_VALIDATED_V2` confirmation.

## Required action before resuming WP-11

The operator must close or otherwise safely finish the Virtuoso session that owns source lock PID
25425. Codex is not authorized to terminate that process or remove either lock file. After the
operator confirms the session is closed, the next run must verify that Cadence removed the locks
normally. A remaining stale lock still blocks execution and requires a separate explicit decision.
PDK, source, V1, and unrelated library writes remain prohibited.

## Release gate

`v1.0.0` must not be created until a real approved copy has passed dry-run/apply equivalence,
backup restore, all local/security/integration tests, install/uninstall verification, and design
source/PDK immutability checks. Because the required sequence did not complete, no tag or GitHub
release may be created from this checkpoint.
