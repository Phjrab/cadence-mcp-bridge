# CLIENT-REAL-QUAL-CODEX-02: current actual Codex read checkpoint

Observed on 2026-10-07 KST. Start main:
`815321e71ea0565b3119d9d6da54d57b84bd2615` (PR135).
Branch: `feat/client-real-qual-codex-current-02`. Exact candidate/review/normal
PR integration and remote SHA/tree receipts belong to the containing PR.

Status: **PARTIALLY_VERIFIED**. Current actual Codex names and bounded native DC
reads are verified; operator-bound measurement/sweep/specification and complete
client qualification remain incomplete. No implementation is rebuilt here.

## Direct app observations

Calls use the active Codex agent's `mcp__cadence_mcp_bridge` tools. No SDK process
is substituted for the actual application. The model-visible deferred inventory
is name/existence metadata, not a captured full application tools/list response.

| Observation | Actual result |
| --- | --- |
| Before restart | 77 names, exactly the reviewed pre-Offset inventory |
| User restart handoff | Initially deferred, then explicitly reported complete; no agent-owned restart or config write |
| After restart | 85 names, equal to current source inventory; all eight later names now exposed |
| `cadence_runtime_info_v2` | Bridge 1.0.0, stdio; built-in design registry v4, one design; built-in PDK registry v2, one adapter |
| Journal selection | Analysis platform default, Sweep package-relative default; health not assessed |
| Runtime comparison | Same full runtime payload and registry digests before/after restart |
| Design list/describe/PDK/measurement definitions | Bounded reference discovery and three native measurement definitions; generic execution still unqualified |
| Measurement catalog | Empty analog, signed DC power and goal lists in this loaded default configuration |
| Native DC status/result | Preserved admitted operation succeeded, quality valid, protected flag true; current full payload equals the frozen historical result |
| Repeated native DC read | Identical full payload; same-ID reading only, no submit/reservation |
| Generic analysis read with the preserved native ID | Bounded invalid_input: analysis operation not admitted in the selected generic journal |
| Unknown design | Bounded rejection; subsequent native DC read succeeds |
| New amplifier specification catalog | Tool callable, bounded rejection requiring the reviewed finite-grid operator registry |

The new names are `cadence_offset_study_result`,
`cadence_prepare_amplifier_sweep`, `cadence_submit_amplifier_sweep`,
`cadence_amplifier_sweep_status`, `cadence_amplifier_sweep_result`,
`cadence_cancel_amplifier_sweep`, `cadence_amplifier_specification_catalog` and
`cadence_evaluate_amplifier_specifications`. Submit/cancel tools were not called.

Pre-restart native status/result/repeat and admission rejection are preserved
in the conversation tool cards. The attempted combined private export exceeded
Windows command length; it did not invalidate those returned tool events. Initial
runtime/local catalog records and post-restart bounded records are private.
No missing raw pre-restart record or event ID is invented. DC frame equality to
its frozen historical result was observed on both sides of the user handoff.

## Qualification limits

Runtime responses do not attest a source SHA, build artifact or app version.
The private launch observation points to the reviewed checkout, but exact loaded
process identity, process start times and previous bridge termination were not
independently captured. App version, full input/output schemas and annotations,
initialize negotiation, stderr/EOF and new job lifecycle remain NOT_TESTED.
Existing-result reads do not qualify simulation execution.

The historical native result remains NN / 27 C / VDD 1 V with its recorded
320/702 mV applied bias and warnings. This phase creates no new scientific fact,
current-source/ADE equivalence or design PASS. No numerical goal is invented.

## Configuration finding and safe handoff

The current registration launches the checkout with only the observed UTF-8
environment override. Built-in v4 and default journals are expected defaults,
not a server defect. Code updates/restarts do not select operator catalogs or
migrate historic admissions.

Keep two existing qualification contexts distinct:

1. Historical native/analog/power/diagnostic reads use the previously validated
   operator measurement registry and its existing analysis admission journal.
2. Finite amplifier grid reads use the exact reviewed
   [finite-grid registry](config/reference-amplifier-finite-grid-v1.json) and
   existing amplifier sweep journal. Registry version 2 is an explicitly pinned
   context, not an older implementation inferred from its number. Do not merge
   registries by hand. The companion target catalog stays empty.

Private prepared fragments select those existing contexts and permit only
bounded read tools. They are not installed by this phase. Review/apply the chosen
fragment through the operator/client mechanism, then restart and compare runtime
versions, counts and semantic digests. Select existing admitted IDs privately;
do not generate new IDs, create replacement journals, resubmit or reset counters.
See [runtime observation](RUNTIME_CONFIGURATION_V1.md) and
[official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
Operator-bound current measurement qualification requires a separately activated
handoff. No app configuration is silently changed to manufacture a PASS.

## Claude evidence is retained

[PR127's actual Claude Desktop Code-tab report](validation/claude-desktop/20261006T0407Z/REPORT.md)
already verifies preserved reads and restart. It is not replaced by a blanket
absence claim. Its unreviewed loaded-tree identity, default Sweep journal block
and untested Desktop chat/full schema/protocol/new lifecycle remain separate
limits. Complete gate remains CLAUDE_REAL_CLIENT_UNVERIFIED; later Claude work
is deferred. No new Claude action is required for this checkpoint.

## Gates, resources and protection

Documentation/private evidence/handoff preparation only. Runtime, remote code,
schemas, source tests/toolchain, policies, licenses, imported planning and replay/
admission identities remain identical to starting main. Fresh contract/client/
runtime/security/package/document gates and exact unchanged full-unit reuse are
recorded in the containing PR. Fresh 61 client/runtime/contract tests PASS
(47.01 seconds), Ruff/mypy59/contract85/security18/locked dependency audit PASS.
Full 2,234 PASS / five OS symlink SKIP / 56 warnings is reused after exact
unchanged source/test/toolchain verification; it is not a fresh full-suite run.
Canonical fresh package gate PASS: wheel67/sdist68, expected Apache notices,
zero unexpected/protected/imported content; isolated install, CLI, three SDK
stdio formats with85 tools and uninstall PASS. These are SDK/package evidence.
Missing actual app tests remain NOT_TESTED.
CI/independent review are reported as actually observed.

Zero new simulations, result reservations, deployments, deletions, targets and
global config changes. Native reads contact the registered host; normal logging
may occur, so zero filesystem side effects is not claimed. Whole live checkpoint
and all 1,955 baseline private hashes are checked before integration. Shared
ledger remains 82/500 attempts and 9,798,942,720/10,737,418,240 reserved bytes.
Six existing sweep jobs remain 1,105,799 logical / 1,511,424 allocated bytes,
not whole VM usage. No refund/reset or elapsed ceiling is introduced.

Five conservative evidence/orchestration corrections are retained within the
20 ceiling: oversized export, lost orchestration bindings after restart and two
private/public write permission failures plus one loader-return unpacking fix.
Initial tool failures remain history;
no runtime or guard was weakened to fix them. Prior phase correction histories
and the unrelated local stat-only OCEAN change are preserved.

Finish this reviewed checkpoint PR and report. Recommend separately activating
operator-bound current Codex read qualification, keeping simulation, deletion
and publication excluded. Do not silently install a fragment or start another
phase. [Readiness v3](RELEASE_READINESS_V3.md) stays conditional by scope; imported
rights LEGAL_REVIEW_REQUIRED and PUBLICATION_NOT_AUTHORIZED remain. Earlier
archive inspections apply only to their inspected commit, not this doc candidate.
