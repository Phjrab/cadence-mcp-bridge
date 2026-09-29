# WP-14 renewal local preflight implementation v1

## Status and authority

Repository-only implementation and isolated verification; **not execution authority**.
PR #51 merged reviewed head `577968abf027d76df66ac2ded5df17862d24a582`
as `f6917a0eb49239f81cdf034df68d2254069cfc22`. That exact commit was the
latest fetched and remote main before branch `wp/WP-14-renewal-local-preflight`
was created. GitHub visibility is PUBLIC; deployment remains disabled.

The new, argument-free operator script is `scripts/verify-wp14-renewal-local.py`.
Its normalized-LF SHA-256 is
`6cc1d22981dd2cbf53a58a747093c14e22eef3a2733b9490829b032b152f309b`.
It is not an MCP tool. No collector or deployer is modified, executed, imported,
dot-sourced, or repurposed by this checker or by this run.

This implements only the local review boundary of
`docs/approvals/WP14_RENEWAL_SINGLE_USE_ACTIVATION_REQUEST_V1.md`, digest
`9cc668d58448d8c3965751fb1bd25b3acf9f807b8fa1dc2e27547513888be04d`.
The existing renewal request digest remains
`747ec5d73372f7fc8149f773638a0be106d12698fa4a1b7a45306c49a2374f4a`;
the existing renewal collector digest remains
`d814d0da7ffc3890274ea24f1b9fc946bf861ec617860c6560cab320f08a3d89`.
All old request/decision/plan/evidence records remain unchanged.

## Fixed local boundary

The checker accepts no caller paths, identifiers, values, environment overrides,
commands or execution modes. Importing it defines functions/constants only.
Its only subprocess is a fixed isolated (`-I -B`) local Python child running the
same checker through a fixed internal entrypoint. There is no SSH/SCP, collector,
deployer, Cadence, shell, network or arbitrary-script dispatch path. The operator
entrypoint rejects every argument before starting that child.

In a later separately approved real invocation, its closed checks would be:

1. Verify eleven pinned public contract/source/evidence digests (source files are
   read as bytes only, never imported). Verify `deployment_enabled=false`.
2. Require absence of the legacy collection activation, recovery activation,
   renewal activation and evidence V2 at their existing fixed repository paths.
3. Resolve only the Windows known-folder deployment and collection ledgers from
   the existing contract. Reject missing/non-directory/reparse ledgers; never
   create or repair a ledger.
4. Acquire the existing deployment `operation.lock`, then existing collection
   `operation.lock`, nonblocking. `OPEN_EXISTING`, exclusive Windows sharing and
   the compatible byte-range primitive preserve both existing lock domains.
   Release in reverse order; never write, truncate, replace or delete lock bytes.
5. Require absence of the fixed `recovery-v1.json` and
   `collection-renewal-v1.json` slots. Empty or partial files also block. A new
   UUID, checkout or package revision cannot reset the reserved renewal namespace.
6. Read the current username/MachineGuid inputs in memory only. Use the renewal
   rule's exact UTF-8 `username|MachineGuid` digest input, without case folding,
   trimming or substituting SID. Require the username to agree exactly with the
   native Windows username; environment-derived ambiguity fails closed. Validate
   bounded input shape and compare two observations for stability.
7. Check the preserved deployment activation's pinned normalized digest (at most
   16,384 bytes) and each consumed predecessor claim's closed six-field schema,
   types, historical bindings and UTC timestamp (at most 4,096 bytes per claim).
   Derive claim byte hashes only in memory. No externally approved private claim
   digest exists at this pre-authorization stage: do not claim to match one.
8. Re-read compared public/claim/activation bytes and absence conditions before
   success, while holding both locks. Check each lock's bytes before release.
   The bounded file reader rejects non-regular files, hard links, reparse paths,
   redirected resolved handles and oversized input; it denies write/delete sharing.

The complete fixed names remain in the existing request and reviewed source.
No resolved private path, claim value, authorization UUID, username, MachineGuid,
SID, binding or private digest is returned. Historical V1 remains expired at its
original `2026-09-18T08:05:01Z` boundary; this check cannot refresh it.

## Time, output and fail-closed behavior

The parent establishes a ten-second monotonic budget before starting its child.
It reserves the final 0.75 seconds for terminating/reaping that owned child and
closing handles, so normal data inspection must stop by 9.25 seconds. Startup
time counts against the budget. Child termination is not ledger cleanup and does
not authorize artifact deletion, recovery or retry. Native OS process startup or
termination remains an OS dependency, not a hard-real-time guarantee.

