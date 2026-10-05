# SPEC-CONTRACT-01 result

Date: 2026-10-06. Starting main:
`e3a3fb41d48a391a8c9667237a076dabeea3dda1` (merged ANALOG-MEAS-01 #118).
Feature branch: `feat/spec-contract-01`. Integration uses the containing reviewed
feature PR; resulting remote SHA/tree verification is preserved privately after
permitted merge, without a state-sync-only PR. Package/server version stays 1.0.0.
No tag, release or version bump is created.

## Implementation and contracts

Operator registry v7 adds `specification_contracts` to v6: logical specification,
design and measurement IDs; exact source-contract/compiled-definition hashes;
bounded decimal targets, comparison, unit and user-goal reference; exact expected
analysis, revision, operating point and effective conditions. Registration uses
the existing CLI and private registry. No second configuration system or executor.

Three additive read-only tools increase inventory **66 → 69**:

- `cadence_list_specifications`
- `cadence_describe_specification`
- `cadence_evaluate_specification`

All previous 66 complete tool schemas and v1–v6 registry schema artifacts remain
unchanged. Evaluation reads admitted analog evidence through existing measurement,
analysis, PDK, native input/identity and protection validators. Clients cannot
supply facts, targets, units, expressions, scripts, paths or registration.
v7 revalidates the full v6 projection and then the full v5 execution projection;
new read-only goals cannot change sweep admission identity or weaken execution
field hashes. No new journal, extraction, reservation or deployment is introduced.

## Scientific behavior

Comparators are `>=`, `<=`, `>`, `<` and inclusive `range`, with canonical decimal
targets and no rounding-to-display, tolerance or unit conversion. Every decision
includes the registered contract/hash, source result/hash, definition, unit, native
provenance and actual effective settings. PASS/FAIL applies to one exact admitted
operation and its registered conditions, never all PVT or a later FS revision.

| Situation | Outcome |
| --- | --- |
| No selected target | NOT_EVALUATED, no source read |
| Reader lacks scientific qualification | UNQUALIFIED |
| No operation selected for eligible reader | MISSING_MEASUREMENT |
| Partially qualified bandwidth estimate | UNQUALIFIED, preserved partial measurement |
| Effective condition/revision/plan/settings mismatch | CONDITION_MISMATCH |
| Fully qualified matching-condition value meets/misses selected goal | PASS / FAIL |
| Unknown/stale/unadmitted/substituted/malformed/failed source request | Tool error; never specification FAIL |

**The actual reference has no numerical user specification.** Its v7 constructor
has zero specifications and its listing remains `not_evaluated`/`not_selected`.
No physical design PASS/FAIL is claimed. Fictional unit-test goals verify comparator
boundaries and failure semantics only. The installed fictional example contains
a targetless declaration, not a real target. Existing measurement results retain
their original `spec_evaluation = not_evaluated` field unchanged.

## Verification and corrections

- `uv sync --all-groups`: pass, existing locked dependencies retained.
- Ruff and mypy: pass; 45 source modules checked.
- Focused specification/analog/server/protocol suite: **79 passed**, one cache warning.
- Full unit suite: **1,693 passed, four OS symlink skips, 57 warnings**,
  755.74 seconds. Canonical `uv run python -m pytest tests/unit` used.
- Security suite: **18 passed**; secret preflight and dependency audit pass,
  no known locked dependency vulnerabilities.
- Final wheel/sdist audit and isolated installed acceptance: pass. 53 wheel
  members / 54 sdist members; canonical Apache-2.0/license/notices included,
  unexpected/private/protected patterns zero, imported planning excluded.
- Installed Codex/MCP JSON/Claude configurations each expose 69 tools and execute
  all three new APIs against a fictional missing target: NOT_EVALUATED without
  admission, remote transport or fabricated measurement; CLI/uninstall pass.
- Actual exported Codex/Claude **SDK stdio** initializes/lists/calls against the
  same server: all 66 old full schemas equal; preserved native DC/AC/TRAN,
  analog results/provenance, RC sweep, storage inventory and restart equal.
  Empty reference goals and unknown-spec denial pass. This is not Desktop app E2E.

One correction of the active twenty-correction allowance was consumed. Initial
static validation found formatting/dictionary type issues; focused verification
found strict nested contract tuples rejected SDK JSON arrays and a wrong-identity
test backend ignored its flag. The bounded correction revalidates output contracts
through strict JSON, uses explicit typed arguments, repairs the test backend and
updates additive protocol inventories. Original failure transcript/record retained.

## Resources and protected integrity

New Spectre attempts **0**; cumulative **62/500**. New reservations **0**;
cumulative **7,114,588,160 / 10,737,418,240 bytes (10 GiB)**. Deployment, design
mutation, storage deletion, extraction and optimization **0**. Removed elapsed
ceiling, shared EDA lock, disk floor and durable replay domains remain intact.
Fixed reference postflight before/after confirms original/OA/ADE/PDK fingerprints,
prior jobs and counters equal. The original admission journal bytes and **1,063**
prior private evidence records remain equal. No historical evidence is rewritten.

## Residual limitations and next phase

Another operator can register selected goals and inspect/evaluate them through
the same bounded MCP server and client configuration. Physical evaluation remains
limited to actually qualified registered analog readers; gain is at 10 Hz only.
Bandwidth is partial; phase margin/power/offset/slew remain UNQUALIFIED. Reference
goals have not been selected, so meaningful physical design PASS/FAIL is pending
future user intent, not an implementation failure or a request to invent goals.

New physical routes, other Cadence versions/PDKs and real-design numeric sweeps
remain unqualified/deferred. `CLAUDE_REAL_CLIENT_UNVERIFIED` and fresh Codex app
NOT_TESTED remain. Historical real-host storage deletion is NOT_RUN and requires
separate explicit plan/item selection. Apache-2.0 originals/external product terms
stay separate; imported `docs/agent_plan` rights remain `LEGAL_REVIEW_REQUIRED`,
excluded from curated distributions. Whole-repository rights are not declared READY.

Recommend **Release Readiness reassessment** next: inspect actual API compatibility,
public scope, client evidence, licensing and packaging before deciding semver or
publication. No release or optimization is automatically activated. Complete this
one phase, report evidence and ask once whether to continue.
