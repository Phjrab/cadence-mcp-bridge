# Explicit user candidates: bounded follow-up proposal

This document proposes a later implementation and qualification slice. It does
not describe an implemented candidate API, authorize an experiment, or make the
2.1.0 release depend on new W/L functionality. The release of already qualified
features and this candidate feature have separate acceptance decisions.

The target remains the professor-provided standard VM and its existing PDK.
There is no automatic search, candidate generation, multidimensional native
sweep, layout generation, or DRC/LVS/PEX prerequisite.

## Existing implementation and evidence

| Existing component | Reuse | Limit that remains binding |
| --- | --- | --- |
| `operator_operations.prepare_plan` | Full registered variable vector, numeric/unit checks, immutable plan and grant binding | Every allowed variable is explicit; registration is not execution permission |
| `NativeOperationService` and `OperatorLifecycle` | Existing plan, submit, reconcile and verified result lifecycle | Existing domain, journal, replay, locks, confirmation and cumulative accounting |
| `NativeSweepSupervisor` | Reference for bounded sequential coordination and persistent child identities | Current implementation is one explicit axis; it is not a mixed-candidate API |
| `AuthenticatedOperatorProvider` | Effective-input, reader, extraction and terminal receipt provenance | Candidate-provided hashes cannot replace independent effective-input checks |
| `result_reports` | Retained successful reports, metric definitions and artifact identities | `compare` remains an unchanged same-input reproducibility comparison |
| `generic_analog.capture_offset` | Example of allowing only declared input differences while retaining each complete source report | Its scientific definition and two input variables do not become a generic comparison contract |
| `m2_inverter` | Observed single-finger CDF selection, owned generation/readback and independent netlist verification | Current generator preserves observed dimensions; it provides no user W/L override |

V and A are accepted numeric-contract units. This alone does not qualify an
arbitrary voltage or current source, its binding, or an electrical range. The
retained owned-inverter execution registration fixes its one voltage variable;
it cannot be silently widened into a candidate range. No general current-source
candidate execution is established by those inverter results.

Actual M2 evidence establishes a narrow observed MOS form: one finger, equal
`w` and `fw`, `simW` referring to `fw`, and `simM` referring to multiplicity times
finger count. It does not establish `nf` semantics, PDK-wide bounds, legal grids,
callback behavior, or dimension changes. The synthetic `schematic_plan` fixture
has length units and invented ranges; neither is production PDK evidence.
See [M2 acceptance](M2_OWNED_INVERTER_ACCEPTANCE_20261015.md) and
[experimental analog qualification](POST_07_GENERIC_ANALOG.md).

## Minimum separate contract

Add an operator-only candidate module rather than changing existing public MCP
schemas or weakening existing comparisons. One batch has one registered analysis
and at most sixteen explicitly supplied candidates. DC, AC and TRAN use separate
batches with separately fixed analysis conditions. These are sequential single
operations, not a multidimensional native sweep.

An immutable batch manifest must include:

- Batch identity, schema version, baseline candidate ID and ordered candidate
  IDs, with bounded user labels kept separate from identifiers.
- Source design and testbench revision identities, parent/source-baseline binding,
  source and ADE-state evidence references, and fixed PDK/model identities.
- Declared variable differences by logical ID and their registered ADE binding,
  with the exact source/device instances affected. Any future device-property
  difference also requires its exact hierarchical instance ID, registered master
  and CDF property; a display label is not an instance binding.
- One complete `OperationRequest` per candidate, including every registered
  variable, its original supplied unit/value and canonical numeric value.
- Fixed analysis, temperature, corner/model selection, supply constraints, load,
  stimulus and measurement definitions. Their registered evidence is authoritative;
  descriptive labels do not attest these conditions.
- Candidate count, expected execution count, each result reservation, the aggregate
  reservation, and an explicit initial `halt_all` failure policy.

