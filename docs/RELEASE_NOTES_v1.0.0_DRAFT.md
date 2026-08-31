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

A later separately approved, three-object, exact-value read-only forensic classified V3 as
`SAFE_ROLLBACK_CANDIDATE`. Source and backup exactly match at eight cellview properties and all
three objects match structurally at 35/14/8. The target differs only by approved
`mcpMutationTest=validated-v1` and the OA-maintained `schGeometryLastUpdated` change from 107168 to
107169. No rollback occurred. The new exact conditional plan SHA-256 is
`eb057da2a866b92be5e1474bc3d06aba05f6ae49b5001465dd65ed9921afc911`; it remains non-executable,
undeployed, and pending separate approval. The original validation manifest, audit, and runner job
record remain missing, so the release gate stays failed.

An explicitly approved rollback attempt later stopped before Cadence startup because its bounded
evidence parent directory was absent. No design write, manifest, or rollback audit occurred; all
three protected fingerprints remained unchanged. The evidence-root setup is corrected in source
but was not redeployed or retried. V3 rollback therefore remains incomplete and the release gate
continues to fail.

A separately approved corrected-runner retry used fresh run ID
`575356ae-1853-409f-a913-25c1ba9038a8` and completed `V3_ROLLBACK_VERIFIED`. All 15 rollback
acceptance criteria passed: the target was restored from the fixed backup by removing only the
approved mutation and restoring the single OA-maintained baseline property; topology and logical
structure hashes were unchanged, and Source and backup remained immutable. An immutable manifest
and 14-stage audit record were verified. This successful recovery preserves the failed V3 evidence
but does not make the earlier clean validation pass. V4, tag, and release remain unstarted and
require a separately reviewed clean-validation plan and explicit approval.

That planning gate is now represented by non-executable V4 plan SHA-256
`c5b2f418c5a76bfe54adc24c2ee947a33d904122b404bba323706dfbe3cbdd66`. It fixes new V4 target and
backup names, preserves all earlier evidence, and defines 18 stages and 18 acceptance criteria,
including a separate bounded check for the Cadence-maintained metadata transition observed in V3.
After separate approval bound to that exact plan hash, runner 0.16.0 executed V4 run
`e636eeba-80dc-4280-b2ea-4f23b0cd1139` exactly once. All 18 criteria passed, including non-mutating
dry-run, fixed backup, exact semantic/metadata diff, rollback, complete baseline restoration,
immutable manifest, bounded audit, and Source/PDK/prior-evidence immutability. The actual apply
contained only `mcpMutationTest=validated-v1` and the bounded OA metadata transition from `107168`
to `107169`; rollback removed the mutation and restored the prior property hash. Manifest SHA-256
is `e7b306db74fe28040584b39e94b980709d61aa8a19e78ad0987ab688d1e9db7b`. No retry, cleanup,
tag, or release occurred. The package remains version `0.1.0` pending reviewed branch integration
and separately authorized final release preparation.
