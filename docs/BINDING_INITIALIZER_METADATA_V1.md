# Experimental fixed initializer metadata repair

This operator-only path supports the registered professor-provided standard VM.
It is an explicit local export, never an MCP capability, startup action, doctor
repair or automatic deployment. It adds no VM access or administrator authority.
The current source64 approval covers implementation and verification only.

Source61 changed-path local checks and hosted Linux CI passed. Its Windows export
fixture failed because its synthetic owner default differed from the ordinary
account; the fixture now uses that account, and the failure remains retained.
Final source62 tests, installed checks, CI and review are pending. None of these
software checks establish current-VM or Python2.6 acceptance.

## Exact scope and conservation

The recipe derives its library union from the authenticated native registration.
It conserves all registered library trees and retains the original source/state
registration records without updating them;
only installation library roots and their top-level `.il`, `.ils` and `.cxt`
files can become metadata targets. The installation selection must be inside a
protected root containing a bound Cadence tool. Workspace/source libraries and
other protected roots cannot expand this mutation scope. Limits are eight
libraries, three selected library roots, 128 selected targets, 8,192 combined
tree entries and 64 MiB combined library contents per observation pass.

The selected filename roles are a bounded repair recipe, **not discovery or proof
of a complete initialization dependency closure**. Source behavior, other files,
compiled contexts and dynamic dependencies still need separate reviewed evidence.
Nothing in this path creates a positive execution-trust attestation.

An initial plan binds the exact registered tree hashes, library metadata/content,
inode/owner/group/link identity, selected file hashes and ACLs, ancestors and
exact before/after mode/ACL values. It removes shared-write permissions through
the existing repair engine while preserving read/execute access, contents and
owners. No recursive chmod, uniform755/644, chown, source/PDK content change,
license operation or root MCP server is introduced. Unexpected types, aliases,
overlapping libraries, owners, unsafe ancestors and scope drift reject.

The original registration, plan and tree snapshots are retained. A successful
comparison produces linked original/current tree hashes and explicitly reports
metadata differences. Every other metadata row and all contents must remain
equal. It never replaces the old library fingerprints or activates a registration.
A later registration transition needs the actual delta evidence and its own
reviewed path. The ordinary postcheck compares the approved inputs and current
metadata; it does not authenticate a privileged administrator receipt.

## Export and explicit execution

Export only from an authenticated existing native bundle using the installed
operator interpreter:

```text
python -m cadence_mcp_bridge.binding_initializer --bundle <private-native-bundle> --manifest-sha256 <exact-native-manifest> --output <new-private-directory>
```

The new directory contains `initializer-admin.py` and `manifest.private.json`.
The helper freezes validated operator profile/registration plus exact installed
repair, snapshot, accounting and recipe bytes. It accepts no arbitrary source,
module, shell command, remote target or mode argument. Export authenticates the
bundle, uses the existing held private output namespace, and performs no transport.
Keep the generated helper and all plan/request/output files private.

After separate authorization for the exact VM operation, the fixed standalone
entry uses the VM's existing interpreter with `-E -s -B`:

```text
/usr/bin/python -E -s -B initializer-admin.py plan
/usr/bin/python -E -s -B initializer-admin.py apply <independently-approved-plan-sha256>
/usr/bin/python -E -s -B initializer-admin.py rollback <independently-approved-plan-sha256>
/usr/bin/python -E -s -B initializer-admin.py postcheck <exact-plan-sha256>
```

`plan` may run as the registered ordinary account or administrator. `apply` and
`rollback` require explicit administrator execution; the MCP server remains an
ordinary process. `postcheck` requires the registered ordinary account.
Apply/rollback/postcheck read one bounded canonical request from stdin, with
exactly `plan`, `expected_plan_sha256` and `operator_authority`. The plan includes
the exact frozen profile/registration and must match the independent argv hash.
Apply/rollback require a nonempty actual authority reference of at most512
characters. Postcheck requires `operator_authority=null`. A generated authority
string or matching hash is not independent evidence of human approval.

The helper uses a60-second deadline. The inherited repair request/response bound
is16MiB; snapshots are read twice to detect intervening changes. Getfacl/setfacl
are the existing fixed ACL operations; EDA starts and simulator reservations are0.
The operating interpreter, startup, loader and ACL utilities remain external
standard-VM trust prerequisites, not proved by these explicit asset hashes.

