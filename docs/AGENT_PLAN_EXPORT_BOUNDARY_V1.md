# Agent-plan export boundary v1

Date: 2026-10-06. Baseline: `8009060edc076ccacb371c45d8f8fb3a335b150f`
(merged PR #123). Preparation status: **IMPLEMENTED_IN_REVIEW_BRANCH** at the original draft.
The completion audit below supersedes that preparation checkpoint; its original
synthetic evidence and limitations remain historical.
This is a bounded distribution-engineering change, not legal clearance, a new
execution policy or release authorization.

## Evidence and decision

`LICENSING_AUDIT_V1.md` identifies the user-provided
`CADENCE_MCP_FINAL_PROMPT_PACKAGE` imported by PKG-INTEGRATE-01. The integration
manifest records 178 imported files, 177 byte-identical files and the adapted
`tools/verify_package.py`. It records integrity/provenance, not a confirmed
license grant for every imported item. Existing root authority also preserves
that planning package and its historical work-ID references.

The user requested that this directory's distribution issue be handled while
remaining development instructions are prepared. Choose the reversible,
non-destructive boundary: preserve the imported directory, notices, hashes and
Git history; exclude the directory from newly generated Git archives whose
selected commit contains these rules. Do not infer ownership from AI assistance,
user upload, public visibility or the existing root Apache license.

The new `docs/.gitattributes` sets `export-ignore` for `agent_plan` and all of its
children. It does not alter the root attributes or line-ending rules. No imported
file is deleted, moved, modified, relicensed or copied elsewhere. Runtime code,
MCP interfaces, remote helpers, policies, simulation data and package version
remain unchanged. Curated wheel/sdist exclusions remain unchanged.

## Exact meaning and limits

Git documents that export-ignore omits matching files/directories from archives.
GitHub documents that its source snapshots use git archive. Nevertheless, an
exact proposed candidate's **GitHub-generated ZIP and tar.gz must be downloaded
and inspected**, not inferred from a local unit test or documentation alone.

This boundary does NOT:

- hide the directory from GitHub browsing, clones, forks or Git bundles;
- change older tags/commits or already downloaded archives;
- establish imported ownership, permission or a blanket Apache grant;
- exclude copies or derived imported content outside the named directory;
- authorize release publication or clear unrelated qualification gates.

`LEGAL_REVIEW_REQUIRED` therefore remains the rights status for the preserved
import. An exact archive can separately earn `IMPORT_EXCLUDED_VERIFIED` after
actual member/content inspection. These statuses must not be conflated. A public
clone/full-history bundle remains a different distribution scope. Confirmed
unauthorized material would require separate remediation; this exclusion alone
would not resolve that issue.

## Validation performed in preparation

Five standard-library tests were run successfully under Linux using disposable
synthetic Git repositories and the exact proposed docs/.gitattributes bytes:

1. TAR excludes only the imported subtree and preserves other payload bytes.
2. ZIP has the same bounded exclusion and retained payloads.
3. All synthetic imported files stay tracked and byte-identical.
4. Uncommitted attribute edits do not rewrite the committed archive boundary.
5. Removing the rules makes the import reappear (negative control).

Run with:

```text
python tests/unit/test_agent_plan_export_boundary.py -v
```

Synthetic fixtures are newly authored test strings, not copies of imported
material or Cadence data. No network, simulator, source mutation or data deletion
is used by these tests. They do not prove whole-repository or GitHub-hosted
archive acceptance. The full checkout could not be downloaded in the preparation
environment; no full-suite, Windows, packaging, Cadence or hosted-archive PASS is
claimed. This is why the change is a draft review checkpoint, not merged evidence.

## Required completion in the existing operator environment

At the next normal work boundary, continue this same change rather than open a
duplicate implementation:

1. Fetch the review branch and latest main; preserve unrelated changes and all
   historical imported files. Inspect the exact diff and existing policy.
2. Check direct/runtime/test references to agent_plan and any redistributed
   duplicates/derivatives outside it. Archived full prompts can contain copies;
   do not clear their rights by path matching alone.
3. Run new tests plus current applicable lint, type, security, contract,
   distribution and documentation gates. Preserve original runtime byte identity;
   no Cadence simulation is necessary for this export-only change.
4. Inspect local committed-tree ZIP/TAR and actual GitHub ZIP/tar.gz for the exact
   review head. Require zero docs/agent_plan members (including nested originals,
   archive copies and helper), retained required original source/notices, and no
   unexpected omissions. Verify before any publication.
5. Keep archive installation instructions usable without imported planning.
   Historical ICF/work-ID/package-integrity checks require the preserved reviewed
   checkout; do not fabricate a PASS or weaken a missing-file security gate to
   make an exported archive look like that checkout.
6. Update current README, THIRD_PARTY_NOTICES, release-readiness overlay,
   PROJECT_STATE and phase plan to distinguish verified archive exclusion from
   unresolved rights. Preserve dated audit evidence; do not erase old findings.
7. Complete review and merge only under the existing policy and passing gates.
   Recheck exact remote identity. No direct main write, force push, history rewrite,
   tag, release, index upload or license change is authorized by this document.

If exact GitHub archives retain the directory or external copies lack rights,
keep the relevant distribution gate blocked. Do not announce release readiness.
A later narrowly scoped removal/replacement proposal can be considered without
rewriting history or treating archival evidence as disposable.

## Sources

- Repository: `docs/LICENSING_AUDIT_V1.md`,
  `docs/agent_plan/INTEGRATION_MANIFEST.json`, `AGENTS.md` at the pinned baseline.
- Git attributes: https://git-scm.com/docs/gitattributes#_export_ignore
- GitHub source archives:
  https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives

The underlying rights uncertainty is not a finding of infringement. No legal
conclusion is made about the imported package beyond the existing audit evidence.


## Completion audit on the continued PR #124

Current starting main is `20726ead871ffda18a937938fed7c4a6426d5b5d`, merged
ANALOG-POWER-01 #125. The same `chore/agent-plan-export-boundary-01` branch
is continued with a normal main merge. No duplicate implementation PR is made.
Current scope is distribution engineering only; power extraction is already
complete, while generic power discovery/specification binding remains pending.

### Dependence, copies and rights

The continued checkout has 181 tracked files under `docs/agent_plan`: the
178 imported package files plus three integration records. They and their
Git blob identities remain unchanged. The 178/177 figures in the import manifest
are historical import counts, not a count of every current file in the folder.
No runtime, build, deployment or product unit test imports the planning helper.
The archive verifier/new synthetic tests mention the exclusion, and distribution
rejection tests deliberately use fictional import paths; these are original tests.

External references remain in AGENTS/root execution policy, PROJECT_STATE,
current/historical planning and licensing documentation, and the two
`docs/decisions/WP14_VBIAS_DECISION_*` records. Those decision records cite
historical planning assumptions; they do not supply runtime inputs. Root
execution policy also documents its prior integration/adaptation of the imported
planning constraints. These references and adaptations are not relabeled as
independently licensed import content. No complete normalized-byte duplicate or
identical paragraph of at least 250 normalized UTF-8 bytes was found outside
the directory in the current tracked-file comparison. That limited comparison
cannot establish authorship or absence of paraphrased derivatives. Rights review
must include the preserved import and any affected external adaptations;
`LEGAL_REVIEW_REQUIRED` remains. No infringement conclusion is made.

`docs/archive/CODEX_MASTER_PROMPT_pre_PKG-INTEGRATE-01.md` is the project's
pre-integration root contract preserved by the manifest. Other root/archive
prompts and prior phase reports remain historical evidence; export-ignore does
not grant them new rights or erase them. No imported material is copied out to
make an archive self-contained. No license, original, history or past result is
modified. The current boundary proves omission of the named import subtree only,
not legal clearance for every retained document.

### Historical package checks versus product installation

The imported `tools/verify_package.py` checks its historical manifest, checksums,
planning/catalog/link graph and `archive/LEGACY_INPUTS.zip`. That original ZIP
was intentionally never committed. Its actual invocation in the full reviewed
checkout is recorded separately; missing required historical inputs remain a
failure, never a waived check or current product-installation PASS. Do not add
that ZIP or weaken its integrity validator for this phase.

For a source-archive user:

1. Choose an exact inspected commit ZIP/tar.gz and unpack into a fresh directory.
2. Run `uv sync --all-groups`, then `uv run cadence-mcp-bridge doctor` and the
   [local onboarding guide](ONBOARDING_CLI_V1.md). Doctor validates local bridge
   requirements; SSH/Cadence qualification and execution need their own contracts.
3. Run `pwsh -NoProfile -File scripts/verify-package.ps1` for the curated build,
   distribution audit, isolated installed CLI/stdio and uninstall gate. It does
   not require the imported historical helper or `.git`.
4. Development lint/type/unit commands remain available. On Windows, use
   `uv run python -m pytest tests/unit` so project-root `scripts` imports resolve.
   The initial console-script invocation's collection failure is preserved;
   no test is removed to achieve a PASS.
5. Historical ICF/package-integrity work and the Git-enumerated secret preflight
   require the reviewed checkout and preserved inputs. Their absence in a ZIP
   is not an installation error, a passed historical audit, or permission to
   bypass a fail-closed gate. The export audit compares all retained Git blobs
   after checkout secret verification; curated distribution scanning is separate.

### Repeatable exact-candidate archive inspection

`scripts/verify-git-archive.py` is an operator-only read-only audit, not an MCP
API. It requires an exact 40-character commit and locally downloaded/generated
archive files, rejects unsafe paths/links/duplicates/expansion, and reads without
extraction. It requires every candidate regular file outside the imported
subtree, exact blob-content identity, original source, dependency metadata and
LICENSE/NOTICE/THIRD_PARTY_NOTICES. Unexpected omissions/additions fail. It
makes no network, Cadence, execution, rights or publication assertion.

```powershell
git -c core.autocrlf=false -c core.eol=lf archive --format=zip --output=candidate-local.zip EXACT_COMMIT
git -c core.autocrlf=false -c core.eol=lf archive --format=tar --output=candidate-local.tar EXACT_COMMIT
# Separately download GitHub-generated zipball/tarball at that same commit.
uv run python scripts/verify-git-archive.py --commit EXACT_COMMIT --archives candidate-local.zip candidate-local.tar candidate-github.zip candidate-github.tar.gz
```

Store downloads/evidence outside tracked release payloads. Windows auto-CRLF settings must be disabled for canonical local snapshots;
otherwise Git export may convert retained text bytes. The first real local
archives failed exact blob comparison on 243 CRLF-only files; both failed
artifacts are preserved, and the canonical commands above passed without
weakening the verifier. Hosted archive bytes
may change compression independently; retained candidate blobs must still match.
Exact hashes, commit, URLs and verification outcomes are preserved privately.
Future tags/candidates must be inspected again. Old snapshots do not inherit
the new attributes. Tests/builds of an actual hosted snapshot are distinct from
synthetic Git fixtures and from SDK subprocess or actual app/Cadence evidence.

### Completion evidence

At inspection checkpoint `6c185dc6ebcb77041e7d5b03ade4fa929f789c06`, all four
canonical local ZIP/TAR and actual GitHub ZIP/tar.gz snapshots pass complete
member/blob comparison: 181 import files excluded, 680 retained files identical,
5,468,915 retained file bytes. Original source/lock/schemas/examples/tests and
canonical LICENSE/NOTICE/third-party notices remain. This is
`IMPORT_EXCLUDED_VERIFIED` for those inspected snapshots only. Final reviewed
head snapshots are inspected again and recorded privately before integration.

An actual GitHub ZIP was unpacked outside the checkout, with no `.git` or
`docs/agent_plan`. Its dependency sync, local doctor, contract audit, 64 focused
archive/distribution/contract tests and full canonical package gate pass. The
latter builds/audits wheel and sdist, verifies three exported installed stdio
formats with 72 tools, unqualified execution denial, CLI and uninstall. These
are synthetic/config/SDK subprocess checks, not new actual-app or Cadence E2E.
Both checkout and hosted-source builds have 56 wheel / 57 sdist members, expected
Apache notices and zero unexpected/protected-pattern findings. Final reviewed
archive installation is checked against that same candidate after completion
documentation. Whole-repository full gate completion and exact integration are
recorded in the containing PR #124 and new private phase records.
Publication remains `PUBLICATION_NOT_AUTHORIZED`. No simulation, reservation,
remote deployment/contact, result deletion, client-config write or tag/release
is part of this phase. Existing power/AC/TRAN/sweep evidence can be reused only
because source/remote/contracts remain identical; this phase makes no new
scientific measurement or actual Desktop-app claim.


Final checkout gates: **1,783 passed / four OS symlink skips / 56 warnings /
616.85 seconds**; new archive tests11; Ruff PASS; mypy48 source modules PASS;
contract audit72 schemas/22 legacy declarations/v1-v7 schemas PASS; secret
preflight861 files PASS; security18 PASS; locked audit no known vulnerabilities.
Two bounded verification corrections are counted against the active20 ceiling:
console-entrypoint import handling and Windows local archive line endings.
The initial collection ERROR and initial local archive FAIL remain private;
canonical verification does not turn them into a historical PASS. Existing
historical package checker remains **NOT_PASS** for its missing required ZIP.
No product or security test is skipped because the planning directory is omitted.
Four existing symlink tests remain OS SKIP and are not counted as passed.
Changed current Markdown visible links/fences pass; historical imported graph
and license ownership are separate, uncompleted checks.

Source/remote/import, policies/contracts and all1,304 prior top-level private
records retain their baseline identity. Current limits remain500 attempts/10 GiB/
20 corrections with removed elapsed ceiling and prior usage histories intact.
This phase consumes zero Spectre, reservations or remote storage and makes no
Cadence contact; last verified counters62/500 and7,114,588,160/10,737,418,240 bytes
are reused, not represented as a new whole-VM disk measurement. Local archive,
fixture/build and audit bytes are distinct from simulation-result reservations.
All historical source/ADE/PDK/native/replay evidence stays protected; no result
is deleted or reclassified. No fresh real-app or scientific measurement is made.

Complete integration through existing PR124 with a manual exact-head scope,
security/contract/diff review and actual GitHub check/review-state inspection.
No configured CI is not a CI PASS. Verify final archive/install outcomes and
main SHA/tree privately; no follow-up state-only PR is needed. Archive exclusion
is **IMPORT_EXCLUDED_VERIFIED**, preserved rights **LEGAL_REVIEW_REQUIRED**, new
publication **PUBLICATION_NOT_AUTHORIZED**. Other products retain their terms.

Next recommendation: finish the remaining expanded ANALOG-POWER-01 objective
through **MEAS-CONTRACT-02**, binding the already qualified dc-supply-power-v1
result into versioned generic measurement/specification paths while preserving
old definitions/goals and targetless NOT_EVALUATED behavior. This is not a repeat
of completed current extraction, and it is not activated by this report. Then
consider the separately confirmed bandwidth/PM/slew/offset/range/real-sweep/spec
roadmap. Other Cadence/PDK/host and actual Claude testing stay deferred.
