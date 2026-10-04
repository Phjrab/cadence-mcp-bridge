# Actual PDK PVT and statistics preparation

Date: 2026-10-04. User-selected phase: `ADE-PVT-PREP-01`.
Outcome: protected model/support inventory completed; no new circuit execution.
Specification evaluation remains `not_evaluated`.

## Observed support and limits

The bound gpdk090 v4.6 Spectre model tree contains nine inventoried `.scs`/`.mdl`
files, totaling 427,717 bytes. The argument-free operator follows actual include
and section selections, rejects escapes/symlinks/missing selections, and compares
every inventoried file before and after. It preserves the exact case of section
names. Section availability is distinct from simulator qualification or a design
specification result.

| Item | Actual observation | Qualification limit |
| --- | --- | --- |
| Base model sections | `NN`, `FF`, `SS`, `FS`, `SF` | Only the existing `NN`, 27 C native DC/AC/TRAN evidence is executed; other corners are not run |
| Additional model sections | `NN_highPerf`, `FF_highPerf`, `SS_highPerf`, `FS_highPerf`, `SF_highPerf` | Definitions are present; no substitution, equivalence, performance or execution claim |
| Current MOS binding | Both actual circuit model identifiers have exactly one reachable definition in each section, covering eight NMOS and six PMOS instances | Identifiers are returned only as opaque digests; model coefficients and statements stay private |
| Statistics in each reachable section graph | Five `statistics` blocks, five `mismatch` blocks, seven `vary` declarations with lexical references | Direct references to those variation names inside the two matched definition spans are zero; indirect/device binding and effective variation remain unverified |
| Process statistics | Zero `process` blocks in the ten selected include graphs | No process-only or process-plus-mismatch statistical execution is enabled |
| Spectre installed support | `spectre -h montecarlo` exits zero; mentions `variations`, `process`, `mismatch`, `seed`, `numruns` | Help support does not prove a successful Monte Carlo model binding, runtime checkout, PRNG behavior or sample execution |
| OCEAN installed support | All nine fixed APIs are callable; OCEAN exits zero | Callable APIs do not establish ADE XL/corner/Monte Carlo license entitlement or execution success |

The fixed APIs are `modelFile`, `temp`, `desVar`, `monteCarlo`, `monteRun`,
`ocnSetXLMode`, `ocnxlCorner`, `ocnxlMonteCarloOptions`, and `ocnxlRun`. The
probe calls only `isCallable`; it never calls these execution/state APIs.
No new MCP tools or actual profile corners are activated; the registry remains
at 35 tools with its existing qualified fixed workflow.

The original saved state still has 300/650 mV, `NN`, 27 C and DC enabled.
Prior native owned candidate evidence at 320/702 mV is reused without rerunning
DC, AC or TRAN. VDD=1.0 V remains a hard constraint; prior verified VCM=0.5 V,
topology/load/stimulus and revision bindings must be rechecked by any future run.
This phase applies neither a bias nor a model section. A valid temperature domain
or new voltage interval has not been established; no temperature or VDD sweep is
proposed by analogy. Model corners are discrete PDK-defined selections, not an
observed continuous process distribution or measured worst-corner ordering.

## Implementation, corrections and protected evidence

`scripts/ade_pvt_prep.py` is an operator entry point with finite actions and no
caller path, script, signal or model argument. Its policy is bound to a private
current-task delegation, exact deployed bytes, the existing campaign, correction
history and completed native reference. A durable reservation precedes deployment
or inventory. Repeating a read cannot rerun the inventory; status reads only the
fixed saved result and is bounded to three communication attempts. The remote
runner verifies manifests, checks for active EDA and uses the existing shared
lock. Cadence/system/PDK files remain read-only, with new files confined to the
managed root. No system or Python upgrade is performed.

V1 successfully inventoried sections and installed support. Three corrections
were consumed under the same phase, with all versions and journals preserved:

1. V2 recognized inline definitions, added actual MOS model binding, and prevented
   duplicate counting of common blocks included through multiple selected sections.
   It stopped at the MOS check: the actual preserved OA instance prefixes are
   `NM`/`PM` with counts 8/6, rather than a generic `M` prefix.
2. V3 used those exact existing prefixes. Its read-only diagnosis proved model
   bindings but found a cross-runtime canonical JSON digest disagreement.
3. V4 pins original remote result bytes. Python 2.6 and the local JSON serializer
   produce different numeric text despite parsed equality. A fixed protected read
   proved that equality and retained both the remote bytes and local canonical
   digest. V4 then completed and verified all ten section graphs.

No interrupted inventory was replayed. V2/V3 runtimes and reserved read journals
remain evidence of unsuccessful completion. The two fixed diagnostic reads
performed no EDA or runtime writes; only interpreter cache under the managed
installation may be created. Successful V1 help/API evidence is reused by V4.
All three correction allowances are consumed; this change has no further automatic
correction deployment allowance. Prior DC/native AC/TRAN/candidate/native MCP
counters are preserved.

## Resources and validation

New circuit runs: zero. The shared Spectre ledger remains 24/100, with
2,014,314,496 reserved bytes under 5 GiB. Final preparation artifacts including
the four immutable deployments occupy 117,925 bytes, separately checked against
remaining result headroom. Disk free space is 25,826,234,368 bytes above the
greater-of-2-GiB-or-10% floor. Final active EDA count is zero and paid resources
are zero. The removed elapsed ceiling remains removed.

