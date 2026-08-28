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

## v1.0.0 checklist

- all WP-00 through WP-11 acceptance criteria pass;
- controlled write target and mutation are explicitly approved;
- dry-run/apply equivalence and rollback pass on a copy;
- source, PDK, shared library, and ADE state fingerprints remain unchanged;
- Ruff, strict mypy, default tests, security gate, real integrations, and package verifier pass;
- package version and `__version__` are both `1.0.0`;
- release notes contain no proprietary data or secrets;
- annotated `v1.0.0` tag is pushed to the private repository;
- private GitHub release is created from the reviewed tag.

The checklist is intentionally incomplete while the design-write contract is blocked. Current
version `0.1.0` is not a v1 release.
