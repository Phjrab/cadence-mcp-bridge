# WP-14 recovery Authorization input review v1

## Decision

- Review timestamp: `2026-09-17T12:36:15.9605215Z`
- Evidence observation: `2026-09-17T08:05:01Z`
- Evidence expiry boundary: `2026-09-18T08:05:01Z`
- Remaining interval at review: approximately 19 hours 28 minutes 45 seconds
- Temporal result: `UNEXPIRED_AT_REVIEW_ONLY`
- Exact Authorization readiness: `BLOCKED`
- Execution authority: `false`

PR #40 reviewed head `ea5d863c38d6dacb5ef5129682f0c483246517b4`
was merged as `25c3e56c8a3720004d38c77250924c78d1ed4239`, verified as
the latest local and remote `origin/main` before this feature branch was created.
Repository visibility remains PUBLIC and `deployment_enabled=false` remains fixed.

This is a repository-only review. It is not an Authorization, activation record,
identity attestation, current remote preflight, claim or invocation instruction. It
does not grant either remote flag and does not instantiate any of the 17 fields.

## Local executor-binding verification method

The fixed recovery deployer derives the binding only on Windows, under the exact
operator and machine that would execute it. It reads the current Windows account SID
and the local-machine `MachineGuid`, joins their exact strings with one `|`, encodes
that string as UTF-8 and computes lowercase SHA-256 hexadecimal.

A future, separately approved preparation must verify the binding locally as follows:

- Verify the checked-out recovery deployer normalized-LF SHA-256 is
   `e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374`.
- Run a fixed, operator-only local check in the same Windows account and machine
   context intended for execution; it must accept no SID, machine ID or binding as
   caller input.
- Derive the binding in memory using the exact algorithm above. Never print, log,
   commit or place the raw SID or `MachineGuid` in an artifact.
- Compare the derived binding in memory with the candidate record and with the
   deployer's own runtime derivation. Any mismatch, lookup failure, non-Windows
   context or context change is fail-closed.
- Recheck immediately before a future activation is installed and again before
   invocation. This review does not perform either check and records no value.

No generic identity, shell or script interface may be exposed. Because the
repository is PUBLIC, the eventual exact record must remain an operator-local,
non-committed artifact at the already fixed activation path.

## Current fixed preflight requirements

The recovery deployer permits one preflight only after all local Authorization,
predecessor-claim, recovery-slot and lock checks pass. The fixed preflight must:

- use the fixed Windows OpenSSH transport and strict host-key/identity controls;
- confirm hostname `cadence`, user `buet` and canonical, existing, non-symlink root
  `/home/buet/cds_work/.cadence_mcp`;
- fail if any Virtuoso or OCEAN process is active;
- require the existing runner to be executable and report exactly `0.18.0`;
- require the snapshot-parent directory, when present, to be canonical and not a
  symlink, and require the exact new snapshot path to be absent;
- for all eleven fixed assets, require canonical non-symlink parent directories,
  no symlink at the destination, no staged `.wp14-v1-new` artifact and exact
  evidence-bound presence, type, owner, link-count, hash and mode preimages;
- return only `WP14_NARROW_PREFLIGHT_OK` with no stderr, nonzero status, malformed or
  excessive output; otherwise stop without snapshot, upload or replacement;
- remain within the shared 300-second deadline and 65,536-byte combined output cap.

The dated evidence and the earlier post-close diagnostic are not this preflight.
Remote conditions are mutable, so a future execution still needs the exact current
preflight under a separately approved record. This review performs no remote call.

## Closed 17-field data-source review

| Field | Authoritative source for a future exact record | Current state |
| --- | --- | --- |
| `schema_version` | Recovery deployer closed schema | Fixed requirement: integer `2`; not instantiated |
| `record_kind` | Recovery deployer closed schema | Fixed requirement only; not instantiated |
| `status` | Separate explicit user grant | Unset; this review is not `APPROVED` |
| `package_normalized_lf_sha256` | Merged deployment package v2 | Bound requirement: `96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431` |
| `deployer_normalized_lf_sha256` | Exact checked-out recovery deployer | Bound requirement: `e4ed2610aa0cb6a5b930b0ce6a52f1a6d2273c390195f0b58ff3e17c0d976374` |
| `remote_preflight_authorized` | Separate explicit user grant | Unset; must be Boolean true only in an approved exact record |
| `remote_deployment_authorized` | Separate explicit user grant | Unset; must be Boolean true only in an approved exact record |
| `max_uses` | Recovery deployer closed schema | Fixed requirement: integer `1`; not instantiated |
| `authorization_id` | Newly generated and separately reviewed lowercase UUID | Unknown; must not reuse any predecessor ID |
| `not_before` | Actual UTC clock at separately approved preparation | Unknown; must not be backdated or inferred |
| `expires_at` | Reviewed interval constrained by code and evidence boundary | Unknown; later than `not_before`, at most 24 hours, and no later than the evidence boundary |
| `executor_binding` | Same-context local derivation described above | Unknown and unpublished; fresh verification required |
| `remote_identity` | Reviewed evidence plus exact fixed schema | Historical evidence available; current remote truth still requires preflight |
| `preimages` | Eleven closed entries from reviewed evidence | Historical evidence available; current remote truth still requires preflight |
| `evidence_sha256` | Merged evidence v1 | Bound requirement: `0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7` |
| `observed_at` | Immutable evidence v1 field | Bound requirement: `2026-09-17T08:05:01Z` |
| `recovery_plan_sha256` | Merged recovery plan v1 | Bound requirement: `5333c6915c06ca1897b3e282e1de48cc16564fbfd37fcbdfe05a1907edb30d3a` |

