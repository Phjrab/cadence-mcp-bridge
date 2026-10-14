# POST-07 fast-input sampled step validation

## Review correction and finite preparation

Automatic review4269249515 identified that a monotonic input ramp can limit the
output slope. Monotonicity alone is insufficient. The host-only opt-in estimator
now preserves unique measured input10/90 crossings, their containing-bracket
duration upper bound and the output crossing-duration lower bound. A value is
qualified only when the input bound is at most25percent of the output bound.
The operator may tighten this ratio but cannot widen it. Ambiguous crossings,
unresolved grids and slow edges retain null values and explicit failure status.
No native assets, public MCP schema or execution authority are changed.

The retained actual inverter1ns-ramp result is now
`INPUT_EDGE_NOT_FAST_ENOUGH_FOR_SAMPLED_STEP_RESPONSE`: its input-edge upper bound
is approximately0.878ns versus an output-duration lower bound0.547ns. Its earlier
-1.100875721V/ns report and PSF remain preserved as historical source-pinned
evidence; that number is no longer a qualified fast-step response. Comparator
unsettled-plateau rejection remains. This reclassification spends0.

One newly owned inverter QA OA/state copy is prepared with1ps rise/fall,0.5→0.7V,
500ps delay,2ns width and4ns period. Actual common netlisting/effective input passes
for TRAN stop1.5ns/maxstep20ps, NN/27C and unchanged original loading. Original
MyDesignLib/ADE and the existing ledger are preserved. A local assertion expected
a parameterized pulse val0 whereas the source emits numeric0.5; the failed
assertion is retained and the already successful netlist is rechecked without
another netlisting run or stimulus change.

The direct user's continuing remaining-QA delegation is the authority, not this
document or the generated plan. One finite TRAN grant is prepared for at most
128MiB using the same domain/journals/ledger; no admission or reservation has yet
occurred at this checkpoint. Before each admission, fresh qualification, trust,
disk, accounting, approval and exact effective-input checks remain mandatory.
Initial plateau0–0.3ns/final1–1.5ns and the25percent edge criterion are declared
before execution. Any failed run or insufficient response retains its job/PSF/
outcome/spend; no blind replay, tolerance widening or second job under this grant.

Current cumulative124/500 and15,184,429,056/17,179,869,184 bytes; if admitted once,
anticipated125 and15,318,646,784 bytes. These are prospective, not spent values.
Native changes remain22/24. Previous fully consumed loop grant and all source,
result, failure, approval and replay histories remain retained. Further Claude
checks are EXCLUDED_BY_USER, not PASS. Public2.0.0 stays immutable; no POST merge
or publication is inferred. Exact rebuilt install, actual TRAN, restart/read/retry,
updated review and exact hosted checks remain required.