The initial implementation should reject partial overrides. A later convenience
form may expand overrides only against an explicitly identified immutable baseline;
the resulting full manifest must be displayed and hash-bound before admission.
No missing value may inherit a saved ADE value or a preceding candidate's input.

Planning calls the existing `prepare_plan` for every complete request. It remains
local and does not mint a grant, reserve capacity, initialize a replacement ledger,
or dispatch. Total cost must fit both the exact approved batch and existing grant
and environmental ceilings; displayed global capacity is not an execution grant.

## Sequential execution and restart

Fix a distinct existing-format operation ID for every candidate before dispatch,
and persist the immutable batch-to-child mapping exclusively. Reuse the existing
native lifecycle and analysis journal for child state, receipts and spending;
the batch manifest is not a new accounting authority. A crash during publication
must leave recoverable evidence without publishing an incomplete batch.

Batch submission or same-ID retry only admits or looks up the same manifest.
An explicit advance may submit at most one untouched child after reconciling all
earlier children. An altered manifest, different child plan, or changed authority
must reject instead of replacing a retained identity. Reopening a batch never
automatically dispatches its next candidate.

`UNKNOWN_OUTCOME`, any nonterminal running state, extraction failure, authority
failure, safety failure or input inconsistency stops further admission. A
transport exception is not permission to resend. The first implementation stops
on any execution failure and retains all rows. Continuing after a proven isolated
convergence failure requires a later authenticated failure-classification contract;
the current generic `FAILED` phase is insufficient to infer that classification.

## Independent candidate comparison

Add a distinct comparison function and result schema. Preserve
`result_reports.compare` and its current rejection of differing inputs.

For voltage/current candidates on the same registered source revision, require
all original report conditions to match except the prospectively declared variable
values and the necessarily different effective-input digest. Verify each candidate's
complete vector against its saved plan. Keep every effective-input digest in its
own row; removing it from the common-condition calculation never discards it.

For W/L candidates, revision/source/static/reader identities can also differ.
Do not globally ignore those differences. Require a validated revision chain and
an exact change record binding the approved instance/property edits to independent
readback and effective netlist evidence. Compare unchanged topology, model closure,
testbench, stimulus, load, analysis and measurement semantics exactly. The reader's
whole registration hash includes its ADE registration, so matching measurement
meaning needs a narrowly defined semantic contract while retaining each original
registration hash. A new candidate-derived hash is not that proof.

Produce one row for every declared candidate, including condition mismatch,
`NOT_RUN`, interrupted/unknown, execution failure, extraction failure and success.
Missing measurements remain null with a reason. Each row retains requested and
independently verified effective values, verification status, unit-bearing metrics,
baseline differences, errors and operation/plan/input/netlist/reader/frame/receipt
artifact identities. A failed or unverified row cannot acquire measured values
from the baseline. Relative change against a zero or unavailable baseline is null
with an explicit reason; a valid absolute change may still be shown.

CSV uses UTF-8 with BOM and standard quoting. Treat labels and other user-supplied
text as untrusted spreadsheet cells: neutralize formula prefixes, including those
preceded by whitespace/control characters. Quoting a CSV cell alone does not stop
formula interpretation. Preserve the original label in the structured report and
document the export escaping. Numeric metrics remain typed numbers with their units.

Waveforms may be exported only from retained authenticated AC/TRAN sample data
through the existing bounded reader path. Scalar reports cannot manufacture a
waveform. Preserve axes, node identities and phase definition; differing grids
must be marked as unaligned unless an explicit validated alignment method is
selected. Do not silently interpolate, call ordinary AC phase phase margin, or
call a sample-derived slope intrinsic slew rate.

## W/L binding work and evidence still needed

Keep raw requested length/unit and an exact Decimal-based SI normalization, with
explicit supported units such as m, um and nm. Reject unknown units, nonpositive
sizes, expressions and ambiguous suffixes. Any addition to general variable units
needs schema/compatibility review; a length input field alone adds no execution
support.

