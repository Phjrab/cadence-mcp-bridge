# Controlled Design Write Policy

## Current status

WP-11 design writes are **blocked**. Read-only discovery found only `MyDesignLib` and
`MyFirstDesign`; both are source libraries and neither has been designated as a dedicated writable
work library. No write MCP tool, runner subcommand, SKILL mutation, destination path, approval
token, backup, or rollback operation is enabled. The public MCP surface therefore remains exactly
twenty tools.

## Permanent protections

- PDK libraries, including `gpdk090`, are permanently read-only.
- shared Cadence libraries such as `analogLib` and `basic` are permanently read-only.
- reviewed source libraries `MyDesignLib` and `MyFirstDesign` remain read-only.
- the original cellview and ADE state must never be modified.
- arbitrary paths, file contents, SKILL/OCEAN text, and generic shell/SSH commands remain forbidden.

`write_policy.py` implements a fail-closed readiness gate. It classifies the known protected and
source library names and rejects every write request while `work_library` is unset and the allowed
mutation set is empty.

## Required contract before resuming WP-11

The user must provide and explicitly approve all of the following together:

1. dedicated work library name and its approved location;
2. exact source library/cell/view and destination copy cell/view;
3. one predefined mutation, its typed parameters, and expected post-save verification;
4. backup location and retention rule inside the approved project boundary;
5. rollback success criterion;
6. explicit authorization to execute that named mutation against the copy.

After those inputs are reviewed, the implementation must add a fixed remote registry, copy-only
dry-run, one-time confirmation bound to a canonical plan hash, atomic manifest/backup creation,
post-save verification, and rollback. Dry-run and apply must consume the same immutable plan, and
the source hash must be rechecked immediately before apply. Any mismatch must fail closed.

## Release gate

`v1.0.0` must not be created until a real approved copy has passed dry-run/apply equivalence,
backup restore, all local/security/integration tests, install/uninstall verification, and design
source/PDK immutability checks. No tag or GitHub release was created in the blocked state.
