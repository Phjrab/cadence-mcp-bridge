# Finite standard-VM source-binding observation

PR164, development 2.2.0.dev0. This is an opt-in operator operation, not a public
MCP execution tool or a replacement for native simulation admission. Published
2.1.0 and PR163's explicit-candidate lifecycle remain unchanged.

The software path connects preparation, finite admission, authenticated transport,
the existing resource lock, owned-copy staging, one fixed OCEAN start, protection
checks and terminal evidence. No current-VM observation is established by this
document. Synthetic subprocess evidence is not Cadence evidence.

## Execution trust and authority

Two different records are required, in addition to the prepared plan:

* A separately reviewed standard-VM execution attestation covers interpreter and
  startup, OS loader/libraries, Cadence launchers/runtime/contexts and registered
  library initialization. Every category names a retained evidence digest. It
  binds the exact profile, registration, worker, request, collector, declared
  member manifest, registered library trees and fixed launch recipe.
* A finite human admission binds that attestation and the exact prepared plan,
  package, existing identity/domain and expected live counter. The operator must
  independently provide its approved digest to `run`. A generated JSON document,
  its own hash or an agent-written plan does not establish human approval.

The declaration guard still checks only its bounded explicit members and complete
ancestor union. It does not discover the dynamic loader/init closure. The broader
OS/vendor/runtime behavior is an explicit **externally reviewed standard-VM trust
assumption**, reported as `OPERATOR_ATTESTED_STANDARD_VM`. It is not dynamically
proved dependency completeness, benign behavior inferred from hashes, or empirical
Cadence qualification. Missing category evidence, unresolved dependencies, changed
libraries or expired authority must block actual operation. Do not create a
positive attestation merely to make these checks pass.

Only the professor-provided standard CentOS/Cadence/PDK VM, or an equivalently
reproduced installation, is in scope. Connection identity, account, workspace,
registry, journal, source/state and limits remain operator configuration.

## Operator commands

`operator-binding-observation schema` and `prepare` remain local and do not claim,
contact a VM, attest an installation or start EDA. `prepare` exports three exclusive
files. Original configuration file hashes and canonical execution-projection
hashes are separately recorded; pretty input JSON is never rewritten.

```text
cadence-mcp-bridge operator-binding-observation prepare \
  --settings SETTINGS --context CONTEXT --registration REGISTRATION \
  --design-id DESIGN --analysis-id ANALYSIS --output NEW_PLAN_DIRECTORY

cadence-mcp-bridge operator-binding-observation run \
  --settings SETTINGS --context CONTEXT --registration REGISTRATION \
  --prepared PLAN_DIRECTORY --expected-plan APPROVED_PLAN_SHA256 \
  --admission FINITE_ADMISSION --expected-admission HUMAN_APPROVED_ADMISSION_SHA256 \
  --manifest DECLARED_MEMBER_MANIFEST --attestation REVIEWED_EXECUTION_ATTESTATION \
  --output NEW_PRIVATE_EVIDENCE_DIRECTORY

cadence-mcp-bridge operator-binding-observation result \
  --output RETAINED_EVIDENCE_DIRECTORY --expected-admission APPROVED_ADMISSION_SHA256
```

Paths above are local operator files, not arbitrary remote commands or executable
inputs. Only normalized installed worker bytes and the three unchanged pinned
helpers can supply bootstrap code. SSH uses strict host-key checking, BatchMode
and the fixed `/usr/bin/python -E -s -B` entry. A bounded stdin envelope is fully
authenticated before code evaluation. There is no deployment or sudo operation.

## Closed admission contract

The canonical ASCII object has exactly these fields:

| Group | Required fields |
| --- | --- |
| Kind | `schema_version=1`, `kind=FINITE_BINDING_OBSERVATION` |
| Human reference | `authority_reference`, `approval_receipt_sha256` |
| Prepared software | `prepared_plan_sha256`, `package_sha256` |
| Selected code/input | `profile_sha256`, `registration_sha256`, `request_sha256`, `collector_sha256`, `helper_sha256` |
| Execution evidence | `declared_members_sha256`, `execution_attestation_sha256` |
| Retained resources | `resource_domain_sha256`, `identity_manifest_sha256`, `expected_counter` |
| Existing campaign | `predecessor`, with the existing four `predecessor_*_sha256` references |
| Freshness | `valid_from_unix`, `valid_until_unix`, at most one hour |
| Bounds | `limits`, exactly the values below |

`expected_counter` is the existing `campaign_id`, `count`, and
`result_reserved_bytes`; no ledger is initialized, reset, refunded or replaced.
`limits` is exactly: remote_attempts1, ocean_starts1, outer_seconds60,
ocean_seconds45, stage_bytes8388608, new_simulations0, new_extractions0,
new_reserved_bytes0. The disk floor remains active. The retained global policy
and any other work's consumption still apply. The 8MiB stage allowance is not a
Spectre result reservation or authorization for a candidate experiment.

