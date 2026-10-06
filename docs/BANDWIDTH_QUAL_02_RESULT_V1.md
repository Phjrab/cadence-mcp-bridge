# BANDWIDTH-QUAL-02 result

Start main: `d97d9934341d382c1131ee1f5d61ab8cc75ace38` (merged #126).
Branch: `feat/bandwidth-qual-02`. Exact reviewed head, PR, merge and remote main/tree
verification are retained privately after this containing implementation PR;
no state-only follow-up is required.

## Real reference scientific evidence

The original10-point/decade AC result is reused. Two scientifically justified
fixed refinements ran with installed Spectre12.1, original differential excitation,
same NN/27 C/VDD1 V/effective320/702 mV candidate and unchanged circuit/model/options.
The installed AC help confirmed `start`/`stop`/`dec`; source input/PSF were pinned.
Reversing each owned AC line reproduces the exact original native input hash.
Both simulations and fixed OCEAN extraction passed their protection/quality guards.
No original/ADE/PDK or historical result changed.

| Grid points/decade | Samples / observed interval | First -3.0 dB estimate | Containing sample bracket |
| --- | --- | --- | --- |
| 10, preserved | 71 /10 Hz–100 MHz | 487,663.024077 Hz | 398,107.2–501,187.2 Hz |
| 50, new | 251 /10 Hz–1 MHz | 488,885.836317 Hz | 478,630.1–501,187.2 Hz |
| 100, new | 501 /10 Hz–1 MHz | 489,006.855322 Hz | 478,630.1–489,778.8 Hz |

Reference gain is78.951961906998 dB at10 Hz in all three grids. Sampled10–1,000 Hz
gain spans are0.000018906449,0.000019037958,0.000019037958 dB with21/101/201
samples. Maximum observed peaking above the reference is below0.000000425 dB.
Each observed interval has one downward crossing. Successive relative changes
are0.2501222471% and0.0247479159%; last change is121.019006 Hz. Relative bracket
widths decrease21.13755%→4.61398%→2.27987%.

The preselected empirical criteria yield `OBSERVED_WITHIN_0_1_PERCENT`.
This is not a measured error bound. Status remains **PARTIALLY_QUALIFIED**;
absolute error bound is absent. Preserve the exact existing10 Hz/3.0 dB definition
and its original result. No conventional DC, half-power, unity-gain, closed-loop,
PVT-wide or specification-PASS claim. See [definition and limits](BANDWIDTH_QUALIFICATION_V1.md).

## Implementation and compatibility

One read-only additive tool: `cadence_bandwidth_study_result`.75→76 tools, all old75
full schemas and v1-v8 registries exact. Original analog/native/sweep/goal identity
and default configuration remain unchanged. Separate refinement schema v1 avoids
silently extending the old72-record native result. Source admission and exact
receipt/provenance checks protect the supplemental read. No public new execution
route or raw vectors. Package version1.0.0 remains unchanged.

Focused new science/operator tests78 PASS; combined analog/power/contract tests158
PASS before final refinement provenance fields. Final full/static/contract/package
and security outcomes are recorded below. Initial static and fixture
failures remain private, with conservative correction accounting. Historical sizing
postflight FAIL after new reservations is retained; the separately composed
phase verifier passes original protection/fingerprints and exact new reservation
conservation. It does not weaken or rerun the historical checker as a claimed PASS.

SDK stdio PASS uses the exported Codex configuration, current source and actual
preserved/reference Cadence files. New study, old bandwidth, native DC/AC/TRAN,
signed power, registered sweep and server restart are checked independently.
SDK evidence is not actual Desktop app E2E. New actual app tool calls: NOT_RUN.
Claude actual app: DEFERRED / CLAUDE_REAL_CLIENT_UNVERIFIED; its configuration/
protocol adapter remains intact. Other Cadence/PDK/host qualification is deferred.

## Resource and protection accounting

- This phase: two Spectre attempts;268,435,456 new cumulative reserved bytes.
- Cumulative:64/500 attempts;7,383,023,616/10,737,418,240 reserved bytes.
- New result jobs:832,281 logical bytes;937,984 allocated bytes.
- Result-runtime root including its container:832,281 logical bytes;942,080 allocated bytes.
- New immutable deployment:30,765 logical bytes;53,248 allocated bytes.
- Combined result-runtime/deployment roots:863,046 logical bytes;995,328 allocated bytes.
- Managed filesystem free observation:25,790,550,016 bytes; floor remains satisfied.
- Twelve conservative correction events of20; no consumption reset/refund.
-1,370 pre-existing private files, source/ADE/PDK and prior result/replay/admission
  integrity checked by exact hashes/fingerprints. No historical deletion, cleanup,
  optimization, numerical target, source mutation or publication.

Logical bytes, allocated blocks, filesystem free space and cumulative reservations
are distinct. These observations describe the approved roots/host at inspection;
they are not an inventory of every VM file.

## Distribution and next phase

Apache-2.0 covers original bridge code only. External Cadence/PDK terms and
existing LICENSE/NOTICE/THIRD_PARTY_NOTICES remain. Imported planning/export
boundary and LEGAL_REVIEW_REQUIRED remain; PUBLICATION_NOT_AUTHORIZED. No version,
tag, release, PyPI/MCPB publication or history rewrite.

Users can inspect empirical refinement of the preserved bandwidth result through
registered IDs and retrieve the same report after restart. Its scientific limits
remain visible, and partial bandwidth cannot produce specification PASS/FAIL.
Recommend **ANALOG-PM-01** to investigate a valid reference loop-gain method.
It is not activated by this completion. Report and ask once before proceeding.

## Verification checkpoints

Final focused science/operator/schema gate:112 PASS. Ruff and strict mypy52
source modules PASS; exact76-tool/old75/v1-v8 contract audit PASS. The first full
gate recorded1,892 PASS/two exact inventory failures/four OS skips/56 warnings
in540.91s. Only the two missing reviewed names were added to those explicit
allowlists; the initial failure log remains intact. The second full gate recorded1,893 PASS/one further explicit read-only inventory
failure/four OS skips/56 warnings in544.17s. After that exact list update,121
server/SSH/science/operator tests pass. Final full gate: **1,894 PASS, four OS
symlink SKIP, 56 warnings in539.63s**, exit0. The earlier two failed full runs
remain preserved. Final documentation review corrected a stale six-addition
app count to seven and the old export-phase current-status field; this is the
tenth conservative correction event, with no runtime or test change.
The first final-checkpoint comparison also detected the already recorded ninth
test-name inventory correction relative to its older manual checkpoint. That
comparison failure is preserved; exact diff review confirms only the new reviewed
name was added, and the final full run tested it. This verification correction
is the eleventh event. The twelfth corrects only the private comparison script's
expected indentation for those two names. Both initial comparison failures remain
recorded. Runtime and test identity remain exact; no test was waived.

Security/dependency gate:18 PASS, one non-fatal existing cache permission warning,
no known locked dependency vulnerabilities. Final secret preflight881 files.
Build/distribution inspection/isolated install/CLI/three SDK configuration formats/
uninstall PASS; final inspected wheel60/sdist61 members, canonical Apache license and all
three notices, zero unexpected/protected-pattern files. Final source/contract
identity and documentation/secret checks bind these completed gates to the
containing candidate; no runtime changes followed them. This does not claim
actual Codex or Claude application verification.
