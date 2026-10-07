# Operator state preservation and public verification

The fixed bootstrap installs immutable content directories and retains partial
candidates. Initial activation and append-only deactivation are available;
active-pointer replacement and live migration are refused. Staging another
manifest does not replace the selected runner, delete old bytes or change
accounting. Native trust/identity/ledger checks remain mandatory before execution.

Operator state belongs outside site-packages. Runtime settings select existing
operator journal parents and a shared resource-state directory. No implicit move
or reset of a legacy package-relative journal is performed. Keep original OA/ADE,
PDK, results, replay, audit, authority history and ledgers backed up using the
operator's existing process before any separately reviewed migration.

The current migration capability is deliberately unsupported. Do not implement
rollback by deleting an active marker, replacing the pointer or creating a fresh
budget database. Preserve failed candidates and unresolved jobs, record their
identity and involve the operator before a reviewed repair. A future migration
must verify both versioned schemas and immutable identities, back up original
state and recover partial transitions. N-to-N+1 and downgrade acceptance remain
NOT_TESTED until actual distinct qualified version candidates exist.

The package verifier installs a curated wheel in an isolated environment, runs
three SDK configuration profiles and operator context 1-to-2-to-1 restart, then
uses only installed fixed bootstrap assets. It creates synthetic original/replay,
shared-ledger sentinel, durable legacy and generic lifecycle analysis history and SweepStore state outside
the package. Content repeat, staging, rejected activation, partial candidate
preservation and deactivation are exercised. Exact file hashes survive a
same-version reinstall and uninstall. These checks are synthetic and do not
qualify native migration or semver upgrade. The verifier cleans only its newly
created disposable local temporary workspace; it never visits operator storage.

Fresh operator Storage, destructive deletion, job cancellation and native result
access remain disabled behind RUNNER_SETUP_REQUIRED. Existing legacy Storage
and old results retain their original policy. No general phase or remaining-space
approval is consent to delete an old result. A future destructive capability needs
exact item selection/plan hash, independent operator consent and disposable native
Linux end-to-end evidence. Active simulator termination is unsupported; no global
process kill or stale-lock removal is exposed.

Public CI uses windows-2022 / Python 3.12.10 / uv 0.12.6, locked dependencies and
contents:read. Checkout v4.2.2 and setup-uv v6 are full-SHA pinned. Their manifests,
checkout credential handling and uv setup/download paths were inspected; the
Windows uv binary checksum is pinned from its GitHub release asset metadata.
Credentials are not persisted, dependency caching is disabled and no artifacts
are uploaded. PR code runs only on disposable GitHub-hosted machines without
Cadence, PDK, SSH/license secrets or access to the registered VM. There are no
pull_request_target, workflow_run or self-hosted triggers. Branch protection,
workflow administrator settings and publication are unchanged.

Local lint/type/unit/security/contract/package evidence and actual hosted run
results must be reported separately. A new workflow file is not a green CI run.
Actual Cadence trust, license checkout, two new circuits and client submission
remain operator-local acceptance gates. Generic release remains BLOCKED.
