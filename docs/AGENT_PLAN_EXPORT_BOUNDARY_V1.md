# Agent-plan export boundary v1

Date: 2026-10-06. Baseline: `8009060edc076ccacb371c45d8f8fb3a335b150f`
(merged PR #123). Status: **IMPLEMENTED_IN_REVIEW_BRANCH**; repository-wide
acceptance, exact GitHub archive verification and integration remain pending.
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
