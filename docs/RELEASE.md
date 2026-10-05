# Packaging and Release

## Current public readiness, 2026-10-05

The repository is public and v1.0.0 was published on 2026-08-31. Its tag peels
to `8a0d44fab90e2095cc39322baef60fc09d741cd6`. The GitHub release body and
versioned v1 notes retain stale candidate wording; the historical notes and
published release are preserved. Post-v1 main has 48 tools and the local
onboarding workflow, whereas the published tag has 22. Package/runtime/lock
metadata remain 1.0.0. See [current readiness](RELEASE_READINESS_V1.md) and
[proposed next release notes](RELEASE_NOTES_NEXT.md).

The owner selected Apache-2.0 for original bridge source in RELEASE-LICENSE-01.
See [licensing audit](LICENSING_AUDIT_V1.md), [LICENSE](../LICENSE),
[NOTICE](../NOTICE) and [third-party boundaries](../THIRD_PARTY_NOTICES.md).
Cadence/PDK/client/dependency terms remain separate. Imported planning rights
are LEGAL_REVIEW_REQUIRED and that material is excluded from package artifacts;
a blanket whole-repository Apache distribution is not approved. Exact candidate
and separately scoped publication remain outstanding. This preparation changes
no version, historical tag/body or GitHub release.

## Reproducible package verification

Run from Windows PowerShell:

```powershell
.\scripts\verify-package.ps1
```

The verifier builds the project into a unique system-temporary directory, creates an isolated
Python 3.12 environment, installs the wheel, checks metadata/runtime/CLI versions,
then runs isolated installed-package onboarding and actual stdio for both client
formats. It verifies all 48 tools, preservation of 22 legacy names, configured
catalogs and denial before admission for the unqualified fictional design.
No Cadence transport or simulation occurs. The verifier uninstalls the package, proves
the module is no longer importable, and removes only its validated temporary directory.

## Operator install

1. Install Python 3.12 and `uv` on Windows.
2. Clone the public repository and select a reviewed commit/tag. The v1.0.0 tag
   has only the historical v1 capabilities; current onboarding requires a reviewed
   post-v1 commit until a new release exists.
3. Run `uv sync --frozen --all-groups`.
4. Run `scripts/verify-security.ps1` and `scripts/verify-package.ps1`. Actual
   Cadence execution needs qualified registered operations, private delegation
   and resource reservation; installation is not simulation authority.
5. Follow [operator onboarding](ONBOARDING_CLI_V1.md) for private registration,
   joined verification and explicit client settings. The legacy installer remains
   the fixed-reference installation path.
6. Restart Codex Desktop and verify the exact reviewed tool allowlist.

## Upgrade

1. Preserve the existing Codex configuration and remote audit/job data.
2. Fetch the public repository and review the actual target commit/tag and notes.
3. Run `uv sync --frozen --all-groups` and all verification gates before deployment.
4. Use only the applicable reviewed deployment contract if changed remote bytes
   require it. A profile or new package never grants deployment authority.
5. Verify effective settings and integrity, reuse preserved results where appropriate,
   review/update explicit client settings, then restart Codex Desktop.

## Uninstall

1. Close Codex Desktop.
2. Restore the newest installer-created Codex configuration backup, preserving unrelated entries.
3. Remove only the `cadence-mcp-bridge` Python environment or checkout selected by the operator.
4. Do not delete remote jobs, audit records, design libraries, PDK data, or Cadence installation
   files as part of uninstall.
5. Any future remote application-root removal requires a separate retention decision and explicit
   operator approval.

## Historical v1.0.0 release-candidate checklist

- [x] WP-00 through WP-10 are integrated and their acceptance evidence passes.
- [x] The controlled-write target and sole mutation were explicitly approved.
- [x] V4 dry-run/apply equivalence and backup rollback passed on the approved copy.
- [x] Source, PDK, shared libraries, ADE state, and preserved V1/V2/V3 evidence remained unchanged.
- [x] Ruff, strict mypy, default tests, the security gate, all real integrations, and the package
      verifier pass on the release-preparation branch.
- [x] `pyproject.toml`, package `__version__`, `uv.lock`, and installed CLI report `1.0.0`.
- [x] Final release notes contain no proprietary data, raw design content, credentials, or secrets.
- [x] The `wp/WP-11-v1-release` branch was reviewed and integrated through explicitly approved
      PR #13 as merge commit `8a0d44fab90e2095cc39322baef60fc09d741cd6`.
- [x] Annotated tag `v1.0.0` was created from that exact reviewed main commit and pushed to the
      private repository under separate authorization.
- [x] The stable GitHub release was published from that exact tag in the private repository under
      separate authorization.

Version `v1.0.0` is published. The annotated tag peels to
`8a0d44fab90e2095cc39322baef60fc09d741cd6`, and the private-repository release is available at
`https://github.com/Phjrab/cadence-mcp-bridge/releases/tag/v1.0.0`.
