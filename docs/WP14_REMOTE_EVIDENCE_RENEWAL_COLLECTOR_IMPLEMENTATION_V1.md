# WP-14 remote evidence renewal collector implementation v1

## Result

This repository checkpoint implements the request-only contract in
`docs/approvals/WP14_REMOTE_EVIDENCE_RENEWAL_COLLECTION_REQUEST_V1.md` without
activating or invoking the collector. The contract normalized-LF SHA-256 is
`747ec5d73372f7fc8149f773638a0be106d12698fa4a1b7a45306c49a2374f4a`.
PR #47 merged the reviewed request head
`2b6e36511271d111a5e98d8f9f8ed1047c025302` as latest `origin/main`
`379c5c462604c12ba6429d9dc2c1feaeacfff178` before this feature began.

The new argument-free operator script is
`scripts/collect-wp14-renewed-remote-preimages.py`. Its normalized-LF SHA-256 is
`d814d0da7ffc3890274ea24f1b9fc946bf861ec617860c6560cab320f08a3d89`.
It is not an MCP tool, deployment tool, or generic SSH/shell interface. The
implementation commit is intentionally not embedded into its own source. A future
private activation must identify the reviewed implementation commit after this
feature is integrated into main and must bind this exact collector digest.

Status is repository-implemented and locally verified, but remote execution stays
blocked. No renewal Authorization, claim, lock, executor binding, V2 evidence, SSH
process, remote file, deployment, Cadence process, or design operation was created.

## Fixed implementation boundary

The collector accepts no arguments and compiles in all of the following:

- SSH alias `cadence-vm`, expected hostname `cadence`, user `buet`, and canonical
  remote root `/home/buet/cds_work/.cadence_mcp`;
- the exact ordered eleven-asset allowlist and required/file-or-absent rules from
  the PUBLIC v2 package;
- Windows System32 OpenSSH, `BatchMode=yes`, strict host-key verification, one
  process, parallelism one, one 60-second monotonic deadline, and 32,768 combined
  stdout/stderr bytes;
- strict UTF-8, empty stderr, exit zero, exact identity/asset ordering/terminator,
  regular-file/owner/link/mode/containment checks, and a closed evidence-v2 schema;
- fixed preservation hashes for the contract, old packages, old collector,
  deployment/recovery deployers, V1 evidence, and the consumed deployment
  activation;
- `deployment_enabled=false`, absent legacy collection activation, absent recovery
  activation, and absent V2 evidence as preconditions.

The fixed remote command reads identity and exact-byte hashes only. It does not run
the old runner, create a remote temporary file, upload, snapshot, deploy, invoke
Cadence/SKILL, read design content, or emit file bytes. The public result contains
only fixed identity labels, bounded preimage metadata, reviewed provenance and an
empty blocker array on success. Error output is one closed JSON envelope containing
an allowlisted code; raw stderr and partial evidence are never returned.

## Private activation gate

The script recognizes only
`docs/approvals/WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_RENEWAL_AUTHORIZATION_V1.json`.
That path is absent. A future record must have the exact 19-field schema defined by
the request, schema version 2, generation `collection-renewal-v1`, max uses one,
the exact contract/package/collector/V1/deployment-activation bindings, two exact
private predecessor-claim byte digests, the fixed username/MachineGuid binding
rule, a matching private executor binding, a fresh UUID, an activation interval no
longer than 24 hours, and the explicit true collection grant. Extra or duplicate
fields, wrong scalar types, a malformed/unreviewed commit field, mismatched binding,
reparse path, oversized record, or invalid time window fails before ledger access.

The repository implementation commit is carried by the later exact activation and
copied into evidence. The activation review is the authority that binds that commit
to the exact collector blob; the collector also recomputes and enforces its own
normalized digest. This avoids a self-referential commit hash in the source while
preventing the old implementation or a different blob from being substituted.

## Preserved lock and claim lineage

