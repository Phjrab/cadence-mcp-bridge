# Native fixed corner DC/AC qualification

Date: 2026-10-04. User-selected phase: `ADE-PVT-QUAL-01`.
Outcome: eight new native owned-state analyses completed and verified.
Specification evaluation: `not_evaluated`.

## Actual measurements

Each new owned ADE state contains 320/702 mV and exactly one of the actual
FF/SS/FS/SF model sections. VDD=1.0 V, temperature=27 C, input VCM=0.5 V,
the existing topology, no added external load and the original stimulus are
verified by the generated native input and protected source/copy signature.
The original saved state remains 300/650 mV, NN, 27 C with DC enabled.
The NN row reuses PR #96's preserved native MCP results without simulation.

| Actual section | DC output common mode (V) | DC output differential (V) | Differential AC gain at 10 Hz (V/V) | Gain at 10 Hz (dB) |
| --- | ---: | ---: | ---: | ---: |
| NN, reused | 0.2277073 | 0 | 8863.354002 | 78.95196 |
| FF | 0.6819519 | 0 | 3.731396 | 11.43743 |
| SS | 0.1503440 | 0 | 1839.439201 | 65.29371 |
| FS | 0.6081144 | 0 | 0.0692544 | -23.19105 |
| SF | 0.1035445 | 0 | 69.054660 | 36.78386 |

Each AC result has 71 points from 10 Hz to 100 MHz, ten points per decade.
Gain is `(Vop - Vom)/(Vp - Vm)` at each sampled frequency; the AC differential
excitation magnitude is verified as 1 V. These are deterministic model-section
observations at one fixed temperature, supply, bias pair and topology. There
is no numerical specification, statistical distribution, yield, temperature
domain, full PVT sweep, corner ordering or worst-case coverage claim.
In particular FS has gain below unity at 10 Hz. Successful execution does not
qualify the candidate's design performance. MOS operating-region causes of the
large corner differences remain uninvestigated in this phase.

## Implementation and provenance

`scripts/ade_pvt_qual.py` provides only fixed deploy/postflight actions and
indexed submission/status/result operations for eight privately pinned UUID4
requests. A separate versioned Python 2.6/Bash adapter loads the qualified
candidate/DC/AC readers and guards without changing their archived source.
There is no new public shell, OCEAN, SKILL, path or model execution surface;
the existing 35 MCP tools and their NN execution contracts remain unchanged.

Original state facts and effective owned settings are retained separately.
The guard permits only the two qualified bias expressions, the owned modelSetup
section and the existing job routing difference. Other saved state files are
byte-checked. Before simulation, the actual generated include must select the
requested section from the bound model file. Only that proved include selection
is normalized in memory to reuse the original NN semantic validator; the actual
netlist is never rewritten. Existing supply, temperature, circuit, analysis,
stimulus and source-copy checks still run. Input, owned state, measurement frame
and PSF fingerprints remain in private results.

The nine-file PDK inventory is pinned to the original private manifest bytes,
SHA-256 `4a1fda45bb3738fc7253429903aee30b9c65f40439aee28f6cf22047178fd0d0`.
Every file's byte count and SHA-256 are checked before and after each run.
The three original native MCP job trees and all prior native reference results
are also pinned and unchanged. No PDK statements, coefficients, model identifiers,
OA/ADE source, netlists, raw PSF or unrestricted logs are published.

Shared EDA locking permits one worker. Durable request and reservation records
precede side effects; each corner/analysis pair can be claimed only once.
Same-ID replay returns the preserved state and never reruns a successful,
failed or uncertain stage. New IDs cannot repeat an existing pair. Any shared
ledger change outside the phase, duplicate pair, wrong request identity,
unexpected warning, incomplete reader, protected drift or exhausted budget
stops execution with evidence retained. Fixed per-operation timeouts remain;
the removed campaign elapsed ceiling is not restored.

All eight Spectre runs have zero errors, the same two allowlisted CMI-2477
warnings and zero notices. Native DC/AC selectors and extraction succeeded.
The actual non-NN native Spectre/OCEAN path is therefore observed working.
ADE XL batch-corner and Monte Carlo licensing/effective variation remain
unqualified. No highPerf, temperature/supply sweep, Monte Carlo, optimization,
TRAN rerun, source promotion, system upgrade or destructive cleanup occurred.

## Verification and resources

Focused corner, candidate, native AC/TRAN and security checks: 134 passed,
including 38 new corner checks. Product source plus the new operator/test pass
strict mypy (23 source files); Ruff passes. An exploratory strict check of all
legacy test modules reports 108 existing errors in 21 unchanged test files,
outside the established product-source type gate; they are not suppressed or
claimed passing.

Eight private measurement frames were independently checked using DC arithmetic
and complex AC gain, dB and phase calculations, covering all 284 new AC points.
Same-ID submission consumes no further attempt and wrong-corner status is
rejected. Actual guest Python 2.6 compilation, Bash syntax and exact deployment
manifests pass. Final secret preflight passed for 649 repository files. The
unchanged dependency lock reuses PR #97's same-day frozen vulnerability audit;
no dependencies are changed in this phase. Full regression exercised 896 local
tests: 895 passed initially and one existing campaign-authority test failed
because the invocation omitted this worktree's required Git safe.directory
environment. Its preserved log reports `repository remote mismatch`. The sole
failure passed both its isolated rerun and the full suite's `--lf` rerun with
that environment restored; no production guard or test was relaxed. Eight
opt-in remote integration cases are skipped, not claimed passing. The 56
existing deprecation warnings remain. No second simulation was needed for
test-harness or arithmetic verification.

Policy SHA-256:
`9f84e8c1806079cafe6e316e4aa8ac06e2e455720de89756a02a75bb47873713`.
Deployment manifest SHA-256:
`1d8c85b03c19a16c5372fdf729c75feac9ddedcfe4dc4444689f0e1cfa0897e7`.
Original remote JSON bytes and locally canonicalized result hashes are kept
distinct. Only frame bytes are compared directly across runtimes. State
metadata has 444 unique keys; all deployed source hashes match the policy.

New Spectre attempts: 8/8. Shared cumulative use: 32/100, with
3,088,056,320 reserved result bytes under 5 GiB. New job files occupy
2,335,417 bytes; including the 27,272-byte immutable deployment gives
2,362,689 bytes. Free space remains approximately
25.82 GB on a 62.38 GB filesystem, above the greater-of-2-GiB-or-10% floor.
Active EDA is zero and paid resources are zero. This new change consumed zero
deployment corrections; prior counters remain DC5/6, native AC/TRAN3/3,
candidate1/3, native MCP1/3 and PVT preparation3/3.

The phase stops after reviewed feature PR integration and its report.
Proposed next phase: `ADE-PVT-DIAG-01`, a bounded examination of preserved
device operating points to explain the FF/FS gain collapse before any new
bias range or statistical execution. It requires the user's next phase choice.
