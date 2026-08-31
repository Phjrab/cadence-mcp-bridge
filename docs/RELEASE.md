# Packaging and Release

## Reproducible package verification

Run from Windows PowerShell:

```powershell
.\scripts\verify-package.ps1
```

The verifier builds the project into a unique system-temporary directory, creates an isolated
Python 3.12 environment, installs the wheel, checks the CLI version, uninstalls the package, proves
the module is no longer importable, and removes only its validated temporary directory.

## Operator install

1. Install Python 3.12 and `uv` on Windows.
2. Clone the private repository and check out a reviewed release tag.
3. Run `uv sync --frozen --all-groups`.
4. Run `scripts/verify-security.ps1`, `scripts/verify-package.ps1`, and the documented E2E suite.
5. Register the MCP server with `scripts/install-codex-mcp.ps1 -Confirm`.
6. Restart Codex Desktop and verify the exact reviewed tool allowlist.

## Upgrade

1. Preserve the existing Codex configuration and remote audit/job data.
2. Fetch the private repository and review the target signed/reviewed tag and release notes.
3. Run `uv sync --frozen --all-groups` and all verification gates before deployment.
4. Deploy only through `scripts/deploy-remote.ps1 -Confirm` when the release changes reviewed
   remote files.
5. Re-run the E2E suite and registration script, then restart Codex Desktop.

## Uninstall

1. Close Codex Desktop.
2. Restore the newest installer-created Codex configuration backup, preserving unrelated entries.
3. Remove only the `cadence-mcp-bridge` Python environment or checkout selected by the operator.
4. Do not delete remote jobs, audit records, design libraries, PDK data, or Cadence installation
   files as part of uninstall.
5. Any future remote application-root removal requires a separate retention decision and explicit
   operator approval.

## v1.0.0 release-candidate checklist

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
