# Cadence MCP Bridge v1.0.0 — Draft Release Notes

Status: **not released**. This draft must not be used to create a tag or GitHub release until the
WP-11 controlled-write acceptance gate passes.

## Planned v1 capabilities

- Windows-local MCP SDK v2 stdio server with a closed typed tool surface;
- strict Windows OpenSSH transport to a fixed CentOS 6.5 runner;
- asynchronous Spectre job lifecycle, bounded logs/results, cancellation, audit, and recovery;
- metadata-only allowlisted Cadence discovery;
- reviewed synthetic and actual ADE simulation profiles;
- versioned deterministic synthetic ADC measurement contracts;
- copy-only, explicitly approved design mutation with dry-run, backup, verification, and rollback.

## Security boundary

The release contains no generic shell, arbitrary SSH, arbitrary SKILL/OCEAN evaluation, caller
path, raw netlist, PDK content, raw PSF, credential, or license value interface. PDK, shared, and
source design libraries remain read-only. Only a separately allowlisted work-library copy may be
eligible for a predefined mutation.

## Blocking release evidence

The write contract and explicit approval were supplied, and the approved destination copy was
created. The real sequence stopped before dry-run completion on a legacy IC6.1.5 property-query
API mismatch, so apply, backup, rollback, and baseline-restoration evidence do not exist. The
destination now exists and the policy forbids overwrite. Package version remains `0.1.0`, and
`v1.0.0` has not been tagged or released.
