# Standard-VM new installation and retained domain reuse

Supported release scope is the professor-provided CentOS/Cadence VM or equivalent
reproduced installation, its existing PDK and individual VMware. Ordinary-user
SSH, MCP, EDA, OA/ADE copy, extraction and journals stay separate from administrator
installation repair. New OS/Cadence/PDK abstraction and other physical hosts are
not qualification requirements for this release.

The fixed operator CLI handles genuine zero-history initialization and existing
accounting registration as distinct actions. Neither action creates an execution
grant. Current GREL03 remains partial until the authenticated production provider,
terminal worker/recovery and actual new circuit execution pass.

## Reproducible operator flow

1. Confirm actual VM/tool information and strict SSH host identity using the
   environment qualification and installation trust workflow. Register your own
   address/SSH alias, account, workspace, protected Cadence/PDK/source roots and
   circuit/ADE/registry/journal settings. Reuse common measured VM compatibility,
   never another user's host keys, private checkpoint, UUIDs, grants or journals.
2. Export `domain export-setup-helper-bundle --output <new-private-directory>`.
   Preserve its manifest SHA256. Run `domain stage-setup-helper --profile
   <profile.json> --expected-helper-sha256 <manifest-sha256>`. The package stages
   only its fixed files under `workspace_root/.cadence_mcp-setup/<manifest-sha256>`
   as the guest user. It accepts no caller file contents, script or target filename.
   Repeat verifies retained bytes and changes zero files. Imports/server startup/
   doctor do not stage or initialize anything.
3. For a genuine new installation, the workspace must already be user-owned and
   trusted and its `.cadence_mcp` must be absent. Set explicitly approved initial
   ceilings in the operator profile. Run `domain plan-fresh --profile <profile.json>
   --output <new-private-plan.json> --expected-helper-sha256 <manifest-sha256>`.
   The plan is read-only and states `PLAN_IS_NOT_OPERATOR_APPROVAL`.
4. After the VM operator confirms that initial policy, invoke `domain apply-fresh
   --profile <profile.json> --plan <private-plan.json> --output <new-private-receipt>
   --expected-plan-sha256 <plan-sha256> --expected-helper-sha256 <manifest-sha256>
   --operator-authority <reference-to-actual-human-instruction>`.
   This explicit account-owner CLI action records that instruction; the text is
   not an authenticated execution grant. Other VM users need their own authority.
5. Existing installations first use the retained-ledger migration/seal workflow.
   Then run `domain register-existing --profile <profile.json> --output
   <new-private-receipt> --expected-helper-sha256 <manifest-sha256>
   --identity-manifest-sha256 <effective-existing-anchor-sha256>
   --operator-authority <reference-to-actual-human-instruction>`.
   This retains consumed budget and only registers the established identity.

No developer private checkpoint is required by this implementation. Typed source
registries and separately confirmed execution authority remain required; those
production execution steps are still incomplete. The CLI does not silently provide
Cadence/PDK entitlement or qualify new circuits.

## Single account-domain protection

The index at the actual guest account's fixed home `.cadence_mcp-domain` cannot
be relocated by a caller profile, SSH alias, local journal or context ID. It binds
one canonical managed root and immutable accounting anchor. Its `run.lock` is
only an initialization/registration mutex. EDA and reservations continue using
the canonical managed root's existing shared `run.lock`; it creates no additional
execution capacity. Production providers must validate this index before admission.

Fresh inventory searches the actual account home for retained `sim-mcp-v2-jobs`
counters or `reservation-identity` anchors, excluding registered protected vendor/
PDK/source roots and without following symlinks. Unreadable/oversized inventories
reject (50,000 directories/32 levels). An existing index, pending initialization,
retained history or already-existing target refuses initialization. An operator
cannot select a fresh root to discard the previous installation's consumption.
This is trusted-account provisioning, not protection against a malicious OS owner
deliberately deleting or concealing all of their own retained records.