The implementation does not create or repair a ledger or lock. It requires both
existing known-folder ledgers and both existing lock files. Using Windows exclusive
file sharing plus the compatible byte-range primitive, it acquires:

1. `wp14-narrow/operation.lock` (deployment/recovery domain), then
2. `wp14-preimage-evidence/operation.lock` (collection domain).

Acquisition is nonblocking. Both handles remain held through bounded predecessor
verification, durable consumption, the single transport, closed-schema validation,
public-output screening and post-operation predecessor verification. They are
released in reverse order. Missing, busy, non-regular or reparse paths fail closed;
neither lock is created, truncated, rewritten, renamed, removed, or replaced.

Within the locks the collector requires the original six-field collection and
deployment claims, verifies their exact private SHA-256 values supplied by the
future activation, and validates all fixed historical package/activation/
implementation bindings. It also rechecks the preserved deployment activation and
rejects any recovery claim. Old claim bytes and the preserved activation are
snapshotted and compared again before lock release.

The only future consumption path is the fixed
`wp14-preimage-evidence/collection-renewal-v1.json` slot. Exclusive create-new,
write, flush and fsync occur before transport. The private claim records the exact
activation/contract/collector/predecessor bindings and original consumption
timestamps. Any existing file, including empty or partial content, consumes the
namespace. Write, flush, launch, timeout, expiry, validation or uncertain failures
leave the slot in place; no cleanup, fallback name, UUID/hash/version/checkout reset
or retry is implemented.

## Isolated acceptance verification

`tests/unit/test_wp14_preimage_renewal_collector.py` and the test-only local process
`tests/fixtures/wp14_renewal_fake_ssh.py` use only pytest temporary directories,
synthetic identity/bindings, synthetic predecessor records and local fake transport.
Production has no fake-transport or environment-controlled bypass.

The 65 focused tests prove:

1. one synthetically approved activation acquires deployment then collection locks,
   verifies immutable predecessors, durably consumes the new slot before one fake
   transport, returns the exact evidence-v2 shape and does not create the evidence
   file;
2. success and every tested failure retain V1 evidence, predecessor claims,
   deployment activation and both lock bytes exactly;
3. missing, partial, extra, duplicate or digest-mismatched lineage, recovery state,
   absent locks, synthetic reparse attributes, empty/partial renewal slots and
   concurrent holders fail before transport;
4. actual Windows exclusive sharing is compatible with the existing PowerShell
   holder, and byte-range exclusion is compatible with the legacy Python collector;
5. write/flush and launch failures, wall-clock and activation expiry, all stdout/
   stderr flood variants, stderr, nonzero exit and invalid UTF-8 remain consumed and
   cannot retry;
6. malformed count/order/identity/hash/type/mode/owner/link/containment, required
   absence, symlink indication, protected payload and terminator cases fail closed;
7. changed UUID or repository commit cannot reset a consumed fixed slot; legacy
   activation, active recovery authority, repository tamper, V2 collision, extra
   arguments and sensitive public fields are rejected;
8. the success result excludes authorization UUID, executor binding, MachineGuid,
   predecessor claim digests, personal paths, credentials, license values and raw
   remote output.

These tests do not read the workstation identity, use the real known-folder ledgers,
invoke real SSH/SCP, or contact the Cadence VM. They do not establish remote
freshness, deployment readiness, scientific conditions, source/ADE-state semantic
equivalence, VDD, VCM, load, snapshot freshness, or a bias baseline.

## Remaining gate

WP-14 remains `BLOCKED`. After this feature is reviewed and merged, a separate run
must verify the exact main commit and collector hash, review the two private
predecessor claim digests and current private executor binding without publishing
them, and prepare a separate exact single-use activation for user review. Only that
future explicit grant may permit one real read-only collection attempt. It must not
reuse any prior activation or claim. Recovery, deployment, discovery invocation and
WP-15 remain separate later gates.