The retained CDF frame records parameter names, types, units, defaults/effective
values and selected Spectre descriptors. It does not record callback definitions,
allowed ranges or legal grids. Absence from that frame is not evidence that a
callback or restriction is absent. Before a dimension-changing writer is enabled:

1. Reuse authenticated retained observations where sufficient, then identify only
   the missing bounded read-only metadata for the exact registered device family.
   New remote reads or an EDA startup need their own valid scope; this proposal
   grants neither. No broad PDK traversal or license query is needed.
2. Bind exact PDK/master/instance/property meanings and operator-reviewed legal
   values or ranges/grid. Resolve `w` versus `fw`, multiplicity/finger behavior and
   derived areas/perimeters. Unknown `nf`, callback or derived-size behavior rejects.
3. Create a fresh owned candidate revision, leaving the original and failed
   revisions intact. Define its creation/partial-failure recovery and never reuse
   a failed revision as a fresh candidate.
4. Independently check requested properties before save, after reopen, through
   effective CDF readback, and in the generated netlist. Verify unchanged models,
   connectivity, load and stimuli. Do not use text substitution or only a hash of
   the candidate as evidence of effective dimensions.
5. Qualify baseline, bias-only, W/L-only and mixed candidates within one observed
   circuit/device family, using identical package/templates and explicit full
   inputs. Report execution/extraction separately from scientific performance.

If retained evidence cannot supply legal dimension choices or callback semantics,
report that exact blocker. Do not borrow the synthetic fixture's bounds or promote
an observed default into a reviewed range.

## Proposed acceptance tests

| Layer | Meaningful acceptance |
| --- | --- |
| Input contract | Complete vectors, canonical ordering, duplicate IDs, omitted values, undeclared differences, wrong units, out-of-range/off-grid values and changed baseline reject before dispatch |
| Local planning | Mixed V/I changes create only the declared child plans; counts and reservations equal their sum; no store/remote contact or authority is created by plan |
| Lifecycle | Fresh-process same-ID and interrupted submission reconcile without duplicate spend; running/unknown children stop the next admission; concurrent advances retain one child intent |
| Failure policy | Safety/authority/input failure stops the batch; generic failure is not relabeled convergence; failed, extraction-failed and untouched rows all remain visible |
| Comparison | Declared V/I differences pass; changed supply, load, corner/model, analysis grid, signal mapping or measurement definition reject; unchanged legacy comparison still rejects different inputs |
| Provenance | Missing/tampered operation, plan, input, reader or receipt identity rejects; every successful metric maps to its own retained source |
| Export | Korean labels roundtrip with BOM; formula/control/whitespace prefixes are neutralized; quoting/newlines work; missing or failed values are null, never zero |
| Waveforms | Only actual retained samples export; axes/nodes/phase remain explicit; incompatible grids remain marked or reject rather than silently aligning |
| W/L | Unit equivalence preserves raw input and exact SI; unknown properties/fingers/callbacks/grids reject; effective-width mismatch, accidental topology/model edits and wrong revision fail independent checks |
| Installation | Exact built package runs candidate planning/comparison tests in isolation; earlier public contracts and journals/replay remain preserved across version transitions |

Synthetic tests establish software behavior only. Retained-result replay verifies
only unchanged relevant execution bytes/bindings and must identify their original
source. A fresh native candidate test requires a new explicit bound experiment;
previous fully consumed M2 grants cannot authorize it.

After the exact release-A candidate is reviewable, present one combined follow-up
decision: selected circuit/revisions, complete finite candidate list and analyses,
maximum executions/result reservations, missing read-only observations, exact
change/restore scope, failure/stop policy and any required implementation/deployment
authority. Confirm current accounting immediately before execution and preserve all
consumption, failed claims and receipts. Release publication and actual environment
update remain separate decisions bound to exact artifacts.
