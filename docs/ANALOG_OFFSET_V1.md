# ANALOG-OFFSET-01 — selected nominal input-nulling study

Starting main `09339c48c692f6e00e53b36adc725516b54b4daf`; branch
`feat/analog-offset-01`. The user selects input-referred offset and authorizes
OFFSET → BIAS-RANGE-QUAL-01 → REAL-AMPLIFIER-SWEEP-01 → SPEC-REAL-EVAL-01
continuously, retaining each phase's gates and reviewed PR integration.

## Selected definition and evidence

Applied **Vp−Vm where Vop−Vom=0**, nominal open-loop, NN/27 C/VDD1 V,
VCM0.5 V, effective bias320/702 mV, existing topology without added external
load. The sign is the applied nulling input, never automatically negated.
Original saved300/650 mV is unchanged. No mismatch, Monte Carlo, statistical,
closed-loop, PVT-wide or device electrical-rating qualification is established.
The user has supplied no numerical specification target.

Five fixed cases were selected before observation: preserved admitted zero-input
DC PSF (high-precision scalar extraction only), then−1,+1,−0.5,+0.5 microV in
four owned DC copies. Effective common mode/rail/input, reversed source input
hash, simulation quality, complete receipts and protected checkpoints are checked.
Each new simulation shares the existing EDA lock/disk guard/ledger and128 MiB
cumulative reservation; no replay or old accounting is reset.

The unique linear bracket yields coarse−2.2672600779374006e−15 V and
fine−2.2670260850857216e−15 V. Fine containing bracket is
[-5.000000000143778e−7,0] V; root-pair difference2.3399285167900047e−19 V.
Coarse/fine local gains8864.667560/8865.582253 V/V differ0.01031735%.
These are algorithm diagnostics. **The tiny result is numerical residual
consistent with nominal zero, not femtovolt physical precision.** No absolute
error bound, solver-tolerance convergence or mismatch qualification is supplied.
Fixed±0.1 V local output/headroom checks are not MOS-region proof.

Supplemental study is **PARTIALLY_QUALIFIED**. Original generic offset-v1 remains
**UNQUALIFIED/null**. This study cannot generate specification PASS/FAIL.

## Bounded API and compatibility

One additive read-only `cadence_offset_study_result`,78 source MCP tools with
all77 old complete schemas and registry v1-v8 exact. Use the registered
`analog-offset` design/contract hash and original admitted DC operation ID.
The tool checks original analysis/measurement/PDK/admission, source input/PSF,
five complete receipt digest and selected definition hash. It returns fixed
scalars, brackets, conditions, counters, provenance and explicit warnings;
no caller range/path/expression/script/PSF/vector or execution input.

`offset-qual-v1` is immutable operator qualification, not a new sweep engine.
Its strict72-attempt phase conservation remains intact. A separate immutable
`offset-read-v1` reader permits bounded future ledger advancement and validated
new native job IDs while preserving every previous job and protected fact.
It checks historical markers, all result bytes, effective substitutions,
original source and concurrent ledger stability. Existing temporal verifiers
are not monkeypatched. Historical zero extraction consumes no new reservation.

## Evidence and verification

Actual Spectre: four DC runs; bounded OCEAN: five scalar frames. Current-source
SDK stdio checks78 full schemas, preserved DC/AC/TRAN/power/bandwidth/slew/sweep,
new offset and process restart, unchanged admissions and1,652 prior private
hashes. Actual Codex runtime-info-v2 reports builtin registryv4; the new Offset
tool is not exposed in this active app session. SDK PASS is not actual app E2E.
Claude remains deferred/CLAUDE_REAL_CLIENT_UNVERIFIED; historical PR127 evidence
is retained. Full/static/security/package results are in the phase result report.

Phase usage:4 attempts/536,870,912 reserved bytes. Cumulative72/500 and
8,456,765,440/10,737,418,240 reserved bytes. Five job directories use660,771
logical/929,792 allocated bytes. Reservations are not occupancy and not refunded.
All original OA/ADE/PDK/native/sizing/bandwidth/slew/jobs/replay/evidence remain
protected. Apache covers original bridge code only; import rights remain
LEGAL_REVIEW_REQUIRED, PUBLICATION_NOT_AUTHORIZED. No deletion/release/tag.

## Preserved initial failures

The first conservation guard rejected Windows CRLF in a historical slew OCEAN
checkout before remote action. Exact Git blob was restored and scoped LF
attributes prevent recurrence; historical source/policy bytes stay unchanged.
Initial lint/type/fixture/private-baseline-bound and optional registry-metadata
lookup failures are retained. None authorizes replaying successful simulations.
The first full collection used a console import path missing `scripts`; the
canonical `python -m pytest` invocation restores repository namespace discovery.
Old hardcoded inventory counts require explicit additive-snapshot updates,
never waived tests. Scientific selection is no longer pending.

## Final gate checkpoint

2,073 full unit PASS/four OS symlink SKIP/56 warnings in546.75s; focused119
and SSH32 PASS; Ruff/mypy56/exact78 old77/v1-v8 contracts PASS. Security18
PASS/one existing cache warning, locked audit no known vulnerabilities,945-file
secret scan PASS. Wheel64/sdist65 notices/source/protected-content/isolated78
three SDK formats/CLI/uninstall PASS. Changed Markdown94 links/balanced fences
PASS. Exact containing-PR primary review and permitted merge/remote SHA/tree
verification recorded privately; independent review/CI are not inferred from
local checks. No publication or deletion.
