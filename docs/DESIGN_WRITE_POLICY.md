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

The user subsequently approved implementation and execution of the immutable V3 plan SHA-256
`3362e4fc13874d4f16c78506c24ae6ebd64c882718fe57e9cb2bb60619890c87`. Runner 0.12.0 now has
an operator-only command whose plan, target, backup, confirmation, timeout, protected
fingerprints, SKILL program, sequence, audit schema, and manifest are fixed in reviewed source.
The first invocation stopped before validation-directory creation or V3 copy because preflight
classified the preserved V1 `sch.oa-` auxiliary file as blocking. Read-only verification showed
that V1 `master.tag` authoritatively selects its regular `sch.oa` and that no active lock, panic,
or recovery file exists. The corrected gate preserves and fingerprints V1 `sch.oa-` without
treating it as a lock. Per the plan's no-automatic-retry criterion, that invocation was not retried.

The user then approved exactly one new corrected-runner invocation. Validation
`0b9bf93c-11e9-416f-9e4a-69b1060fbd8e` passed source verification, both V3 absence checks, copy,
the 35/14/8 and eight-property baseline, non-mutating dry-run, unchanged verification, backup,
and the approved one-property apply. It failed closed at exact-diff verification because a
baseline property also changed. The fixed script stopped before rollback, baseline restoration,
source-final verification, manifest creation, or audit append. No retry was attempted. The V3
target and backup now exist as preserved incomplete evidence. Source, V1 (including `sch.oa-`),
both V2 views, and `gpdk090` tree fingerprints remained exactly unchanged.

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

The prepared V3 plan remains unchanged at the approved SHA, but its clean-destination precondition
can no longer pass because both V3 names now exist. Continuing requires a separately reviewed,
explicitly approved fixed read-only V3 forensic plan. Any conditional recovery must have its own
exact acceptance criteria and approval. The V3 target and backup, V1 `sch.oa-`, all V1/V2 evidence,
Source, and PDK must remain untouched until then; retry, overwrite, deletion, and fallback names are
not authorized.

## Release gate

`v1.0.0` must not be created until a real approved copy has passed dry-run/apply equivalence,
backup restore, all local/security/integration tests, install/uninstall verification, and design
source/PDK immutability checks. Because V3 exact-diff and rollback acceptance failed, no tag or
GitHub release may be created from this checkpoint.
