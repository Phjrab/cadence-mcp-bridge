# WP-14 VBIASN/VBIASP Source-of-Truth Decision

Date: 2026-09-14

Package: [WP14_VBIAS_DECISION_PACKAGE_V1.json](decisions/WP14_VBIAS_DECISION_PACKAGE_V1.json)

Package status: `READY_FOR_REVIEW`; confirmation status: `BASELINE_DECISION_REQUIRED`.

## Scope and outcome

PR #19 merged reviewed WP-13 head `7ec535ea035f0a1a424d802d051726a2a4b12930` as
`b12cff904fe31a1d68490836c1fe6765734b9bf0`. That exact commit was latest `origin/main`
when `wp/WP-14-vbias-source-of-truth` was created. Repository visibility was PRIVATE.

WP-14 prepares a versioned decision package from repository evidence. It does not select an
approved baseline. Document acceptance can pass while baseline confirmation remains BLOCKED on
the user's scientific choice and supporting conditions. WP-13 remains the last completed WP;
the next work stays WP-14, not WP-15.

No SSH, Cadence, simulation, deployment, MCP change, OA write/save, state change, bias application,
or source/schematic/layout/work-library/PDK/V1-V4 evidence operation occurs in this run. This is
not a fresh remote audit. The actual-state facts below are dated WP-13 observations; their remote
fingerprints were not revalidated in WP-14.

## Evidence and binding

The JSON package pins six evidence paths and Git blob IDs at the base commit. The two audit
reports, fixed registry, wrapper, local variable gate, and imported history have distinct roles.
Raw source/state/model content is not copied into the proposal.

| Evidence | VBIASN | VBIASP | What it establishes |
|---|---|---|---|
| Source snapshot, WP-12/WP-13 audits | one reference, no declaration | one reference, no declaration | consumes names; declares neither value |
| Registry version 1 and `prepare_actual` wrapper | `300m` = 0.300 V | `650m` = 0.650 V | fixed compatibility execution values supplied before including the snapshot |
| ADE L state1, WP-13 observation | `300m` = 0.300 V | `650m` = 0.650 V | values stored at the observation time; not proof of scientific correctness |
| Historical research reported in WP-12/imported history | `370m` = 0.370 V | `650m` = 0.650 V | reported candidate; original measurement/revision linkage unavailable in the bounded evidence |

The JSON uses separate version-1 candidate records `compatibility-observation` and
`research-report`; these are documentation IDs, not runtime profiles. The v1 registry and wrapper
are unchanged. Both `scientific_baseline_approved` flags remain false. Agreement on VBIASP does
not approve it independently, and agreement between state and wrapper does not choose VBIASN.

The local actual-profile contract uses `NoProfileVariables`, and the remote registry has an empty
variable schema. That caller restriction does not mean the stored ADE state has no variables.
It also does not globally disable the pre-existing fixed v1 submission implementation: this run
invokes none of it and grants no new execution authority. Parameter overrides remain unavailable.

## Conditions that cannot be inferred

The imported ICF-00-03 reference distinguishes compatibility and scientific baselines and records
a 1.0 V research goal. It is a planning/history reference, not a current VDD measurement or new
permission. VDD equality across the two candidates is unverified. VCM, input waveform, load,
device W/L/revision, and the research candidate's source/state hashes, model/corner/temperature,
analysis, and measurement record are unknown. No value or range is filled from an example.

WP-13 recorded gpdk090 4.6 / NN / 27 C and source counts 35/14/8 for the observed profile. Those
facts do not link the historical operating point to identical conditions. A topology count match
does not prove a parameter or connectivity match. An earlier process success does not establish
measurement validity, circuit performance, or signoff.

## Analysis and freshness decisions

| Item | Evidence | Consequence |
|---|---|---|
| Reviewed profile | transient, stop `4m` = 0.004 s | compatibility profile behavior |
| ADE state at WP-13 | DC enabled; transient disabled, stored stop `4m` | `analysis_mismatch`; stored stop time is not an enabled analysis |
| Source SHA-256 | `30e941fdc24ffdc30a8dc989ffb884cd2a5256797adfa5ce2b2c032af67d5351` | fixed historical snapshot identity |
| Profile SHA-256 | `dea735f2ba81ba5ca714df8dba1b752be1fa3ab67f5742c2cee76eb5af849a4b` | local registry hash reconfirmed; WP-13 remote observation retained |
| ADE-state tree-metadata SHA-256 | `a6ead91891db7b1372e9e41515c76ac3b7dc8b2adeae281f4383d3c1ba32364d` | metadata fingerprint, not proof of semantic equivalence |
| Source/state timestamps | `2026-08-20T09:18:28Z` / `2026-08-20T09:43:40Z` | source is 1,512 seconds older |
| Latest successful manifest | WP-13 source hash match | reproducibility of that snapshot, not freshness or performance |
| Runner provenance | WP-13 remote 0.18.0; main 0.17.0 | version/behavior evidence only; remote byte identity is unverified |

The user must separately choose the intended analysis policy and snapshot policy. Preserving
the transient snapshot contract acknowledges the DC-state mismatch; it does not repair state1.
A state-aligned DC proposal would need a later reviewed implementation. Accepting the pinned
historical snapshot does not mark it current or clear `SNAPSHOT_FRESHNESS_UNCONFIRMED`. Requiring
regeneration is a planning decision only; regeneration itself needs a separate bounded approval.

## Decisions requested after review

There is no recommended or default numeric selection. Review the JSON package and provide:

