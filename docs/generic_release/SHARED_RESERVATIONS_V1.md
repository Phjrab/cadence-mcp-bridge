# Existing-domain reservation transactions

This is an internal accounting asset, not a production provider or execution
capability. No MCP tool, runner command, grant writer or budget database is
added. The launcher still accepts identity/preflight only. A provider must
independently attest the OS operator, grant, installed runner, native trust,
protected inputs, job admission, current policy and root/domain binding before
calling it. Model-authored bindings are not authority.

## Physical domain and compatibility

The module opens the existing managed root's run.lock without creation or
truncation, using nonblocking POSIX flock. It requires the existing
sim-mcp-v2-jobs/counter.json and native-mcp-v1-jobs directories and already
admitted UUID4 job/work directories. It never provisions a replacement counter,
lock or job engine. Windows msvcrt locking supports disposable local tests only.

The legacy fields remain campaign_id, count, result_reserved_bytes.
The compiled AUTO-PHASE-01 ceiling is500 attempts /10GiB; consumption is never
reset or refunded. This adapter cannot initialize a genuine new installation
or raise limits. A separately authorized append-only migration and physical
domain attestation will be required for that capability.

New files in the existing job's work directory are reservation-intent.json,
legacy-compatible attempt-reserved, and reservation-receipt.json. Bindings
include root/domain, ledger reference, grant/runner/plan and compiled execution-input hashes, expiry, limits,
per-operation bytes and disk floor. Hashes identify a verified contract; they
do not authenticate it. Different aliases/clients must resolve to the same
canonical root/physical lock. Links, junctions, hardlinks, untrusted POSIX
ownership/writable components and bounded corruption are rejected. The trusted
OS account remains the boundary against same-account replacement.

Schema2 bootstrap bundles include hash-bound reservations.py alongside
profile/probe/runner/launcher. Schema1 four-asset history remains verifiable and
retained. No activation-pointer migration or remote installation is performed.
Staging an asset does not enable a command or simulation.

## Write order and uncertainty

Under the existing physical EDA lock:

1. Verify counter, bounded native job markers, own intents/receipts, grant totals,
   expiry, active legacy marker and capacity.
2. Create/fsync the legacy-recognized counter .ade-tmp barrier containing the
   after-counter. Fsync its directory BEFORE writing an intent.
3. Exclusively create/fsync the immutable intent and legacy marker, with directory
   fsync after each creation.
4. Atomically rename the barrier onto the counter; fsync its directory.
5. Exclusively create/fsync the receipt and its directory.

The execution_input_sha256 binding must be the verified generic compiler manifest
digest, in addition to the legacy OperationPlan hash. The old plan alone omits
generic AC/TRAN/DC settings and cannot distinguish substituted input settings.
Different compiled inputs can consume another slot under the same verified grant;
same-operation input substitution is rejected.

No file is removed or repaired on failure. Before step4, the barrier makes
legacy preflight/audit reject uncertain accounting. After step4 without a receipt,
consistent intent/marker lookup and replay return UNKNOWN_OUTCOME. Another own
reservation is blocked. Later legacy advancement never proves a missing receipt
committed; no completion is synthesized. Partial/inconsistent records remain
integrity errors. Power-loss guarantees depend on actual filesystem/fsync
semantics and are not established by process-death tests or grammar parsing.

Completed replay and expired-grant reads do not spend, dispatch or refund.
Conflicting bindings fail. Same-grant quota is reconstructed from immutable
job records under the physical lock; another client cannot reset it with a new
local journal or changed policy fields. The counter retains legacy consumption. Historical marker validation preserves
the native-v1 domain's first post-reservation22 /1,745,879,040 values
(including completed count22–24 markers). The policy's unincremented
21 /1,611,661,312 baseline is not a valid reserved marker. The current ledger and new transaction before/after records
still require the newer32 /3,088,056,320 policy floor. This distinction does not
weaken historical campaign conservation checks or permit current-ledger rollback.

Every own reservation remains conservatively in-flight because trusted terminal
worker receipts are not implemented. Physical free space must cover the floor,
all those in-flight bytes and the new reservation. Cumulative reservations,
grant usage, in-flight commitments and physical free space are distinct.
Logical/allocated occupancy is not measured by this adapter.

## Verification and remaining work

Disposable files are seeded82 /9,798,942,720 bytes. Tests exercise second batches,
replay, process races/death after durable writes/rename, legacy advancement,
missing/corrupt state, grant exhaustion/drift and physical floor. Ubuntu CI
exercises actual flock interoperability with an independent holder and real
group-writable components. Windows skips four POSIX-only checks.

Installed-wheel verification uses disposable accounting only and preserves
its records through same-version reinstall/uninstall. Actual VM Python2.6
parses source without asset execution or remote writes. Production provider,
OS operator authenticity, native provisioning, terminal reconciliation, renewal,
cancellation, extraction recovery, new circuit jobs/Sweep and clean actual
application qualification remain incomplete.
