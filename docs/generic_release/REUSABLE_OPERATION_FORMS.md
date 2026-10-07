# Local reusable operation forms

This checkpoint supplies installed CLI validation of operator-owned authority
forms and immutable explicit-input plans. It does not supply a trusted native
admission provider. GREL-03 remains incomplete until a real shared ledger,
operator confirmation, native lifecycle and repeated batches are qualified.

Generate the closed schemas from an installed artifact:

~~~powershell
cadence-mcp-bridge operation grant-schema
cadence-mcp-bridge operation request-schema
cadence-mcp-bridge operation check-authority --settings C:/operator/runtime.json --context lab-a --grant C:/operator/grant.json --expected-grant-sha256 <reviewed-raw-file-sha256>
cadence-mcp-bridge operation plan --settings C:/operator/runtime.json --context lab-a --grant C:/operator/grant.json --expected-grant-sha256 <reviewed-raw-file-sha256> --request C:/operator/request.json
~~~

The operating-system operator creates and reviews their own private record from
the schema. The CLI only reads it; no MCP or CLI command writes, signs, activates,
renews or revokes a grant. A file hash binds exact bytes, not human consent.
The local record cannot authenticate a human against a model running as the same
OS account. The future trusted admission boundary must independently attest that
confirmation. Locally matched forms always return execution_authorized=false.

Authority records bind the runner, declared resource domain, existing ledger
reference, exact environment/design/PDK input digests, logical design and analysis
allowlists, numeric regions, allowed actions, request and result reservation
ceilings, lifetime and status. Expiration/revocation denies new plan preparation.
No existing completed-result reader depends on this new form. A local description
is never reported as remaining remote capacity: those fields remain null until
observed from authoritative accounting. The environment ceiling is not reset.

Each request includes all declared variable values and a reservation size. The
existing registry's numeric/unit/copy checks apply before the narrower authority
region. Missing values, inherited ADE defaults and duplicate values are denied.
Fixed constraints are distinct from electrically qualified ranges. Canonical
value order and decimal representation produce a stable plan hash. The frozen
plan binds the entire input snapshot and exact authority file, and exposes only
logical IDs, units, canonical numbers and hashes, not library/ADE/private paths.

No journal or resource lock is created by local preparation. Existing AnalysisStore,
SweepStore, supervisors and historical native ledger/EDA lock remain intact.
The local AnalysisStore admission commit already establishes single first-send
identity and lookup-only retry; a future provider must preserve that boundary and
reconcile remote acceptance. Local timeout must not mint a new ID or resubmit.
There is no exactly-once execution claim. Current native reference behavior and
all old 85 full wire schemas remain the compatibility baseline.

Remote attestation, existing-ledger integration and generic analysis adapters
remain explicit blocking reasons. Pending cancellation, active termination,
extraction-only recovery, renewable authority and two real batches are not
implemented on the generic path at this checkpoint. The form's allowed-action
field describes intended scope and does not enable those capabilities.


Each numeric_regions entry requires design_id plus logical_id. Regions are unique
within a design and their design_id must belong to the grant design_ids. A request
uses exactly its design's regions; another authorized design's variables do not
satisfy or obstruct that scope. Thus a zero-variable circuit and a parameterized
circuit can share one local grant. Same-named variables on different designs can
have distinct unit/range constraints. The total bounded region count remains32.
This unreleased draft schema requires explicit design_id; older unscoped draft
forms are rejected and must be regenerated/reviewed by their operator. No grant
is automatically rewritten or reauthorized.