Genuine fresh accounting uses manifest schema2 with an independently confirmed
initial policy, generated domain campaign UUID and zero attempts/bytes. It uses
the same shared transaction/audit/replay code as historical schema1, with policy
ceilings at or below the supported500 attempts/10GiB envelope. These constants
are a maximum implementation envelope, not an automatic allocation or approval.
Two disposable batches, replay and exhaustion tests verify variable reservation
conservation. Existing AUTO-PHASE-01 counters retain their original formulas and
floors; no historic count/bytes are synthesized into a new user's installation.

## Partial application and reuse

Initialization fsyncs an account-index intent before creating the canonical root,
zero counter, policy anchor and completion record. Only identical known partial
states resume. Conflicting files, orphan state, different roots/policies and later
consumption reject reinitialization. Repeating a completed identical setup audits
current consumption and returns reuse without replacing the counter with zero.
No cleanup/reset/refund/automatic anchor deletion is offered. Preserve the exact
applied package/helper/plan for partial recovery; after established operation,
use the provider path rather than generating another initialization plan.

## Validation on 2026-10-08

Local157 affected tests PASS/eight Windows platform skips; security18 PASS/1.12s,
locked audit clean; Ruff/mypy76 PASS. Installed-wheel disposable new-policy zero
initialization, two batches and replay PASS. Canonical installed package/protocol/
bootstrap/reinstall/uninstall PASS;43 operator and20 migration/fresh-policy fixture
files preserved. These are synthetic records, not EDA or live new-user results.

Actual current CentOS VM installed-wheel normal-user (uid500) fixed staging and
repeat PASS (six files then zero), established-domain registration/repeat PASS,
and fresh initialization on the existing domain correctly DENIED. Original
launcher/operator pointer/counter/lock/old anchor/classification-seal contents,
owner/group/mode/inode/mtime remained equal. Effective anchor
`cfd037cd4db24359614baa9f5e465bd24176f34151ee252e462016cdd2a6ef36`;
setup helper `6c220c2b0dfd26379a77cf1e0d17a24073b894b6acf8b766bc4af2c0ae9e3e65`.
Counter82 /9,798,942,720; remaining938,475,520 (895MiB); new reservations/jobs0.
The home index/registration record and fixed workspace helper staging were added;
no Cadence/PDK/OA/ADE content, license, metadata repair baseline or old journal changed.

The first staging attempt was rejected locally before SSH because input/output
transport limits share one bound; the corrected implementation permits the bounded
package payload while independently limiting the returned receipt to4096 bytes.
Failure evidence and earlier candidate artifacts are retained privately. The
canonical preservation receipt above predates this transport-only correction;
actual installed corrected-wheel staging PASS is separate evidence.

Fresh initialization on a clean physical VM remains unrun; on the current VM it
must stay denied. A clean local operator configuration reusing its established
remote ledger, authenticated provider/native jobs/automatic extraction/Sweep/spec
and actual Codex submit/read/retry/restart remain outstanding. No GREL08, merge,
publication, resource increase/reset or licensing changes are authorized.

[Reusable compatibility reference](STANDARD_VM_REFERENCE_PROFILE_V1.json) records
measured common VM behavior only. Every installation must perform fresh observation;
it supplies no address, keys, account, private journal, budget or execution authority.
PR150 corrected head a26256a passed both Windows and Ubuntu CI in push/PR runs.
Earlier failures remain historical; its old P2 threads are outdated, not formal approval.

Final corrected-staging-source canonical package verification also PASS:43 operator
plus20 domain fixture files retained across reinstall/uninstall. This closes the
transport-correction package receipt gap; it does not qualify native new jobs.


## Fresh-policy consumer correction

PR151 independent P1 identified consumers that still assumed the legacy campaign.
[The versioned consumer correction](FRESH_POLICY_CONSUMERS_V1.md) adds actual-policy
counter/storage parsing and shared conservation audit. It preserves historical
public output schemas and does not assert production provider/public generic
routing, terminal workers or fresh circuit execution are complete. The existing
account index is read/reused; no second initialization or registration is performed.