Static requirements and historical bindings do not fill an executable record.
Unknown UUID, timestamps, executor binding and explicit grants remain blockers.

## Single-use claim and preservation conditions

- Preserve the original activation file and its exact SHA-256
  `095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`.
- Preserve the original six-field claim, original authorization ID and exact
  `consumed_at=2026-09-17T08:20:37.8800486+00:00`; never edit, remove, rename,
  reset or reinterpret the consumed attempt.
- Use the same operator-local global state root and exclusive `operation.lock`
  across checkouts and both executors.
- The independent fixed `recovery-v1.json` must be absent before the only attempt.
  A future executor must create it with create-new semantics, write-through and a
  durable flush before transport.
- A failed, partial, crashed, timed-out or uncertain attempt permanently consumes
  the recovery slot. Changing UUID, branch, checkout or machine does not grant a
  retry. No cleanup, repair, fallback destination or automatic rollback is allowed.
- Existing evidence, timestamp, hashes, original claim and activation are immutable;
  they may not be refreshed in place or reused after expiry.

## Expiry routing

Any later run must compare its own current UTC time with
`2026-09-18T08:05:01Z`. At or after that instant, exact Authorization preparation
must stop. Only a new versioned fail-closed evidence-renewal plan may be written.
That plan must preserve the old evidence and consumed collection claim, request a
new bounded collection authority, review the new evidence locally and bind any later
recovery request to new versioned hashes. Nothing in this review pre-authorizes it.

## Acceptance criteria

1. PR #40 exact head, merge commit and latest `origin/main` are verified.
2. Current UTC is recorded and compared to the immutable evidence boundary.
3. Evidence is described as unexpired only at the review timestamp.
4. Exact Authorization readiness remains BLOCKED.
5. The executor-binding algorithm and same-context local verification method are exact.
6. Raw SID, machine identifier and derived binding are neither read nor published here.
7. Fixed preflight identity, path, process, snapshot, asset and runner gates are complete.
8. The timeout, output, stderr and fail-closed constraints remain unchanged.
9. All 17 closed-schema fields have an authoritative source and current status.
10. Unknown identity, UUID, times and grants are not inferred or instantiated.
11. Original activation, consumed claim, evidence, timestamps and hashes are unchanged.
12. Shared locking and durable one-use recovery consumption remain mandatory.
13. Expiry routes only to a separately reviewed versioned evidence-renewal plan.
14. PUBLIC and `deployment_enabled=false` remain unchanged.
15. No Authorization, SSH/SCP, remote operation, Cadence or design operation occurs.
16. Only this review and `PROJECT_STATE.md` change on the feature branch.
17. Document, security, Git-diff and remote feature-SHA checks pass before STOP.

## Local verification

A fresh Git-index export with only this review and `PROJECT_STATE.md` overlaid was
validated without a remote and without any actual activation or operator ledger.
Ruff and strict mypy for 17 source files passed. The full local suite passed 365
tests with eight deliberately skipped real integrations and 56 existing deprecation
warnings. Secret preflight covered 363 repository files; all 18 dedicated security
tests and the strict locked dependency audit passed with no known vulnerabilities.
The final document checks verify the two-file scope, 17 criteria, unique state keys,
absent recovery Authorization, unchanged protected artifacts, PUBLIC visibility,
`deployment_enabled=false` and clean diff formatting. An initial security invocation
could not enumerate the export before its local Git index was initialized, and its
first indexed rerun hit the known Korean Windows-path output encoding issue; the
final UTF-8 rerun passed. No remote integration was enabled or contacted.

## Next gate

Review and integrate this documentation only. Immediately before any later action,
recheck UTC. While still before the boundary, the next separately authorized task
may prepare a concrete operator-local record only after fresh executor verification
and explicit review of every field. At or after the boundary, skip Authorization
preparation and prepare only the versioned fail-closed evidence-renewal plan.
