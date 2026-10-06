# RELEASE-READINESS-03 result

Start: `61e7b1fdaa0ac0d2415dd1eecacaaa9f506dde89` (merged PR134).
Branch: `chore/release-readiness-03`. The containing PR records its exact
candidate, archive hashes, review and final remote merge SHA/tree. Integration
is complete only when those receipts verify the tested candidate.

## Changes and decision

Documentation-only reassessment; no runtime, API, schema, dependency, version,
license, policy, simulation or existing result change. The current assessment is
[Release readiness v3](RELEASE_READINESS_V3.md). README and active state/phase
overlays link it; v2 observations remain historical.

Original-code wheel/curated sdist and an honestly scoped local stdio/reference
release are **CONDITIONALLY_READY** for preparation. Whole clone/history and a
blanket Apache claim remain **BLOCKED / LEGAL_REVIEW_REQUIRED**. Claims of complete
current desktop app qualification remain **BLOCKED_PENDING_QUALIFICATION**.
No publication is authorized. Version stays 1.0.0; v1.1.0 is conditional advice.

## Verification evidence

| Check | Result and evidence type |
| --- | --- |
| Ruff / mypy | PASS; 59 typed modules |
| Full unit suite | 2,234 PASS, 5 OS symlink SKIP, 56 warnings; 526.52 seconds |
| Contract audit | PASS; 85 current tools, exact historical declarations/schemas and registry v1–v8 |
| Security / secret / locked dependency audit | PASS; 18 security tests, one cache-permission warning, no known locked dependency vulnerabilities |
| Canonical package content | PASS; wheel 67 / sdist 68 expected files, canonical LICENSE/NOTICE/THIRD_PARTY_NOTICES, no unexpected/protected/imported content |
| Isolated installed package | PASS; CLI, three launch configuration formats with 85 tools and uninstall; SDK subprocess, no remote Cadence contact |
| Direct installed dependency rights | Five actual MIT license files reviewed; dependency-only, no copied third-party source |
| Exact local ZIP/TAR and actual GitHub ZIP/tar.gz | Required same-candidate receipts in containing PR: retained Git blobs, required install/license files and exclusion of all 181 imported files |
| Inspected GitHub ZIP product installation | Required same-candidate receipts in containing PR: fresh source without .git or imported planning, locked sync, CLI, contract and package/stdio checks |
| Current actual Codex app / new Cadence / selected deletion | NOT_RUN; no qualification inferred from SDK or synthetic tests |
| Complete Claude actual app | CLAUDE_REAL_CLIENT_UNVERIFIED / DEFERRED_BY_USER; limited PR127 history preserved |
| CI / independent review | Actual containing-PR status must be reported; unavailable checks are NOT_RUN, not PASS |

Source archive exclusion applies only to the exact inspected distributions. It
does not remove web views, clone/fork/history/bundles, old commits or old releases.
Retained external adaptations still require the separately documented rights
review. No original deletion, history rewrite or speculative relicensing occurred.
The imported historical helper integrity check is separate from product archive
installation; missing import inputs are never skipped as PASS.

## Science, resources and protection

Prior real finite-grid gain and signed supply-rail DC power remain QUALIFIED at
their exact nominal conditions. Bandwidth/step/nominal input-nulling diagnostics
remain PARTIALLY_QUALIFIED; generic Phase Margin/Offset/Slew remain unqualified
where recorded. Six actual gain/power facts have no numerical design target:
NOT_EVALUATED. This phase neither requalifies nor reruns those experiments.

Phase usage: zero simulations, result reservations, deployments and deletions.
Shared ledger: 82/500 attempts, 9,798,942,720/10,737,418,240 reserved bytes.
Existing six sweep jobs: 1,105,799 logical / 1,511,424 allocated bytes, not whole
VM usage. Seven 128 MiB reservation slots remain, but no new experiment is
activated. No elapsed ceiling is reintroduced. One conservative inspection-probe
correction of 20 is retained; prior phases' correction histories remain intact.

Whole original/ADE/PDK/vendor/jobs/replay/admission/ledger/evidence checkpoint
and 1,920 baseline private hashes must match at final premerge verification.
607 guarded source/runtime/remote/policy/import/metadata/license paths were
verified unchanged. The unrelated local stat-only OCEAN change is excluded from
the commit. Archive/build local disk usage is separate from simulation accounting.

## User outcome and next phase

Users can distinguish verified package/protocol/scientific scope from actual app,
rights and publication gates, and follow product installation from a clean source
archive without imported planning. Complete exact PR integration, report and stop.
Recommend a separately authorized current Codex read-only qualification phase;
Claude and other hosts/versions/PDKs remain deferred. No new goal, simulation,
deletion, version or publication is activated by this assessment.
