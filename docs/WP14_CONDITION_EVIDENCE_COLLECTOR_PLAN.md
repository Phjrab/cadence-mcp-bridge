# WP-14 Condition Evidence Collector Plan

Date: 2026-09-14

Plan: `WP14_CONDITION_EVIDENCE_COLLECTOR_PLAN`, version 1

Status: `PLAN_READY_FOR_REVIEW_ROLE_BINDING_REQUIRED`

Normalized-LF SHA-256:
`4588834378f38a65678880fd5c5a1a93fd85545b482a69a1f60a1ef96b5033fb`

## Purpose and authority

This planning-only artifact defines a fixed, bounded, read-only collector for VDD, VCM, load
condition, and source/ADE-state semantic revision evidence. It is bound to decision record v4
SHA-256 `95c897b2ac277e777db56ad7996db94d6a0119a0e4150b1ac29b4637a7058f46`.
It contains no implementation or confirmation token and authorizes no deployment, invocation,
simulation, MCP exposure, OA save, ADE-state change, or design/PDK/work-library mutation.

## Fixed allowlist

The future operator-only command is `wp14-condition-evidence` and accepts no arguments. It is
compiled for only profile `actual-differential-amplifier-tb2-transient`, source
`MyDesignLib/Differential_Amplifier_TB2/schematic` opened with OA mode `r`, ADE L `state1`, its six
fixed parser files, the fixed source snapshot, and gpdk090 v4.6 section NN as hash-only evidence.
The command is not an MCP tool and exposes no raw shell or SKILL route.

Existing bounded evidence does not identify the exact OA instance/net/terminal/property tuples
that represent VDD, VCM, and load. Those selectors must not be guessed. Before implementation, an
immutable role-binding manifest must identify exact selectors, expected master cellviews, exact
cardinality, and its SHA-256. The manifest must come from reviewed operator evidence or a separately
approved fixed names-only discovery. Until then, the plan is not implementation-ready.

## Read-only sequence

1. Verify the plan and role-binding hashes and the trusted installation identity.
2. Reject every argument, symlink, oversized input, concurrent call, and active or ambiguous lock.
3. Fingerprint the fixed source, state, profile, source snapshot, model, and binding before access.
4. Parse only the six allowlisted ADE-state files with a fixed grammar.
5. Open the exact source cellview with OA mode `r`, resolve only hash-bound selectors with exact
   cardinality, collect finite bounded values, and close without save.
6. Recompute every protected fingerprint and require exact equality.
7. Classify semantic revision linkage only from an explicit generation-manifest hash binding or
   embedded revision binding. Identity, topology, separate hashes, or timestamps are insufficient.
8. Emit one redacted JSON object of at most 32,768 bytes and stop.

Total timeout is 90 seconds, OA open/close is bounded to 30 seconds, concurrency is one with a
nonblocking lock, fixed state/source trees are limited to 4,096 entries and 128 MiB, individual
state files to 1 MiB, the source snapshot to 10 MiB, model hashing to 64 MiB, and load output to at
most eight elements. Logs are bounded to 65,536 bytes each.

## Output and sensitive-data boundary

The fixed schema emits only plan/profile identifiers, finite VDD/VCM values or null, a bounded
load summary or null, bias-to-state binding, SHA-256 fingerprints, semantic-link status, invariant
booleans, and bounded blocker enums. It never emits instance/net/terminal/property names, paths,
raw netlist or ADE-state content, OA dumps, PDK content, waveforms, license/environment values,
credentials, process command lines, or unbounded logs/errors.

Absent, ambiguous, unsupported, duplicated, or out-of-range evidence is never guessed: its value
is null and the result is `incomplete_evidence` or `blocked`. A timestamp cannot prove semantic
revision equivalence. A successful collector result supplies evidence only; it does not approve a
scientific baseline.

## Lock and failure policy

Active locks, stale or ownership-ambiguous locks, and panic/recovery artifacts cause `BLOCKED`.
Nothing is deleted, unlocked, renamed, repaired, retried, or redirected. Only bounded artifact
class, owner, timestamp, PID, and PID-running state may be reported. Any fingerprint drift, close
failure, timeout, unexpected role count, unsupported expression or property type, or attempted
write/save/simulation fails closed.

## Acceptance criteria

The normative 20 criteria are stored in
`docs/plans/WP14_CONDITION_EVIDENCE_COLLECTOR_PLAN_V1.json`. They require zero arguments, exact
targets and hash-bound role selectors, OA read-only open/close, unchanged before/after fingerprints,
strict lock and resource limits, redacted bounded output, negative security tests, and the absence
of every simulation, mutation, deployment, MCP, cleanup, retry, merge, and WP-15 operation.

Three later approvals remain independent: the exact role binding, implementation/deployment, and
one fixed read-only invocation. After evidence is collected, final scientific approval or rejection
is still a separate user decision.
