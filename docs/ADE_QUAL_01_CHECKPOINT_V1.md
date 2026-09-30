# ADE-QUAL-01 — native ADE qualification checkpoint

Date: 2026-09-30. Outcome: `BLOCKED_MODIFICATION_BUDGET`.
This phase is incomplete. No current-state netlist, simulation, extraction or
scientific baseline is qualified. A draft feature PR preserves the implementation
and reviewed failure evidence; it must not be merged as a completed capability.

## Scope and observed facts

The user selected current source/ADE state netlisting and analysis validation.
The first bundle was limited to the saved state's only enabled analysis, DC,
with NN and 27 C. The state files currently contain VBIASN=0.300 V and
VBIASP=0.650 V. These are observed settings, not demonstrated effective inputs
of a newly generated netlist. The 320/702 mV user candidate remains separate;
VDD=1.0 V remains the constraint. No numerical performance target is invented;
`spec_evaluation=not_evaluated`.

The existing verified OA copy was reused. Native read-only signatures compared
source and copy instances, properties, connections, nets and terminals. The
saved state was copied into each owned job; only design identity and project
routing were remapped there. The original state and source were never saved.
The postflight pinned guard verified unchanged original source, ADE tree, model,
copy and historical netlist/project fingerprints. Raw ADE, netlists, PDK, PSF,
logs and private identities remain private.

## Execution evidence

| Immutable deployment | Actual outcome | New Spectre attempts |
| --- | --- | --- |
| ade-qual-v1 | Preflight rejected a differently spelled path to the same model; no job created | 0 |
| ade-qual-v2 | Owned state comparison encountered an empty waveform directory; failed before native execution | 0 |
| ade-qual-v3 | Headless OCEAN confirmed source/copy signatures, but native load returned ADE-5049: no ADE window attached | 0 |
| ade-qual-v4 | VM display was available. Virtuoso confirmed source/copy signatures, then session creation raised a list/type error; state load and netlist markers were absent | 0 |

Three corrections after the first deployment used the existing ceiling of three
modifications of the same code change. No fourth correction, journal reset,
duplicate simulation, deletion or broader phase was attempted. Failed deployments,
job directories and local reservations remain preserved.

The cumulative ledger remains 14/100 Spectre attempts and 672,137,216 reserved
result bytes under the 5 GiB ceiling. There were zero active EDA processes after
the last exit. Free space was 24.06 GiB, above the existing disk floor. The removed
elapsed ceiling was not reinstated. Paid resource usage remains zero.

## APIs and remaining qualification gaps

Installed IC6.1.5 documentation confirms OCEAN `createNetlist`, ASI `asiLoadState`,
and SEV `sevStartSession`, `sevSession`, `sevNetlistFile` and `sevQuit`.
`asiLoadState` documentation describes a CIW/ADE simulation environment.
Its presence does not establish headless support; the v3 execution disproved the
chosen headless route. `asiNetlist` is documented as an environment method that
should not be called directly, so it was not used as a workaround. OCEAN
`restore` is a simulator operating-state function, not an ADE-state loader.

The immediate resume work is to verify the accepted `sevStartSession` design
argument and session/window association using an owned, fixed probe. V4 passed
an OA database handle; the actual API rejected that call with a list/type error.
No undocumented replacement is claimed to work. Also resolve graphical CIW
marker capture: V4 wrote markers to its job-owned log, whereas the current
completion parser reads stdout. Neither echoed script text nor a process exit
code may substitute for a real success marker.

After these prerequisites, qualify the native input's exact include layout,
single DC analysis, model section, temperature, effective variables, VDD/input
bindings and circuit equivalence before reserving any Spectre attempt. Only
then run one DC and qualify the native PSF result selector and scalar extraction.
Existing candidate/snapshot DC/AC results remain available through their earlier
MCP tools; they are not evidence of a successful current-state run.

No current-state AC/TRAN, Noise/STB, corner run or Monte Carlo was executed.
The model's declared section names were inspected, but declaration alone does
not qualify corners. Main-file statistics search cannot establish statistics
support or absence across the included model hierarchy.

## Resume checkpoint

Private checkpoint: `.codex/ade-qual-01-checkpoint.json`.
SHA-256: `74ff35ae46cf6434464e791b68435ebefc2282cf39f99be9acd19488db3183b6`.
The checkpoint includes per-version outcomes, final stage, fresh protected
fingerprints, observed state settings, disk facts and the unchanged ledger.
`scripts/ade_qual.py status` is a fixed read-only reconciliation operation.
`deploy`, `netlist` and `dc` remain one-shot operations with predecessor,
authority, integrity and replay guards; preserved reservations must not be reset.

Resume requires a specifically bounded renewal of the consumed correction
allowance. Keep every other resource/protection limit. Continue ADE-QUAL-01
from this checkpoint; do not start another major phase or repeat completed WPs.

Local tests cover numeric/include/circuit rejection, owned-state routing and
directory comparison, protected drift, strict cumulative counters, replay,
crash-before-counter-update, partial-failure status and operator dependencies.
Their success is implementation evidence, not native ADE qualification.

Validation: 29 focused tests passed. The final full regression run had 692
passes, 8 integration skips and 56 existing legacy-helper deprecation warnings
in 634.11 seconds. The skipped tests require the separate integration flag;
they are not reported as remote E2E passes. Ruff across src/scripts/tests,
mypy for src and the focused tests, repository secret preflight, policy-byte
binding and Git whitespace checks passed. Remote deployment also passed Bash
syntax and installed Python 2.6 compilation. Dependencies were unchanged.
