# WP-14 Package-Bound Narrow Deployer Implementation

Date: 2026-09-17 (original implementation: 2026-09-16)

Status: REPOSITORY_HARDENING_LOCALLY_VERIFIED_REMOTE_NOT_AUTHORIZED

The exact operator-only entry point remains scripts/deploy-wp14-narrow.ps1, with no custom
arguments or MCP surface. It preserves the eleven assets, two bound plans and immutable package
7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87.
The broad deployment gate remains deployment_enabled=false.

The historical escape correction and original control gaps are preserved in
WP14_NARROW_DEPLOYER_CORRECTION_REVIEW_V1.md. They are not rewritten as historical successes.
The separately approved repository hardening, closed V2 authorization/consumption contract,
local test strategy and remaining trust assumptions are documented in
WP14_NARROW_DEPLOYER_HARDENING_V1.md.

## Current control boundary

- PowerShell 7.5+, fixed Windows OpenSSH executable paths and strict-host-key argv.
- V2-only closed, bounded authorization schema binding exact package/deployer, executor,
  validity window, reviewed identity and all eleven remote preimages.
- Unknown hashes/identity fail closed before transport; no inference from old git blobs.
- Fixed identity, ownership/type/link/mode/hash checks before old runner execution,
  repeated preimage checks before backup/overwrite, copied-backup hash verification.
- A shared 300-second monotonic execution budget, concurrent stdout/stderr reads with
  combined 65,536-byte per-call limit and owned local transport termination on failure.
- Durable package-wide consumed claim before first transport, plus exclusive operation lock.
  A failed or uncertain attempt is not retryable; a new authorization ID does not reset it.
- Fixed non-overwriting snapshot, eleven atomic per-file installs, exact post-install checks,
  individual shell syntax checks, Python syntax, runner version and fixed command-surface checks.
- No Cadence/discovery/simulation, design access, remote cleanup, automatic rollback or retry.

## Authority and evidence

No V2 activation record has been created. The original approval audit remains historical,
unchanged and unusable for this script hash. No actual remote operation was performed.
Tests use temporary fixtures, synthetic records and a local fake process only. They validate
control behavior, not current VM identity, real snapshot recovery or actual OpenSSH compatibility.
Remote readiness remains blocked pending review/integration, reviewed fresh preimage evidence
and separate exact-hash stage authorization. Discovery requires a distinct later grant.
