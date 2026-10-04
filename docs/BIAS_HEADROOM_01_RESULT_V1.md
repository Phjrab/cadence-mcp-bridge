# Finite bias/headroom characterization and Spectre budget transition

Date: 2026-10-04. User-selected phase: `BIAS-HEADROOM-01`.
Outcome: finite characterization complete with significant corner tradeoffs.
Specification evaluation: `not_evaluated`.

## Actual results

The user raised cumulative Spectre attempts from 100 to **500**. The deployed
native-v2 adapter and MCP contract enforce that change with the existing ledger
and UUID replay domain. Consumption is retained: **48/500**, including sixteen
new computations in this phase. No elapsed ceiling is restored. Storage remains
5 GiB, with 128 MiB reserved per computation and all other budgets unchanged.

Only the proposed four pairs were applied in owned ADE state copies. Each is
within the observed saved/qualified endpoints, N300–320/P650–702 mV; those
endpoints are not a PDK absolute-rating claim. VDD=1 V, 27 C, input VCM=0.5 V,
existing topology, stimulus and load were checked against generated native inputs.
The original state remains 300/650 mV, NN, DC enabled. The user's 320/702 mV
candidate remains a comparison reference; no candidate is promoted to the source.

Headroom is `abs(vds) - abs(vdsat)`. A negative value is relative to the simulator's
saved saturation-voltage estimate. Vendor region codes are retained as numbers.

| Applied owned pair (mV) | FF negative devices | FF minimum (mV) | FS negative devices | FS minimum (mV) |
| --- | ---: | ---: | ---: | ---: |
| 320/702, preserved reference | 8 | -175.7839 | 8 | -307.8908 |
| 300/702 | 2 | -40.3084 | 8 | -300.1664 |
| 320/650 | 2 | -102.1884 | 8 | -251.2679 |
| 300/650 | 2 | -121.8437 | 8 | -225.9784 |
| 310/676 | 2 | -75.3283 | 8 | -278.2725 |

Each pair improves the ordered `(negative count, -minimum margin)` relative to
the preserved reference in both FF and FS. The predetermined worst-corner rank
selects **300/650 mV**: all candidates have eight worst-corner negative devices,
and this pair has the least-negative worst margin. Pair index resolves ties.
This is a physical screening rule, not a numerical specification or PASS target.

The selected pair then completed DC at NN/SS/SF and AC at all five sections.
Selected FF/FS DC results were reused. Every DC output differential is zero.
Each AC dataset contains 71 points, 10 Hz–100 MHz, ten points per decade.

| Section | Selected DC output CM (V) | Selected negative devices | Selected minimum (mV) | 320/702 reference AC gain at 10 Hz (V/V) | 300/650 AC gain at 10 Hz (V/V) |
| --- | ---: | ---: | ---: | ---: | ---: |
| NN | 0.07352685 | 2 | -124.7480 | 8863.354002 | 47.651360 |
| FF | 0.08292596 | 2 | -121.8437 | 3.731396 | 70.838560 |
| SS | 0.06430752 | 2 | -125.4863 | 1839.439201 | 28.545640 |
| FS | 0.59009370 | 8 | -225.9784 | 0.0692544 | 0.3232444 |
| SF | 0.08898083 | 2 | -164.7543 | 69.054660 | 25.997780 |

FF and FS low-frequency gain improve, while NN, SS and SF gain decrease greatly.
FS still has eight negative-headroom devices and gain below unity at 10 Hz.
NN loses the positive minimum margin observed at 320/702 mV. A criterion focused
on FF/FS does not establish a generally better operating point. These four pairs
provide no evidence of an all-corner solution. No performance goal, acceptable
common-mode window, statistical yield, temperature/supply domain, stability,
transient performance or complete PVT coverage is claimed.

## Reader failure, evidence repair and recovery

The first v1 FF computation completed Spectre and scalar extraction, but failed
verification because its new MOS frame was absent. Loading the earlier diagnostic
module inside extraction reloaded shared Python 2.6 guard modules and reset the
mutable job path. Consequently, the OP insertion extended the historical
`ade-qual-v6/extract.ocn` rather than the new job's script. The early commentary
that described a failure before simulation was corrected after inspecting stages
and the ledger. That computation remains counted, and its failed work tree is
preserved byte-for-byte and metadata-for-metadata.

Further submissions stopped. A one-shot repair verified that the changed script
was exactly the original qualified template plus the known 140-field insertion.
It preserved the changed bytes, reconstruction, intent and result in a new private
evidence directory before restoring the deterministic original script bytes.
The restored SHA-256 is
`e2e604960945ee9968216acd59f61c8461e5af75b844a0a4ea7db4166a29fd8c`.
Original script timestamps were not recovered or claimed unchanged. Therefore,
this phase does **not** claim that every historical artifact was untouched.
Original circuit/OA/ADE and PDK bytes, historical measurement results and PSF,
the three NN job trees, eight previous PVT job trees and diagnostic evidence
retain their protected checks.