Remote deployment verified exact source manifests, real Bash syntax and Python
2.6 compilation. Local focused inventory/security tests passed 41 checks;
strict mypy passed for 22 source files. The tests cover selected include closure,
inline definitions, duplicate common statistics, unsafe/missing includes,
actual-prefix counts, metadata disclosure, caller argument rejection, explicit
authority, wrong deployment digest, durable replay and communication exhaustion.
Final full regression passed 858 tests with eight opt-in remote integration skips
and 56 existing deprecation warnings. Skips are not PASS. The first harness run
failed eight unchanged legacy fake-process transport cases; its log is preserved.
One isolated positive case passed in the approved process environment, and the
full final suite passed there using a shorter workspace temporary root. No legacy
deployer or recovery production code was changed to relax those checks.

Ruff and strict mypy passed; the secret preflight passed for 640 repository files.
The initial frozen dependency audit found one PyJWT and three urllib3 advisories
(`PYSEC-2026-4141`, `PYSEC-2026-4177`, `PYSEC-2026-4176`, `PYSEC-2026-4175`). The
Windows lockfile and environment now use PyJWT 2.15.1 and urllib3 2.8.0; only these
two package versions changed. The final frozen audit reports no known vulnerabilities.
Guest Python/Cadence/PDK remain untouched. An actual subprocess stdio client after
the dependency update verified all 35 tools and the existing native contract list,
with zero simulation submissions. A live saved-inventory result read passed the
strict bounded projection and matched the preserved local V4 result exactly.
Unique state keys, all four immutable source manifests and `git diff --check` passed.

Main model SHA-256:
`029bf5a0767bedf2ca91301035ad2ad6e354663123402545a1a2d73b99986f8f`.
Nine-file inventory digest:
`f0a77b602f49fd0686f0d75f66607d7ecec3ffb39ab769f31f46666b940e350b`.
Final remote policy digest:
`09a28e2be1d6acd84133111b96501516b6599528fff3519a064ce5846846e5f0`.
Final source manifest digest:
`41933f899b2b65b1b23e049454c1f9a7d9058f0259f75f96dfb0a43e3ff6157f`.
Local canonical V4 result digest:
`c7ff032924f5a31474b5f7a0259cb4b58161842828f29f02d22bef89a218044d`.
Preserved remote V1 result byte digest:
`64d0f5f74ff1627897b07d1630c9c832e476e6b8019a3d8b059d92f930930472`.
That byte digest and the local V1 canonical digest identify different serialized
representations of the same checked metadata; they are not interchangeable.

Private `.codex/ade-pvt-prep-v4-result.json`, journals, correction records,
diagnostic evidence and postflight are excluded from Git. PDK source, model
coefficients, native netlist, raw results and help/OCEAN logs are not published.
The report publishes reviewed support/count metadata and opaque provenance only.
No state-sync-only PR is created.

## Minimal next qualification plan (proposed, not executed)

Proposed next phase: `ADE-PVT-QUAL-01`, discrete process-corner qualification of
the existing native candidate at fixed VDD=1.0 V and 27 C. Reuse preserved `NN`
DC/AC evidence and qualify `FF`, `SS`, `FS`, `SF` through native owned-state
copies. Recheck source/state/circuit/load/stimulus fingerprints and validate the
effective generated include section before each run. Change only the owned model
selection and the already qualified analysis/candidate settings. New temperature
or supply ranges, highPerf activation and optimization are excluded from this
minimal proposal.

Reserve at most eight new Spectre attempts (four sections times DC/AC), at most
eight existing 128 MiB result reservations, concurrency one, and the existing
cumulative ceilings. This would reach at most 32/100 attempts and 3,088,056,320
reserved bytes, before any separately accounted preparation metadata. Netlisting,
simulation and extraction must have independent status and immutable operation
IDs; a communication/extraction failure must not rerun a completed simulation.
Use qualified readers and report observed DC/AC differences without inventing
design targets, corner ranking or PASS for unexecuted cases. A warning outside
the existing allowlist, unsupported model binding or license failure is a precise
checkpoint, not a successful corner.

Monte Carlo remains a later gated capability. First verify that the actual used
MOS definitions receive nonzero effective mismatch variation, pin the installed
seed/PRNG and supported variation mode, and define bounded sample/replay contracts.
A small seed reproducibility/variation diagnostic would qualify infrastructure,
not estimate yield or claim a confidence interval. Process statistics are not
enabled while no corresponding process definitions have been observed.

Ask once before the proposed next major phase and stop. Recommended model/effort:
GPT-6.1 Sol, high. Exact proposed start prompt:

> ADE-PVT-QUAL-01을 승인한다. 보존된 NN 결과를 재사용하고 실제 FF/SS/FS/SF의
> native DC/AC만 작업 복사본에서 검증하라. 320/702 mV 후보, VDD 1 V, 27 C,
> 기존 VCM·부하·자극·revision과 누적 예산을 유지하고 새 시도는 최대 8회로
> 제한하라. 유효 model section·측정·provenance를 검증하고 수치 목표나 미실행
> corner PASS를 만들지 마라. 필요한 구현·시험·관리영역 배포·feature PR 검토·
> 병합은 단계 안에서 자율 진행하라. 온도/전원 sweep·highPerf·Monte Carlo는
> 시작하지 말고, 단계 끝에 다음 단계 진행 여부를 한 번 묻고 멈춰라.
