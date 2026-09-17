# WP-14 public visibility contract review v1

Record kind: documentation_review_not_execution_authorization
Status: READY_FOR_REVIEW
Date: 2026-09-17
Repository: Phjrab/cadence-mcp-bridge
Base main: d9b0916a84e17b958a049810aa01b7c9e59a2025

## Decision and existing user authority

Public repository operation is already explicitly approved by the user: "저장소는
public으로 계속 진행", followed by the PR #30 and PR #31 instructions to maintain
public visibility. No further permission to keep the repository public is needed.
GitHub reports PUBLIC at preparation time. Reverting visibility is not the proposed solution.

The proposed reconciliation replaces the obsolete private-only repository prerequisite
with the user's public policy while retaining protected-data restrictions and explicit
operation approval. Repository visibility neither grants SSH authority nor proves that
an individual evidence artifact is suitable for publication.

This review specifies the complete bounded correction for a later repository-only change.
It does not modify the existing hash-bound packages or their consumers. Until that
correction is implemented and verified, the old contract mismatch is a migration task,
not an outstanding request for the user to approve public visibility again.

## Verified provenance and immutable inputs

PR #31 merged reviewed head 05b134d6e52538637bd241607e3d94e5f958de4a into
d9b0916a84e17b958a049810aa01b7c9e59a2025. This is the fetched latest origin/main.
The following normalized-LF SHA-256 bindings must be preserved in this documentation run.
Paths are repository-relative.

| Input | SHA-256 |
| --- | --- |
| docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE_V1.json | 1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb |
| docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_SINGLE_USE_APPROVAL_PACKAGE_V1.json | 648409527484c75b67df50c27eccc4a8e28ce22921750592ab6517b135676b9f |
| docs/approvals/WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE_V1.json | 7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87 |
| scripts/collect-wp14-remote-preimages.py | 598d95e785ccdb2c7f711989f7f7036740425f2f5da465b1695bbda87cf61daa |
| scripts/deploy-wp14-narrow.ps1 | 227b1c0d3831e7de8f974192d7da9434276ee5a25c2448a6f5ad87922e9e0b17 |

## Conflict inventory and proposed replacements

| Location | Current statement | Bounded future correction |
| --- | --- | --- |
| Root CODEX_MASTER_PROMPT.md heading and current Git/definition-of-done language | Private repository | Add a dated post-v1 public-policy overlay; preserve historical WP-00 through WP-11 and release evidence. |
| Evidence collection package v1 repository_binding.visibility_required and fail_closed_conditions | private / reject non-private | New version fixes the repository identity and public visibility; reject unknown repository identity or unchecked publication contents. Preserve v1 verbatim. |
| Single-use request v1 repository_provenance, gate sequence, AC-06, review notes and next_gate | Restore private before activation | New version recognizes existing public approval and requires exact artifact bindings and a later explicit one-attempt operation grant. Preserve v1 verbatim. |
| Deployment request v1 repository_binding and fail_closed_conditions | private / reject non-private | New version changes only repository visibility policy and version/provenance references; eleven assets, modes and all execution limits remain fixed. No deployment authority is granted. |
| PROJECT_STATE.md visibility gate and blockers | Public state itself blocks collection | Record public policy as approved and contract migration pending until all active consumers and references are reconciled. |

`private_stream` and private local/remote file permissions describe data handling, not
GitHub visibility. They must not be replaced by a global private-to-public text substitution.
Historical records, archives, decision v1-v4 and V1-V4 validation evidence remain immutable.

Static inspection of `_assert_package_boundary` in the current collector finds hash,
package identity, authority flags, allowlist and lineage checks, but no live GitHub
visibility query. The private prerequisite is a documentary/operator gate; this review
does not falsely claim a runtime visibility rejection was observed. The collector was
not executed. Its compiled repository_main_commit is e60ab270a5e002256f8c5bbf6b81e54f65c10a31,
a historical binding, not a measurement of latest main.

## Concrete follow-up scope and dependency order

