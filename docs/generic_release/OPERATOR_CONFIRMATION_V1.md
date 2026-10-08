# OS-operator confirmation for the standard VM, implementation checkpoint

This continues the existing authenticated-provider branch over unmerged PR151.
It does not complete GREL03 or enable generic native dispatch. Support remains
limited to the professor-provided CentOS/Cadence VM (or an equivalent reproduced
installation), its existing PDK, and individual VMware use. Actual versions come
from current qualification; examples must not replace measured bindings.

## Explicit operator workflow

The operator owns SSH alias/host key/authentication, guest account, workspace,
source circuit/ADE registrations, results, local journals and authorized limits.
Use the existing domain setup workflow for a genuinely new installation. Retained
installations use their existing account-home index, accounting anchor, shared
counter and run.lock. Confirmation does not initialize or migrate a ledger.

1. Load and check the operator's runtime settings and grant using `operation
   check-authority`. The grant must bind the real domain, runner, existing ledger,
   environment/design/PDK digests, registered designs/analyses/numeric regions,
   actions, lifetime and ceilings. Create the grant only under actual human
   authority. Write its canonical JSON bytes (sorted keys, compact separators,
   ASCII JSON, no trailing newline) and compute the digest of those exact bytes.
2. Run `operator-authority export-helper --output NEW_LOCAL_DIRECTORY` from the
   installed package. The receipt supplies `manifest_sha256`. This is local export,
   not consent, deployment or execution.
3. Run `operator-authority stage --profile ENVIRONMENT_JSON
   --expected-helper-sha256 HELPER_SHA256`. This explicitly stages only the current
   package's four fixed assets and manifest below the registered workspace's
   `.cadence_mcp-setup/HELPER_SHA256`. Existing identical bytes are reused; unknown
   members, changed bytes, links and unsafe ancestors reject. No root or sudo is used.
4. The authenticated OS operator explicitly runs the following command under the
   actual human instruction. Combine lines for the shell. This CLI is not an MCP
   tool. `ACTUAL_HUMAN_INSTRUCTION_REFERENCE` identifies the actual instruction;
   neither an agent-authored plan nor this guide supplies approval.

```text
cadence-mcp-bridge operator-authority confirm
  --settings RUNTIME_JSON --context CONTEXT_ID
  --grant GRANT_JSON --expected-grant-sha256 GRANT_BYTES_SHA256
  --identity-manifest-sha256 EXISTING_EFFECTIVE_ACCOUNTING_ANCHOR_SHA256
  --expected-helper-sha256 HELPER_SHA256
  --operator-authority ACTUAL_HUMAN_INSTRUCTION_REFERENCE
  --output NEW_PRIVATE_LOCAL_RECEIPT_JSON
```

The reference is a bounded printable ASCII identifier, not a password or credential.
The confirmation stores the immutable grant and human-authority reference as a
private ordinary-user record under `operator-confirmations/GRANT_SHA256.json`.
The guest's OS account, hostname, trusted ancestors, existing home index, root,
effective anchor and resource policy must match. The helper holds the existing
EDA lock, rechecks the index and live grant, and audits the authoritative counter.
The local response checks the exact confirmation digest and a closed counter shape.
No reservation, EDA launch, accounting reset, journal rewrite or budget increase occurs.
`operator_confirmed=true` records consent; `execution_authorized=false` means
runtime/trust/adapter/resource gates are still required before any job can execute.

`inspect` takes the same bindings/output and omits `--operator-authority`. It is
read-only and can inspect an expired grant. It validates retained confirmation and
revocation integrity. `revoke` requires the actual authority reference and appends
one hash-bound `.revoked.json` record under the existing lock. It never overwrites
the grant, refunds reservations or signals a worker. Repeat confirmation/revocation
reuses identical records. A revoked grant cannot be confirmed again. Completed
job reads must remain separate from live dispatch authority in the future provider.

Partial/corrupt records are retained and rejected. Loss of the response after a
complete durable write is recoverable by inspection/repeat; an incomplete write
is not inferred successful or silently repaired. An active EDA lock blocks writes.
There is no arbitrary helper filename, caller script/command, sudo or installation
permission operation exposed through this interface. Import/startup/doctor never
stage or confirm. Other operators must supply their own real authorization.

## Shared compiler/worker prerequisites

The local ADE and measurement compilers now delegate to the same Python2.6
primitive renderer. Effective Spectre-input parsing and scalar normalization are
also shared, retaining the existing narrow registered dialect and public errors.
A future fixed worker must obtain expected topology, variables, model includes,
analysis and reader data from confirmed registration, never from the candidate
netlist. Parser success alone does not attest OA/ADE copy or PDK bytes.

An internal owned ReservationSession pins the existing lock inode and descriptor
through a worker lifetime. Existing reserve() calls still use a short session.
The actual session object is required; no JSON flag/fd can bypass locking. POSIX
fixture coverage proves a child can retain the inherited lock after its parent
closes its descriptor. The production acceptor/worker fork is not implemented yet.
All generic reservations remain conservatively in-flight; there is no terminal
attestation, discount, reset or refund.

## Evidence and remaining work

Related source checks passed: 323 tests /5 Windows POSIX skips before the final
additional confirmation fault cases; final confirmation suite37 passed. Shared
ADE/reader/confirmation suite156 passed after effective parser extraction.
Ruff and mypy80 source files passed. Final package/security/compatibility receipts
are recorded separately; these counts do not prove native dispatch.

Actual ordinary-user current VM retained preflight passed again. Counter remained
82 /9,798,942,720 bytes, leaving938,475,520 bytes (895MiB). Seven existing control
files retained content and metadata. Current fixed assets parsed under actual
Python2.6. The common renderer/effective-input parser also executed with synthetic
RC input under actual Python2.6 and rejected expression-valued parameters.
The first runtime check script had an escaped-newline SyntaxError; its private
failure evidence was preserved and a separate corrected check passed. This was
not a Cadence job. Remote writes/reservations/new simulations in these checks0.

No actual grant was confirmed or helper staged during this checkpoint. Installed
preflight reservations still predate current source; retained preflight must not
be presented as current-package native worker attestation. The reviewed immutable
native-runtime transition, authenticated production provider/terminal worker,
owned new RC/MOS OA/ADE circuits, effective netlisting, DC/AC/TRAN/extraction,
generic Sweep/specification and actual clean Codex submission/retry/restart remain
incomplete. Keep one continuing provider branch/PR; do not call this foundation
GREL03 completion or start an independent budget domain. General release BLOCKED.
Continuous GREL02–07, current minimum administrator delegation and the895MiB
remaining-space authorization persist. No phase reapproval, merge, GREL08,
publication, license changes, deletion or budget increase/reset/refund.


Final foundation receipts: affected332 PASS /5 Windows POSIX skips /65.22s;
Ruff PASS; mypy80 source files PASS. Security18 PASS /6.49s; dependency audit
clean. Historical85 public MCP schemas PASS. Curated wheel/sdist and installed
protocol/CLI/helper export/bootstrap/reinstall/uninstall PASS;43 operator and20
domain state files preserved. These are source/package/synthetic receipts only.
Actual Codex runtime-info-v2 returned the existing operator-supplied catalog with
one design (schema2) and two PDK entries (schema2), with authority/environment
qualification unassessed. No new generic job tool is connected yet. That read
proves only the loaded catalog, not new-job submission or restart qualification.
