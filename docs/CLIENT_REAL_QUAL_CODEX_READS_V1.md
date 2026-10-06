# CLIENT-REAL-QUAL-01: actual Codex read-only evidence

Observed: 2026-10-06, 09:43 KST. Starting main:
`434e5efd7fc8ad940d921d5e82c5cd25bd818d7f` (checkpoint #121).
Branch: `feat/client-real-qual-codex-reads`.
Integration: [PR #122](https://github.com/Phjrab/cadence-mcp-bridge/pull/122),
with resulting remote SHA/tree retained privately after permitted merge.
**Partial application qualification; the major phase remains incomplete.**

## Direct application evidence

After the human registration/restart handoff, Cadence bridge tools are exposed
to the active Codex desktop agent. Calls below used its actual
`mcp__cadence_mcp_bridge` tools. No separately launched SDK client or UI automation
was substituted. The global config and app version were not re-inspected; direct
tool availability/call success establishes this connection, not unseen UI actions.

| Actual operation | Observed result |
| --- | --- |
| `cadence_list_designs` | One registered reference design returned |
| `cadence_describe_design` | Bounded analyses/variables/measurements/corners; protected source and owned-copy policy |
| `cadence_design_pdk_status` | gpdk090 reference adapter has fixed native DC/AC/TRAN compatibility |
| `cadence_native_diagnostic_status` | Existing admitted native DC operation: simulator/extraction/stage succeeded |
| `cadence_native_diagnostic_result` | Existing bounded valid DC result and provenance read successfully |

The actual exposed agent catalog has **69 names**, exactly matching the reviewed
snapshot's names. This is **catalog-name evidence**, not a captured application
tools/list response or proof of full input/output schema equality. App version,
initialization/negotiation, full schema dump and app-owned shutdown/restart
lifecycle remain NOT_TESTED. Earlier SDK/protocol evidence remains separate.

The native UUID was selected from preserved admitted evidence, never generated
or resubmitted. Its measurement-frame hash equals the preserved earlier result.
The recorded job is a historical NN/27 C/1 V DC result with applied 320/702 mV
bias; it is not evidence of the latest physical circuit or a specification PASS.
Two historical warnings remain in the bounded result; spec_evaluation remains
not_evaluated. Source/copy/model/PSF identities and the full bounded response
are private. No proprietary content, raw waveform, UUID or private path is added
to this public report.

The result records protected_unchanged=true for that operation. This is not a
new blanket fingerprint check of the current guest; no separate fresh guest
postflight or cumulative-counter query is claimed here.

## Qualification scope and resources

| Scope | Current state |
| --- | --- |
| Actual Codex bridge connection and these five read-only calls | VERIFIED |
| Actual Codex exposed 69 names versus reviewed snapshot names | VERIFIED, names only |
| Actual Codex full tools/list schemas, version and lifecycle | NOT_TESTED |
| Actual Codex Cadence read | VERIFIED for this preserved native DC result only |
| New generic physical execution / variable ranges | UNQUALIFIED; execution_authorized=false |
| Actual Claude Desktop | CLAUDE_REAL_CLIENT_UNVERIFIED |

New simulation, result reservation, deployment, design mutation, cleanup and
global config writes by the agent: **zero**. Two bounded native read calls contact
the registered host; no remote shell or arbitrary path/script capability is used.
The last independently observed cumulative counters remain 62/500 and
7,114,588,160 / 10 GiB; these are not represented as fresh counters from this read.
The phase's 1,091 baselined private records remain unchanged. No runtime, API,
remote source, profile/journal, license, package/version or schema changes.

Documentation-only integration uses contract/secret/diff checks and reuses #120
full/static/security/package evidence for unchanged code. No simulation rerun is
needed to verify a read-only application connection. Correction consumption: 0.

## Remaining external qualification

Follow the [existing application handoff](CLIENT_REAL_QUAL_01_CHECKPOINT_V1.md)
for Claude against the same reviewed bridge and operator configuration. Keep its
matrix unverified until direct named-app calls exist. Obtain app/version/full
schema/lifecycle evidence only through allowed application diagnostics or human
observations; native UI automation restrictions remain binding. The successful
Codex calls remove the earlier missing-tool blocker for this active agent; they
do not remove the remaining Claude or complete-app qualification gates.

Resume this same major phase; no release or next development phase is activated.
Imported planning rights remain independently LEGAL_REVIEW_REQUIRED.