Two bounded readers cap aggregate child stdout/stderr at 512 bytes while it runs;
their queue is bounded. Nonempty stderr, invalid bytes, partial/multiple results,
wrong exit status, unknown code or over-limit output fails closed. The parent
never forwards child bytes or raw exceptions. Public stdout is exactly one ASCII
JSON line with only `success` (boolean) and `code` (closed enum), at most 512 bytes.
Success code is `LOCAL_PREFLIGHT_READY`; all failure codes are fixed in source.
No diagnostic payload or durable private result is written.

`LOCAL_PREFLIGHT_READY` means only that those local prerequisites were consistent
at that instant. It is not a binding record, approved predecessor digest,
Authorization, single-use reservation, proof of PUBLIC visibility at invocation,
fresh remote evidence, deployment readiness or scientific baseline. GitHub
visibility, reviewed commit/blob provenance and checker hash are separately
rechecked by the operator before a later approved invocation. A future activation
workflow must privately recompute/match the required values under its own exact
approval; it cannot reconstruct them from this checker output. The collector must
still perform its own execution-time checks; this result cannot defeat time-of-check
versus time-of-use drift or consume/reserve an attempt.

## Acceptance and isolated verification

The new tests import only this new checker, not existing collectors/deployers.
They substitute both identity and known-folder providers, use temporary synthetic
repository/ledger contents, and replace the supervisor's sole child with a local
synthetic worker. No real operational authority or private file is inspected.

Acceptance criteria verified locally:

1. All compiled public provenance hashes match the reviewed repository artifacts.
2. No caller arguments, remote dispatch or collector/deployer import surface exists.
3. Synthetic successful checks emit only the closed success/code envelope.
4. Username/native-name mismatch, malformed/oversized inputs, drift and invalid
   MachineGuid fail; UTF-8 digest semantics remain exact, not SID substitution.
5. Both six-field predecessor schemas reject missing, extra, duplicate,
   wrong-type, wrong-hash, wrong-state, malformed-time, future or naive timestamp,
   oversized, empty, partial and invalid-UTF-8 synthetic records.
6. Deployment-activation and public-contract tamper cannot succeed.
7. `deployment_enabled=true` cannot succeed.
8. Existing, empty or partial activation/evidence/renewal/recovery collisions fail
   without cleanup or alternate names.
9. Both original lock namespaces use deployment-then-collection acquisition and
   reverse release; missing locks are not created.
10. Competing exclusive and legacy byte-range holders block on temporary files.
11. Hard-linked and reparse inputs are rejected; reads are bounded.
12. Mid-check identity, claim, activation, public-file, lineage and collision drift
    prevents success.
13. Synthetic successful and rejected checks preserve fixture bytes and the file
    inventory; no actual claim is consumed and no durable result is generated.
14. Startup-delay, default ten-second deadline, partial timeout, both output floods,
    exact 512/513-byte boundaries, stderr, invalid UTF-8, duplicate envelope, empty
    response, wrong exit and launch failure are handled without retry.
15. Sensitive canaries in child output/exceptions never reach the output envelope.
16. Existing collector/deployer source, old documents/evidence, PUBLIC policy and
    disabled deployment remain unchanged; operational preconditions remain unverified.

Final verification: 93 new isolated tests plus 18 dedicated security tests passed
(111 total). Ruff passed for the repository; strict mypy passed for 17 existing
source files and the new checker. The existing full pytest suite was intentionally
not invoked because it imports or executes existing collectors/deployers, expressly
forbidden in this task. No claim of a full-suite or actual-invocation PASS is made.
Secret preflight and the locked dependency audit are recorded in PROJECT_STATE
after completion.

## Remaining gate

The production checker was not invoked. Actual identity/binding, predecessor byte
digests, present private lock/claim/activation state and V2 absence were not freshly
observed. Fixture preservation is not presented as measurement of those private
artifacts. No real Authorization, claim, lock or V2 evidence was created or changed;
no SSH/SCP, remote collection/deployment, Cadence, simulation or design action occurred.

Next is review and explicitly authorized PR integration of this implementation.
A later hash-bound approval may permit one real private local checker invocation
with only the closed output. It is separate from any renewal collection approval.
WP-14 remains blocked; WP-15 is unstarted.
