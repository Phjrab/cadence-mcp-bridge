# GENERIC-MEAS-01 result v1

Starting main: `a776ec0230ac32f8a2eee2fb99ebd1884c2f1726` (merged #112).
Branch: `feat/generic-meas-01`. The dedicated containing feature PR integrates
this result; the private final checkpoint records exact head/PR/ending main and
remote verification. No state-sync-only PR, release/tag or package publication.
See [workflow and recovery](GENERIC_MEASUREMENTS_V1.md).

## Implementation and qualification

Design registry v4 adds immutable measurement definitions bound to exact allowed
analysis and compiled definition hashes. Existing operator schema/validate/
register/verify/client-config workflows are extended; no competing configuration
or model-controlled registration is introduced. The built-in reference uses v4;
explicit v1/v2/v3 registries remain unchanged and do not gain implicit readers.
Original schema files and analysis plan/admission identities are preserved.

Three read-only tools are added: `cadence_list_measurements`,
`cadence_describe_measurement`, `cadence_measurement_result`. Tool count rises
**48 → 51**; all 48 previous full tool schemas compare exactly equal to starting
main, and 22 v1 declarations remain. Tools have closed JSON inputs, bounded typed
structured results, read-only annotations and client-independent descriptions.

The compiled reader projects existing native DC voltage scalars, AC differential
transfer spectrum and adaptive TRAN summary. It requires the bound registered
analysis, matching PDK/native compatibility and durable admitted UUID4. Stale,
unknown, unqualified and unadmitted requests are denied before result transport.
Native identity, evidence and shape are revalidated; invalid sources produce a
bounded error. No new extraction, simulation, journal, arbitrary signal/formula/
script/path/netlist/result-input/target or protected file access is added.

Results retain units/method/bounds, fixed effective settings, source/PSF/frame
fingerprints, canonical whole native-result and contract/plan/definition hashes,
revision/operating point and warnings/notices. `quality=valid` describes qualified
extraction. **spec_evaluation=not_evaluated**; no target/threshold/PASS or optimum
is invented. Bandwidth, phase margin, power and MOS OP measurement definitions
remain outside this implementation until separately qualified.

## Verification

| Gate | Actual evidence |
| --- | --- |
| Frozen dependency sync | Pass |
| Ruff / mypy | Pass; 33 source files |
| Focused contract/service/MCP/security-related regression | 299 passed; two OS symlink skips |
| Full unit coverage | 1,512 passed / three OS symlink skips / 56 existing warnings; one Git environment failure subsequently rechecked alone and passed, covering all 1,513 tests |
| Security / dependency scan | 18 passed; one pytest cache-permission warning; no known locked dependency vulnerabilities |
| Installed package | Actual wheel/sdist audit, v4 fictional registration/inspection, Codex/common JSON/Claude stdio, 51 tools/22 legacy names, unqualified measurement/analysis admission denial, uninstall/import absence/cleanup pass |
| Compatibility | All previous 48 full schemas exactly equal; v1/v2/v3 schema and analysis plan identity tests pass |
| Actual native stdio | Codex/Claude exported SDK subprocess settings read three preserved native results and registered measurements; values/settings/frame/result hashes match, restart reads are equal; stale hash denial verified |

Actual stdio does not qualify either named desktop application. Claude remains
CLAUDE_REAL_CLIENT_UNVERIFIED and no fresh Codex app E2E is claimed. Existing
native lifecycle/source/PDK/runner implementations were retained. Unit fixtures
are synthetic; no private circuit measurements are committed in this report.

The canonical package gate includes the licensing/content audit from #112 before
isolated install. New packages contain only curated original source and notices;
private journals/credentials/license values/PDK/PSF/raw data/imported planning are
excluded. The package/runtime version remains 1.0.0; no release is created.

## Corrections, environment and resources

Code corrections: **2/3**, with failures preserved privately. First resolved
initial style. Second separated JSON-compatible compiled output definitions from
strict input contracts, enveloped native validation failures from the reused
analysis wrapper, and updated three read-only tool expectations.

An initial E2E launch and one full-suite authority test lacked the established
Git safe-directory/EXEC_PATH settings. The existing fail-closed remote-identity
gate correctly denied them. Restoring the execution environment made the same
sealed E2E and isolated authority test pass; no code/policy/guard was weakened.
The initial full-suite failure remains recorded rather than claimed as PASS.

New Spectre attempts: **0**. Result reservation delta: **0 bytes**. Remote
deployment: **0 bytes**. Existing counter remains 62 attempts / 7,114,588,160
historically reserved bytes. No budget/history reset or elapsed ceiling is
introduced. Fresh protected source/PDK, job trees, counters, old private evidence
and existing admission/sweep journal hashes are equal. All unmodified production
modules retain their original byte hashes; modified adapters are explicitly
reviewed and sealed for the preserved-job E2E.

## What another operator can do and remaining limits

An operator can register/inspect measurement definitions through the same design
registry and read qualified admitted native observations with exact provenance
without repeating simulation/extraction. A fictional/new physical design may
register unqualified definitions but cannot activate the reference reader.

Generic physical environment/design/PDK adapters, new electrical ranges and
additional measurement definitions remain unqualified. Licensing/imported
`docs/agent_plan/` rights review, real desktop qualification and exact candidate/
publication authorization remain public-release gates. Original-code Apache-2.0
and its external Cadence/PDK/client/dependency boundary are preserved.

Recommend **GENERIC-SWEEP-01 contract/planning preparation**, integrating the
registered analysis/variable/measurement foundations while rejecting real-design
execution with unqualified numeric ranges. Finite candidate evidence does not
establish a continuous safe voltage range. Do not expand/guess such a range to
make a sweep runnable. Report once and ask before that next major phase.