1. Preserve all three v1 packages. Produce versioned v2 request documents with explicit
   supersedes links and the public-policy replacements above. These are requests only;
   do not create any file at an executable AUTHORIZATION path.
2. Update the current root contract and current-phase references with the dated public
   overlay, keeping Git discipline, security boundaries and historical completion intact.
3. Rebind the narrow deployer to the versioned deployment request, then calculate its
   new hash. Rebind the collector to the versioned collection/deployment requests and
   new deployer hash, then calculate its new hash. Finalize the versioned single-use
   request against that collector hash. Avoid circular/self-hash dependencies.
4. Document whether the historical repository commit binding is retained or deliberately
   revised; make all code, fixtures and requests agree. Never silently substitute latest main.
5. Preserve the eleven-asset allowlist and byte content, operator-only/no-argument entry,
   exact remote identity/root, strict host-key checking, closed schema, executor/time
   binding, 60-second/32768-byte collection limits, concurrency one and no retry.
   Keep deployment_enabled=false and scientific baseline unconfirmed.
6. Preserve durable one-use history across package-hash changes. A new hash must not
   silently reset eligibility: recognize existing claims for predecessor packages or
   stop for review. Do not delete, rewrite or create a real operator ledger in local tests.
7. Run isolated temporary-fixture/fake-transport success and negative tests for old-hash
   authority rejection, tampered packages, publication-sensitive output, timeouts,
   concurrency and predecessor claims. Do not run production entry points or SSH/SCP.
8. Report new exact hashes and reviewable code before any subsequent remote operation.
   This current run approves only documentation preparation; implementation is not
   performed here. Later operation authorization remains separate from repository review.

## Public data handling and remaining gates

Only reviewed source, synthetic fixtures and sanitized documentation belong in public Git.
No credentials, license values, key material, MachineGuid, raw runtime authorization,
PDK content, OA/ADE data, netlists, waveforms or unrestricted logs may be published.
An executor commitment is not permission to publish its source identity or active grant.
Future fresh evidence must remain local until its exact closed fields have been reviewed
for publication. Existing metadata publication does not automatically authorize new payloads.
Secret scans supplement that review; they do not prove absence of proprietary information.

No fresh remote identity, preimage, condition or freshness fact is established here.
Public policy approval leaves collection authorization, fresh reviewed preimages,
deployment Authorization V2, discovery invocation and scientific approval unresolved.
VDD=1.0 V, VCM=0.5 V and no additional external load remain planning assumptions.

## Acceptance criteria for this documentation package

- AC-01: latest origin/main and PR #31 agree with the full base SHA above; starting tree is clean.
- AC-02: observed visibility is PUBLIC and prior user approval is recorded without seeking it again.
- AC-03: all five immutable normalized-LF hashes above match; their files remain unchanged.
- AC-04: the conflict inventory covers root contract, both collection requests and deployment request.
- AC-05: future replacements are versioned; no existing package, decision or evidence is overwritten.
- AC-06: runtime observations are distinguished from documentary gates and historical commit bindings.
- AC-07: successor hash dependency order and preservation of durable single-use history are explicit.
- AC-08: future fixed identity, eleven assets, schema, resource limits and no-retry controls are retained.
- AC-09: public publication policy excludes protected content and live authority; no fresh evidence is claimed.
- AC-10: both executable collection authorization and deployment Authorization V2 remain absent.
- AC-11: deployment_enabled=false, WP-14 blocked and WP-15 unstarted remain true.
- AC-12: change scope is this review document plus PROJECT_STATE.md; prior history and hashes are preserved.
- AC-13: document structure, unique state keys, diff whitespace, local static and security checks pass.
- AC-14: only the feature branch is committed/pushed; verified remote SHA ends this run without merge.

## Review outcome boundary

Documentation acceptance can pass while operational readiness remains blocked. Acceptance
of this package does not create collection/deployment authorization, execute Cadence,
alter a design, change repository visibility or start WP-15. The next concrete work is
review/integration of this package and the bounded repository reconciliation described above.