1. Both intended bias values and their unit V: the compatibility candidate, research candidate,
   separately evidenced values, or defer. Include source/state revision and relevant operating
   conditions supporting the scientific choice; missing evidence remains explicitly unresolved.
2. Intended analysis: preserve the fixed transient snapshot contract, require a future DC
   state-aligned plan, or defer. No analysis is applied by this choice.
3. Snapshot policy: accept the exact pinned snapshot as historical only, require separately
   approved regeneration, or defer. No silent freshness promotion is permitted.
4. Package ID/version/hash, approver, timestamp with timezone, and an identifiable approval record.

All decision fields are null/empty in version 1. Unknown ranges, steps, output definitions,
measurement contracts, and execution budgets remain outside this approval. Any future baseline
approval covers documentation/planning only. PR review/merge and scientific baseline approval
are different decisions; neither grants mutation, simulation, deployment, or sweep permission.

Keep the reviewed version intact. A later decision is a separate versioned record referencing
this package. Evidence changes require renewed review. Deferred or conflicting choices keep
confirmation BLOCKED; no newer candidate is selected automatically.

## Acceptance criteria

| ID | Required check |
|---|---|
| AC-01 | PR #19 and WP-13 HEAD are ancestors of the exact branch base; dedicated branch, private repository, clean starting tree. |
| AC-02 | Six evidence path/blob pairs resolve at the pinned commit; original audit and runtime files are unchanged. |
| AC-03 | Registry/wrapper compatibility values match the package; local actual variable schema remains empty. |
| AC-04 | Source references and absent declarations, dated ADE observations, and historical research values remain distinct. |
| AC-05 | Compatibility and research candidates have separate IDs/versions; neither is selected or scientifically approved. |
| AC-06 | Missing operating-condition/revision linkage remains unknown; VDD/VCM/load/geometry equivalence is not invented. |
| AC-07 | Analysis mismatch and -1512-second freshness evidence are retained; metadata hashes are not called semantic proof. |
| AC-08 | Every approval field is unset and every execution/mutation permission is false; no new runtime reader consumes the proposal. |
| AC-09 | Changes are confined to WP-14 documentation/state; previous progress-log entries and protected evidence are preserved. |
| AC-10 | Document checks, Ruff, strict mypy, local pytest, secret/security/dependency checks pass; feature-only commit/push is verified. |

Negative review cases: treating the `370m` report as the latest state, treating `300m` agreement
as approval, promoting common `650m` without choice, accepting missing/changed hashes, inferring
scientific equivalence from 35/14/8, or reading proposal/PR merge as execution authorization must
all leave confirmation blocked. No runtime policy is added or claimed by this document.

## Validation record

Package SHA-256 (UTF-8 without BOM, CRLF normalized to LF, final newline retained):
`58ce0aae5aa3f9cf46f65c1f1196b05663206000f52b4fc7a90fdef4f12eda9d`.
This normalization makes the digest independent of Windows Git checkout line endings. The
package is pinned additionally by the feature commit; its digest does not include this report.

Local document validation passed: six pinned evidence blobs equal the base and current files;
registry/wrapper tokens and SI-unit conversions agree; source declarations remain absent;
approval fields are null/empty; all boolean gates are false; candidate/context/freshness facts
match their evidence; all ten criteria are present; existing progress-log entries are preserved;
and the change set is limited to the six intended document/state files.

- `python -m ruff check .`: PASS.
- `python -m mypy src`: PASS, strict configuration, 17 source files.
- `CADENCE_MCP_RUN_INTEGRATION=0`, `python -m pytest`: 175 passed, 8 skipped,
  56 existing legacy datetime deprecation warnings.
- `scripts/verify-security.ps1`: PASS, 308-file secret preflight, 18 security tests,
  strict dependency audit with no known vulnerabilities.
- `git diff --check`: PASS.

AC-01 through AC-09 pass as documentary checks. AC-10's local checks pass; commit/push and
remote-SHA verification follow this recorded evidence and are reported in the completion report.
No runtime rejection mechanism is claimed by the proposal's negative review cases. Actual remote
E2E is not run in WP-14; prior WP-13 observations retain their original scope/date. Scientific
baseline confirmation remains BLOCKED despite passing document and regression checks.

## Decision review record v2

The continuation review verified feature HEAD
`3a65afd87151fc07257de1b3855692dcd9a016a1` and the version-1 package's normalized-LF
SHA-256 `58ce0aae5aa3f9cf46f65c1f1196b05663206000f52b4fc7a90fdef4f12eda9d`.
The version-1 proposal remains unchanged. A separate non-executable review artifact is stored at
`docs/decisions/WP14_VBIAS_DECISION_RECORD_V2.json`.
Its SHA-256 after UTF-8 CRLF-to-LF normalization, retaining the final newline, is
`6d0b280afb72388bb8621c7a2e66120523c20ff8a2f6e1974557133bb5a21ac9`.

The reviewed continuation request supplied no concrete VBIASN/VBIASP selection, no analysis
policy, no snapshot policy, and no new condition/revision evidence. Version 2 therefore records
only the absence of a decision; it does not select, recommend, or infer a value. All decision
fields remain unset, all execution and mutation permissions remain false, and confirmation stays
`BLOCKED_MISSING_EXPLICIT_USER_DECISION`. Passing document checks does not authorize actual bias
application, simulation, deployment, MCP changes, OA write/save, ADE-state changes, or design/PDK
changes.