The attestation is a separate canonical object with exactly:
`schema_version=1`,
`kind=STANDARD_VM_BINDING_OBSERVER_EXECUTION_ATTESTATION`, `subject` (the five
selected code/input hashes above), `declared_members_sha256`,
`launch_recipe=OWNED_COPY_NOGRAPH_NOCDSINIT_V1`, `review_reference`,
`trust_categories`, `runtime_roots`, `libraries`, `permitted_effects=PRIVATE_STAGE_ONLY`,
`unresolved_dependencies=[]`, `valid_from_unix`, and `valid_until_unix`.

`runtime_roots` is the sorted exact protected-root list. `libraries` is the exact
registered name/path/tree-hash list sorted by name. The four `trust_categories`
each have only `category` and `evidence_sha256`; their categories are
`system_interpreter_and_startup`, `os_loader_and_libraries`,
`cadence_launchers_runtime_and_contexts`, and `registered_library_initializers`.
These references require actual reviewed evidence, not invented hashes.

## Kernel stage capacity prerequisite

Before operational staging, the exact managed_root/binding-observations directory
must already be a separate persistent ext2/ext3/ext4 filesystem with total data
capacity at most8MiB and total inodes at most256. The guard checks the held/named
mount identity, kernel mount type, capacity and inode ceiling before the remote
claim, before launch and at subsequent admission guards. Kernel accounting covers
aggregate writes and open-unlinked files; a tree scan alone cannot enforce those
limits. An ordinary directory, volatile tmpfs or user FUSE mount is rejected.
Existing stage/source/dependency scans continue to detect conservation drift.

This increment performs no mount, filesystem formatting, provisioning or resizing.
The current VM's compatible storage/provisioning mechanism is not yet established;
its facts and a narrowly fixed administrator helper must be resolved before an
actual observation can be described as ready. Do not overlay or delete existing
stages or treat source hashes/approval as this missing kernel prerequisite.
The opt-in disposable CI filesystem test concerns only synthetic files on a hosted
runner. It is neither current-VM provisioning nor Cadence evidence.

The external process inventory streams at most4096 entries, checking cancellation
and the outer deadline between entries and closing the directory on every exit.

## One attempt and terminal evidence

The retained account/campaign claim is spent before SSH. A fixed remote claim
under the existing managed root is spent under the existing lifetime resource
lock before staging. Changing observation ID, output directory or host package
cannot reopen this allowance. Both partial and failed records remain protected.

The worker uses the existing source/state/whole-library snapshots, owned copy,
fixed collector, private HOME/TMP, explicit library map, minimal environment and
bounded ordinary-user process group. No license value is printed or changed.
The child never runs as root. Deferred HUP/TERM/INT cancellation avoids an
exception between spawning and retaining the child handle. Cleanup retains the
resource lock until the owned group stops; kernel-uninterruptible work can exceed
the desired timeout. SIGKILL/power loss cannot promise cleanup and must remain
unknown/spent. Host transport timeout never authorizes a resend.

Remote terminal evidence binds request/code/admission/attestation, actual start
count, process exit, frame hash, protected-state checks, cleanup and before/after
counter. `PROCESS_COMPLETED` means the fixed process completed and protection
passed. Host acceptance additionally requires the existing strict frame parser.
Missing, malformed, late-drifted or incomplete frames cannot become observations.
Runtime/electrical `qualification_established` remains false. No simulation,
extraction or result reservation is performed by observation.

The complete frame stays in its fixed private leaf; the disk terminal receipt
contains its digest. Host stdout, stderr, terminal or failure record, exact
admission and invocation remain private. `result` is retained local inspection:
it does not reconstruct authority, acquire a new claim or initiate SSH/EDA.

## Candidate experiment and release boundary

After authorized actual observation, establish source-property bindings and
effective inputs through the existing native registration/admission path. Reuse
PR163 for baseline plus two complete user-selected voltage vectors, sequential
DC submission, retained scalars and JSON/CSV differences. Hold model/corner,
temperature, load and stimulus fixed and distinguish requested from effective
values. Failure, timeout or unknown state stops advance without resubmission.

The next actual gates include current VM/library bounds and trust evidence,
valid finite observation authority, a live ledger/disk observation, complete
user-selected vectors and a separate finite three-DC grant. Historical values,
expired grants, source60 capacity and metadata-only collection allowances cannot
authorize these operations.

This increment can be reviewed as experimental operator software after its exact
tests/install/CI/review pass. Do not include claims of actual Cadence observation,
fresh three-candidate comparison or stable generic candidate execution in a
release until their actual evidence exists. W/L, mixed geometry, waveform export
and automatic optimization remain outside this minimum. PR164 merge and any
2.2.0/prerelease publication require their applicable explicit approval; v2.1.0
must not be republished.
