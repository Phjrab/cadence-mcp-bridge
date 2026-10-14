# POST-07 ideal voltage-feedback QA continuation

Execution checkpoint: the finite DC1/AC2 batch now completes on exact installed
0f877b6, UID500, shared124 /15,184,429,056 bytes, native22/24. Both grids agree
on a negative~-15.543deg sampled margin; this is not amplifier performance PASS.
Grant is consumed; restart/read/retry/report spends0. See POST_07_LOOP_RESULT_V1.md.
The original prospective plan below is retained as history, not fresh capacity.

Status: prepared input evidence, NOT actual PM qualification. The user's direct
remaining-QA delegation authorizes this work; this plan is not a separate grant
or approval. Public2.0.0 and existing generic/legacy contracts remain unchanged.

## Completed preparation

New owned amplifier OA/state only, with a unity ideal VCVS sensing Vop-Vom.
It drives Vret relative to a fixed0.5V Vcm. A series source between Vm and Vret
has DC0/AC1; the independent Vp source has the same0.5V common mode and AC0.
Actual OA pin-map/check/save and common DC/AC netlisting/effective inputs pass.
The return node occurs only in the VCVS output and injection source. This ideal
feedback network senses without output loading and supplies ideal return drive;
it is a distinct QA topology, not the user's application or common-mode loop.

Current installed Spectre `-h vsource` succeeds. Retained help explicitly gives
small-signal mag default0V and phase default0deg. The four fixed bias/supply DC
sources omit mag; the main input/common-mode sources explicitly use mag0 and the
probe uses mag1. This is HELP_DOCUMENTED evidence, not measured AC source proof.
The inherited sine source types are limited to DC/AC here; no TRAN eligibility
is inferred. Do not add sinusoidal stimulus or a TRAN experiment under this plan.

The first preparation fails on protected SKILL constant t. Its partial source,
logs and local-only harness failures are retained. Minimal variable-only v4
passes; no original OA/state/PDK/library content or permission is changed. These
preparations and help reads use0 simulations/reservations/native corrections.
Active runtime remains the prior offset bundle; successful new source preparation
is not native registration, grant confirmation, activation or admission.

## Next finite validation

Implement a closed opt-in host definition/loop eligibility path before execution.
It must bind the actual static topology, reader mapping and succeeded jobs.
For this exact unilateral fixture, with other AC sources zero,
`Vret_AC = A*(0 - Vm_AC)` and the return ratio is `L = -Vret_AC / Vm_AC`.
Do not choose a sign from a favorable phase result. Check that measured Vp/Vcm
are AC0 and the injection relation is Vm-Vret=1+0j across the complete grid.
Any additional return-node path, wrong feedback gain, independent AC stimulus,
wrong mapping or insufficient topology evidence must reject.

Calibrate sign/crossing/unwrapping with independent known-loop synthetic cases,
clearly separated from actual Cadence evidence. Preserve every observed unity
crossing. Multiple/ambiguous crossings, unresolved phase unwrap or no descending
crossing cannot yield a single qualified margin. Report measured range/bracket,
definition/conditions/job/source/reader/frame hashes and scope. A sampled margin
does not prove whole-circuit/internal/multiple-loop/PVT stability.

After current registration/trust/ledger/disk gates, the proposed finite batch is:

| Job | Purpose | Conditions | Maximum reservation |
| --- | --- | --- | --- |
| DC1 | Closed-loop operating point and loading check against retained nominal source DC | Same source, NN/27C,0.5V common mode,0.32/0.702V bias, DC0 injection | 128MiB |
| AC1 | Complete loop-ratio extraction and measured stimulus checks | 10Hz-1GHz,8 points/decade | 128MiB |
| AC2 | Repeat with a finer saved grid | Same conditions,16 points/decade | 128MiB |

Record exact identities/bindings/grant and per-job stop criteria before admission.
Do not run until DC eligibility and common extraction/definition integration are
implemented. Compare actual two-grid crossings explicitly; lack of convergence
must stay unqualified, without automatic extra exploration. A failed job retains
its ID/outcome/reservation, and the consumed three-job scope cannot be refreshed
into three unused attempts. No fourth job is included in this finite proposal.
Lookup/restart/same-ID retry must add0 and preserve journal/replay history.

Latest actual cumulative121 /14,781,775,872 bytes, remaining2,398,093,312 of16GiB;
native22/24. If all three jobs are admitted, anticipated cumulative124 /
15,184,429,056 bytes. These are prospective arithmetic, not actual reservations.
The existing ledger/domain/analysis/sweep journals remain authoritative.

Private source/preparation receipts: post07-loop-bench-v4, post07-loop-input-v1,
loop-topology-observation.private.json and post07-vsource-default-v1. Reuse them;
do not recreate successful preparations or publish raw OA/netlist/vendor help.
