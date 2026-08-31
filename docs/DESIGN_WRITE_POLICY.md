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
preserved V1 target. The source gate now requires `master.tag` to authoritatively select a regular
`sch.oa`, rejects active locks and panic/recovery artifacts, and requires the source topology to be
exactly 35 instances, 14 nets, and eight terminals. The separately preserved source `sch.oa-` is
fingerprinted but is not treated as an active lock after the user's Cadence/OpenAccess read-only
verification.

Real validation `e55c7e81-cf20-4d5e-b2d9-67dae0ddcd1b` completed source verification, V2 copy,
baseline fingerprinting, dry-run, unchanged verification, backup, and the approved property apply
marker. The fixed 90-second process limit then sent SIGTERM before apply verification and rollback.
Both V2 cell names now exist. No completion manifest or design-write audit records were written,
so the validation is failed and its post-apply state is not accepted as verified.

The user then approved a fixed read-only V2 forensic check and a backup restore only if the V2
target differed from the 35/14/8 backup by exactly the approved `mcpMutationTest` property. Runner
0.10.0 added that closed recovery path. The compatibility-correct forensic result was
`MCP_V2_FORENSIC_FAILURE|V2 target changed a baseline property`; therefore the user's rollback
precondition did not pass. The backup restore command was not invoked, no recovery audit or
success evidence was written, and both V2 cellviews remain preserved without deletion.

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

The prepared V3 plan is stored in `remote/config/design-write-v3-plan.json`. It fixes the target
and backup to the user-selected V3 names, preserves V1 and both V2 cellviews as evidence, raises the
worker limit to 300 seconds, and keeps `execution_enabled=false`, `required_confirmation=null`, and
`release_gate_enabled=false`. Its status is `blocked_on_v2_exact_diff_failure`; there is no V3
apply command. Continuing requires a new explicit decision to either authorize a broader,
backup-based V2 restore despite the baseline-property mismatch or preserve the failed V2 state and
separately approve implementation and execution of the reviewed V3 plan.

## Release gate

`v1.0.0` must not be created until a real approved copy has passed dry-run/apply equivalence,
backup restore, all local/security/integration tests, install/uninstall verification, and design
source/PDK immutability checks. Because the required sequence did not complete, no tag or GitHub
release may be created from this checkpoint.
