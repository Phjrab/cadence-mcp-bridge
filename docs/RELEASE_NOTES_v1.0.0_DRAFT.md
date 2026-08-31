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

V1 and V2 attempts remain preserved as incomplete evidence. A V3 clean-validation plan was
approved at SHA-256 `3362e4fc13874d4f16c78506c24ae6ebd64c882718fe57e9cb2bb60619890c87`, and runner
0.12.0 implements its fixed confirmation-gated sequence. The first V3 invocation stopped before
runtime creation or copy because preflight treated the preserved V1 `sch.oa-` auxiliary file as a
blocking recovery artifact. Read-only verification proved V1 `master.tag` selects regular
`sch.oa`; the corrected gate now preserves and fingerprints the auxiliary file. A separately
approved single corrected invocation passed V3 copy, baseline, non-mutating dry-run, backup, and
the approved property apply, then failed exact-diff verification because a baseline property also
changed. Rollback and audit were not reached, and no retry was attempted. V3 target and backup now
exist as preserved incomplete evidence; protected Source/V1/V2/PDK fingerprints remained
unchanged. A fixed read-only follow-up found exactly the baseline metadata timestamp inequality and
the approved property presence, with no property values returned or stored and all Source/V1/V2/V3/
PDK fingerprints unchanged. Conditional recovery plan SHA-256
`edb34edf04b8ef4616f2215381cedf10f7ccf3ca7dfdcc8836e01d6e9f3b2d1b` remains non-executable
and awaits separate approval. Package version remains `0.1.0`, and `v1.0.0` has not been tagged or
released.
