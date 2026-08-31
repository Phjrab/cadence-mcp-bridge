# Controlled Design Write Policy

## Current status

WP-11 controlled-write acceptance is **verified; release progression remains pending**. The
preserved V3 target was restored from its fixed backup, and a new V4 clean validation subsequently
passed all 18 plan criteria. The user approved the
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

Runner 0.13.0 adds one argument-free, operator-only, fixed read-only V3 property-diff command.
It opens Source, V3 target, and V3 backup only in read mode, fingerprints Source, V1, both V2
views, both V3 views, and `gpdk090` before and after, and rejects any active Virtuoso process or
blocking artifact. The approved investigation found exactly two differences without returning or
storing values: `schGeometryLastUpdated` is `int` and present on both sides with unequal values;
`mcpMutationTest` is absent from backup, present as `string` in target, and its equality to the
fixed approved value is true. All seven protected fingerprints remained unchanged.

The user then approved an exact-value deep forensic limited to Source, V3 target, and V3 backup.
Runner 0.14.0 opens only those three cellviews with OpenAccess read mode and fingerprints their
complete cellview trees before and after. Forensic report SHA-256
`6329eafc458098b744a40b70fc0a1a0d876af57c326d2d79e854e1ceaeb9b02f` classifies the state as
`SAFE_ROLLBACK_CANDIDATE`: Source, target, and backup have identical 35/14/8 structural hashes;
Source and backup have the same eight exact cellview properties; and the complete target-to-backup
diff contains only `mcpMutationTest` (`string`, `validated-v1` to absent) and
`schGeometryLastUpdated` (`int`, `107169` to `107168`). The original validation log proves backup
preceded apply, but its completion manifest, audit record, and runner job record are missing. The
deep forensic created only a mode-600 report under `.cadence_mcp`; no OA write or rollback occurred.

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

The clean V3 plan remains unchanged at its approved SHA, but its clean-destination precondition can
no longer pass. The exact-value read-only forensic is complete. Its new non-executable conditional
rollback plan is `remote/config/design-write-v3-exact-conditional-rollback-plan.json`, SHA-256
`eb057da2a866b92be5e1474bc3d06aba05f6ae49b5001465dd65ed9921afc911`. It has 14 conditional
stages and 15 acceptance criteria, fixes both exact property transitions, requires a future exact
confirmation tied to that raw hash, and is not deployed to the runner. Source, target, and backup
must remain untouched until separate rollback approval; overwrite, retry, cleanup, deletion, and
fallback names are not currently authorized. The earlier redacted plan remains historical evidence.

The first plan-authorized rollback execution, ID
`38cfdbf3-ae92-470b-bf38-6789887a3ae9`, stopped before Virtuoso or any OA write because the fixed
rollback evidence parent directory did not yet exist. After a separate approval tied to the same
plan hash, corrected runner 0.15.0 was redeployed and exactly one new execution was performed with
ID `575356ae-1853-409f-a913-25c1ba9038a8`. All preconditions were revalidated. The fixed V3
backup restored only `mcpMutationTest` (`string`, `validated-v1` to absent) and
`schGeometryLastUpdated` (`int`, `107169` to `107168`) on the fixed V3 target. All 15 plan
acceptance criteria passed: topology stayed 35/14/8, instance/net/terminal logical hashes were
unchanged, the target property hash matched the backup, and Source and backup tree fingerprints
were unchanged. The result is `V3_ROLLBACK_VERIFIED`.

The immutable rollback manifest is mode 400 at
`.cadence_mcp/write-rollback-v3/575356ae-1853-409f-a913-25c1ba9038a8/rollback-manifest.json`,
SHA-256 `77c92d1bd0bf7c68666c60cceb630ad66945ece402d4f36271a24eb6078aac34`. The mode-600 audit file
`.cadence_mcp/audit/v3-rollback-events.jsonl` contains exactly 14 records for this run and has
SHA-256 `4786eab04bdc3ea9d1626b1123e62a25a00ee8efdcce919db4da653ab9c8e34f` at verification time.
The original V3 validation manifest, audit, and job record remain missing historical evidence.
V1, V2, the V3 target, and the V3 backup remain preserved; no cleanup or additional mutation is
authorized.

## Release gate

`v1.0.0` must not be created until a new real approved clean copy has passed dry-run/apply equivalence,
backup restore, all local/security/integration tests, install/uninstall verification, and design
source/PDK immutability checks. The V3 recovery gate passed, but it does not retroactively complete
the failed V3 clean validation. V4 now satisfies this controlled-write gate, but a tag and GitHub
release remain prohibited until repository acceptance, versioning, and release authorization are
completed.

## Proposed V4 clean-validation plan

`remote/config/design-write-v4-plan.json` is a planning-only asset with SHA-256
`c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66`. It fixes the new target
`MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4/schematic` and backup
`MCP_WorkLib/Differential_Amplifier_TB2_MCP_TEST_V4_BACKUP/schematic`, preserves all five V1/V2/V3
cellviews, and keeps Source and `gpdk090` read-only. The proposed semantic mutation remains the
single `mcpMutationTest` string property. The plan separately bounds the Cadence-maintained
`schGeometryLastUpdated` integer as the only permitted metadata side effect: its exact observed
before/after values must be recorded, and no other baseline property may change.

The immutable plan contains 18 stages and 18 acceptance criteria. Its checked-in planning flags
remain deliberately non-executable:
`execution_enabled`, `implementation_enabled`, and `release_gate_enabled` are false;
`required_confirmation` is null. After a separate approval bound to the unchanged raw hash, runner
0.16.0 implemented an operator-only fixed confirmation outside the plan asset and executed exactly
once. Run `e636eeba-80dc-4280-b2ea-4f23b0cd1139` completed
`V4_CLEAN_VALIDATION_VERIFIED`. The actual apply diff contained only `mcpMutationTest` and the
bounded `schGeometryLastUpdated` transition from `107168` to `107169`; topology and structural
hashes stayed fixed at 35/14/8. Rollback removed the mutation and restored the full property hash
`cf24d8a4f8434b2208afa48a4b555c322f29470b7a8632ded90037b3221374a4`.

The immutable mode-400 manifest is
`.cadence_mcp/write-validation-v4/e636eeba-80dc-4280-b2ea-4f23b0cd1139/validation-manifest.json`,
SHA-256 `e7b306db74fe28040584b39e94b980709d61aa8a19e78ad0987ab688d1e9db7b`. The mode-600 audit file
contains exactly 18 records for this run and had verification-time SHA-256
`befbe1e5ebdf253c892085214881e829209720990f4f3a37b70232f8c909ac35`. Source, V1, both V2
views, restored V3 target, V3 backup, and `gpdk090` tree fingerprints were identical before and
after. V4 target and backup remain as restored evidence. No retry, cleanup, tag, or release was
performed.
