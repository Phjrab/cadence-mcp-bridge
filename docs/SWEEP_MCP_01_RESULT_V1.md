# SWEEP-MCP-01 — bounded 1D sweep result

Date: 2026-09-30. Outcome:
`FIXTURE_1D_MCP_E2E_VERIFIED_ACTUAL_BIAS_1D_UNAVAILABLE`.

Five typed MCP tools plan, submit or resume, inspect, aggregate, and cancel a
single-axis sweep. The registered RC transient fixture supplies the only
reviewed numeric axis bindings in this revision. Requests select one of its
three numeric variables, an explicit finite list or a linear range, the exact
units, fixed non-axis values, and the existing completion measurement. Decimal
values, direction, endpoint, duplicates, profile limits, and a 16-point cap
are validated before submission. Each point starts with independent initial
conditions. The plan hash, experiment key, parent ID, point ID, child job ID,
and operation key have separate identities.

The private SQLite checkpoint survives MCP process restarts. A repeated
experiment key resolves to the same parent and children; a different key is
an intentional new experiment. An uncertain submit is reconciled by exact
child lookup and is never blindly reissued. Unknown, failed, cancelled, and
not-run points remain visible in the aggregate. Cancellation checks recorded
child ownership and remote identity before using the existing process-group
cancel path. Requested and effective inputs are separate fields; effective
fixture values are read from the job-owned remote manifest. The original
runner's 17-digit float serialization is compared at the represented numeric
precision and its exact applied string is retained.

One real MCP client completed three RC fixture simulations at reviewed
resistance values 900, 1000, and 1100 ohms, with the registered fixed
capacitance and stop time. The first point completed successfully but an
overstrict local decimal-string comparison initially marked its outcome
unknown. A new MCP session reconciled that exact existing child and ran only
the remaining two. The final aggregate contained three valid completion
measurements, three distinct children, verified effective inputs, and no lost
point or duplicate simulation. A same-key request after completion created no
new attempt. The cumulative Spectre ledger advanced from 11 to 14 of 100 and
reserved 128 MiB for each new attempt under the existing 5 GiB result limit;
the disk floor and one-active-EDA limit were checked. The immutable remote
budget helper is `phase-campaign/sweep-mcp-v1` under the managed root. No
source, ADE state, PDK, or historical evidence was modified.

The private report `.codex/sweep-mcp-v1-e2e-private.json` contains the bounded
point IDs, actual manifest values, campaign ledger and postflight facts. Its
SHA-256 is `918f3fd1ed4b75f59a0f3dddf178f360e99072ec9faf7edc3061cf9dbc582ba0`.
The public report does not publish those private identifiers or raw data.

The historical actual-circuit pairs 300/650, 310/676, and 320/702 mV change
both bias variables. They are a coupled operating-point path, not a
single-variable sweep. No approved one-axis circuit binding or new voltage
range was present, so this phase did not execute a new actual-circuit bias
sweep or report a new circuit scalar/spectrum. The earlier fixed DC/AC MCP
diagnostics remain available at their pinned candidate. The fixture result
measures simulation completion only; it is not an analog performance metric.
`spec_evaluation=not_evaluated` remains unchanged. Actual one-axis bias work
needs a separately reviewed binding and bounded voltage range before execution.

Local fault tests cover duplicate request, interrupted submit reconciliation,
partial failure, missing result, exhausted budget, cancellation, invalid
values, and corrupt checkpoints. The phase report is complete for the reviewed
fixture capability; actual-circuit one-axis execution remains unavailable.

Validation: the initial full regression run had 652 passes, 10 failures, and
8 skips. One failure was an outdated installer tool-count assertion; nine
legacy deployment/recovery failures came from Windows temporary-path length.
After fixing the assertion and using a shorter temporary root, all 112 tests
in the affected modules passed. The final sweep/server/SSH/installer run had
52 passes. Ruff, mypy, formatting, the repository secret scan, and the strict
security gate passed. The gate's dependency audit required updating the
transitive PyJWT lock from 2.13.0 to 2.14.0; the final audit reported no known
vulnerabilities. This is a full run plus targeted failure resolution, not a
claim of a second pristine full-suite run.