The corrected v2 adapter uses a local inventory parser without runtime guard
reloading and checks job routing and write containment before managed writes.
The retired v1 local operator cannot submit another job. The remote v1 runner
also loses its execute permission after a journaled operation; its source
manifest still verifies and no source bytes are deleted. Both versions, policies,
manifests and failure records remain preserved. First-job recovery writes a new
`recovery-v2` evidence directory alongside the immutable failed work. It reads
the original PSF, verifies recovered scalar bytes equal the earlier scalar frame,
and extracts 140 OP values with no new Spectre computation. The original work
stage remains `verification_failed`; the recovery status and result succeed.
The other fifteen jobs complete normally. Correction consumption: **1/3**.
All previous correction histories remain unchanged; the budget adapter uses 0/3.

## Implementation, verification and resources

`scripts/spectre_limit.py` binds the explicit ceiling migration and managed
deployment. `scripts/verify_spectre_limit.py` verifies real subprocess stdio MCP
contract metadata, preserved DC/AC/TRAN result reuse, same-ID replay and rejection
of wrong-analysis status, with zero new simulations. The guest Python 2.6 guard
allows synthetic counters 100 and 499, denies 500 and storage exhaustion, rejects
boolean counters, and leaves the actual ledger unchanged during these checks.

`scripts/bias_headroom_v2.py` exposes only the finite private sixteen-slot operator
workflow, deployment, postflight, selection and first-job extraction recovery.
It reuses native state, circuit, model, DC, AC and warning guards. Four fixed
voltage pairs, five fixed sections, DC/AC, private UUID4s, exact policy bytes,
actual user delegation, request lineage and durable journals bound execution.
No generic runtime shell, SSH, SKILL, OCEAN, path or voltage tool is added. Existing
35 MCP tools retain their fixed NN 320/702 mV simulation settings; their active
native transport moves to v2 for the shared 500-attempt guard.

Shared EDA locking, disk floor, fixed job timeouts, duplicate tuple rejection,
16-attempt phase cap, uncertainty checks, reservation-before-computation and
no automatic simulation retry remain enforced. The final same-ID submission
returns success without changing any job tree or ledger. Recovery status succeeds
while the underlying failure evidence stays immutable. Each computation has zero
errors, two allowlisted CMI-2477 warnings and zero notices.

Independent arithmetic in `scripts/verify_bias_headroom.py` checks the preserved
scalar and OP frame bytes against result hashes, DC common-mode/differential
arithmetic, all **1540 OP fields**, all **355 complex AC gain/dB/phase points**,
and selection using the full preserved baseline values. Actual applied bias,
model section, VDD and protected-state checks pass before each calculation.

Final affected native/budget/plan/reader/PVT/security tests: **240 passed**.
Product and the new local operator/verifier/tests pass Ruff and strict mypy
for 31 files. An earlier full regression passed **982 tests**, skipped eight
opt-in remote integration tests and retained 56 existing deprecation warnings;
that full run preceded the later finite execution additions, which are covered
by the focused final checks and actual guest validation. Skips are not PASS.
All deployed manifests, Bash syntax and actual guest Python 2.6 compilation pass.
Dependencies are unchanged; PR #97's same-day frozen vulnerability audit is reused.
Secret preflight passes for 698 repository files; project state has 475 unique keys.
No guest OS/Python upgrade, destructive cleanup, chip order, payment or release.

Budget policy SHA-256:
`b534b0ade1d17c75cfa711911feca6b8625f2662dde91c621a60fb1fa43d9a8b`.
Native-v2 deployment manifest SHA-256:
`c80cef0b8786ce99dda32644329ee880098432ff0b19cbe33e90389f8d7a7697`.
Corrected bias policy SHA-256:
`c0d523480702efa8e04773b659f82683a11a95ec5f38d42a4b7fc1ab75f8626f`.
Corrected bias deployment manifest SHA-256:
`10ff6c1467c52e26a965296457e2a28ab6a0d3fd73f27abfc229838c4323e2dd`.

Final reserved result bytes: **5,235,539,968 / 5,368,709,120**.
Remaining reservation headroom: **127 MiB**, less than a single **128 MiB** job.
Thus there are 452 unused Spectre attempts but **zero further reservable jobs**
under the unchanged storage budget. Managed per-phase non-job evidence has a
separate 2 MiB allowance; it does not authorize reclaiming reservations.
New job trees occupy 4,830,919 bytes. Review postflight free space is
25,808,297,984 bytes on 62,382,514,176 bytes, above the 10%/2 GiB floor.
No active EDA worker or paid resource remains. Counters are not reset or reclaimed.

## Checkpoint and next phase

All private job requests, journals, bounded results, scalar/OP frames, independent
analysis, repair provenance, replay verification and final postflight are preserved
under the private local `.codex` state and the managed VM root. Feature code,
policies and reviewed numerical report are integrated through a dedicated feature
PR; the exact feature/merge SHAs and actual GitHub checks are recorded in the
private merge checkpoint, with no separate state-sync PR.

Ask once before a new major phase. A proposed next step is a bounded investigation
and plan for FS headroom using circuit topology/device sizing, including explicit
all-corner tradeoffs. It is not activated by this characterization. Any future
simulation also needs a user-selected storage-budget change or a newly approved
storage/reservation policy, because the present budget cannot reserve another job.
Targets are optional until a design decision needs them; none are invented here.