## Prospective registration after a metadata change

Pending source62 adds an explicitly invoked local proposal step. It requires the
original `NativeRegistration`, its authenticated native bundle and existing
runtime context, the exact canonical observed plan, and the ordinary-user
postcheck. Each evidence file has an independently supplied SHA-256. The plan
input is the canonical inner `plan` object from the inventory response, without
a trailing newline. The postcheck pin covers its exact retained stdout bytes,
including any terminal newline; its request uses `operator_authority=null`.

```text
python -m cadence_mcp_bridge.binding_initializer --prospective --bundle <original-private-native-bundle> --manifest-sha256 <exact-original-manifest> --runtime-settings <existing-private-runtime-settings> --context-id <registered-context> --native-registration <original-native-registration> --native-registration-sha256 <exact-original-file-sha256> --plan <canonical-observed-plan> --plan-sha256 <exact-plan-sha256> --postcheck <ordinary-user-postcheck-stdout> --postcheck-sha256 <exact-postcheck-file-sha256> --output <new-private-directory>
```

The original registration must project exactly to the bundle's registration in
that context. Retained whole-library metadata and content hashes must match the
original registered pins. The proposal computes expected replacement tree pins
directly by removing only the selected group/other write mode bits; all other
metadata rows and all content hashes stay unchanged. The postcheck must report
those exact transitions. Every occurrence of each library in every route receives
its calculated pin, while identity, environment, validation requests, source/ADE,
models and readers remain bound to the originals. ACL restrictions are checked
against the original plan; an ACL is not itself encoded by a tree hash.

The exclusive private output contains:

- `native-registration.prospective.json`: the proposed operator registration.
- `projected-registration.prospective.json`: its expected native projection.
- `rebind-report.private.json`: links to the original inputs and calculated pins.

Optional `--administrator-result <retained-admin-stdout>` and
`--administrator-result-sha256 <exact-file-sha256>` must be supplied together.
They correlate retained output only. Neither administrator stdout nor ordinary
postcheck bytes authenticate a root receipt, prove complete initializer/runtime
trust, or supply human approval. The report keeps receipt provenance and runtime
trust unassessed, installation/qualification false, and execution unauthorized.

This command does not update the original registration, install a bundle, change
an active provider, contact the VM, or touch a ledger. Building and applying an
updated bundle through the existing setup/update path is a later, separately
authorized operation after current-VM evidence and external review are available.
Keep all original registrations, plans, receipts and consumed counters; a new
proposal is not a new execution allowance or accounting baseline.

The command checks every original evidence pin and authenticated bundle again
after publishing the output files, before terminal success. Concurrent input drift
rejects without rewriting or removing partial output. Files from an interrupted or
failed command are retained evidence, not a successful registration proposal; only
a successful terminal result can qualify that local proposal for external review.

## Accounting, interruption and evidence

Mutation reuses the existing resource lock and unchanged content/identity guards
for the existing counter, reservation identity and legacy-seal presence/absence.
It never creates a new ledger, resets consumption, refunds failed work or changes
budget limits. Before any mutation, the existing engine durably retains the exact
observed-before plan in its administrator receipt namespace. That receipt is
provenance for the original plan, **not a successful terminal repair receipt or
execution approval**.

Before/known-intermediate/after states are checked against that original plan.
An interrupted or failed operation can be partial; retain its plan, stdout/stderr,
receipt and current metadata. Do not generate a new baseline or blindly retry.
An explicit same-plan resume or rollback must satisfy the receipt, whole-tree,
ACL, accounting and independent-authority guards again. Final success is returned
only after full strict delta verification. The returned delta must be retained
privately by the caller; the helper does not publish a durable success receipt.

Software/installed synthetic checks and disposable Linux chmod/ACL evidence are
distinct from current-VM execution. Actual initializer metadata/behavior trust,
bounded observer storage, finite OCEAN observation and the selected three-job DC
comparison remain independent unfinished gates until their actual evidence exists.

The opt-in Linux checks exercise partial apply, same-plan resume, no-op repeat,
ordinary-user postcheck and rollback. A separate generated-entry case uses the
exact exported helper and its four actual embedded modules on owned synthetic
files. These hosted-interpreter checks do not establish Python2.6 compatibility
or current-VM runtime trust. The locked certifi dependency is updated separately
to2026.10.19 for PYSEC-2026-4320; no other locked dependency version changes.
