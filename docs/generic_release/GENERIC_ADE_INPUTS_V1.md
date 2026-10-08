# Generic ADE L inputs, implementation boundary v1

This operator-only compiler is shipped in the Python package. It prepares private
job-bound artifacts and compares a bounded local Spectre input to registered
expectations. It cannot copy an OA cellview, contact SSH, create an admission,
reserve capacity, dispatch a job or grant authority. Native execution remains
unqualified; GREL-04 is partial and the general-release gate stays BLOCKED.

## Operator procedure

Use `cadence-mcp-bridge ade-input schema` from the installed package for the closed
`AdeExecutionRegistration` schema. Register the design/variable/analysis contracts
and immutable runtime settings through the existing operator workflow first.
The design must use `ade_l` and `owned_copy_only`. XL, Explorer, Assembler,
read-only descriptions and expression-valued scalar overrides are rejected.

Supply a separate local registration with exact design-profile/variable-set hashes,
protected source-tree and saved-state-tree fingerprints, reviewed static-input
fingerprint, ordered protected model includes (path, section, file hash), and
explicit typed analysis settings. These are operator declarations until a trusted
native provider attests the actual source/state/copy/model bytes. Neither a hash
nor a successful local comparison proves that attestation.

All declared numeric variables are required in every request. No earlier request
or ADE default fills a missing value. Existing numeric-contract and operator-grant
checks both apply. The model cannot supply SKILL expressions. DC keeps the saved
operating-point fields opaque and binds the normalized complete generated `dc`
statement; AC supplies start/stop/points per decade, and TRAN supplies stop/maxstep/
method. Input bounds limit planning work; adaptive simulator output still needs
separate provider time/size and extraction limits.

Prepare the ordinary immutable operation plan using `operation plan`. Then run:

```text
cadence-mcp-bridge ade-input compile --settings RUNTIME_JSON --context CONTEXT_ID
  --grant GRANT_JSON --expected-grant-sha256 GRANT_BYTES_SHA256
  --request REQUEST_JSON --registration ADE_REGISTRATION_JSON
  --expected-registration-sha256 REGISTRATION_BYTES_SHA256
  --operation-id UUID4 --expected-plan-sha256 PLAN_SHA256 --output NEW_DIRECTORY
```

Combine lines as appropriate for the shell. Paths belong to the local operator
CLI, never an MCP tool argument. The output must not exist; it contains private
`netlist.ocn`, `registration.json`, and `manifest.json`. Partial output is preserved
on failure. The public CLI reply contains only bounded identifiers/digests/status,
not bindings, model paths, netlists or script text. Use a new reviewed operation
identity for a new job. Artifact compilation does not admit that identity.

The script selects the deterministic job-owned `MCP_GREL_Work/Grel_UUID` cell and
job-local project/state roots. It never saves the original or copied OA/state and
never invokes the simulator. A provider must exclusively create the owned copy,
attest source/state/copy identity and preservation, and prove the designated
library belongs to the managed workspace before using this script. Library/cell
names alone are not ownership evidence. Variable-setter support/semantics and all
ADE calls still require fixed native API qualification; the setter is callable-
guarded. No source fallback is allowed on an unavailable API.

## Effective-input comparison

An operator can compare a local bounded generated input by using the same arguments
with `ade-input verify-input --native-input INPUT_SCS` instead of `compile --output`.
The file must be regular, unlinked, at most 256 KiB and reached without symlink or
junction parents. Same-account concurrent file replacement is not fully isolated.

The initial dialect deliberately accepts ASCII, a `simulator lang=spectre` header,
one statement per physical line, full-line `//` comments, explicit scalar parameter
assignments, exact ordered model includes, and one top-level DC/AC/TRAN statement.
It rejects continuation, inline/block comments, escapes, quoted expressions,
engineering-unit suffixes and non-scalar parameter expressions. Unsupported
native formatting is a denial requiring a reviewed parser extension, not proof
that the circuit is invalid. Extra/missing/duplicate parameters, includes and
analyses are rejected. AC/TRAN compare the complete supported option set; DC
compares the bound statement digest. All remaining normalized statements retain
order and are hashed together, covering registered topology/stimulus/load and
opaque expressions. The registration's reviewed digest is the source of truth;
the compiler never learns a new expected digest from the candidate input itself.

A PASS is `LOCAL_EFFECTIVE_INPUT_MATCHED`. It includes operation/plan/registration/
template/input hashes and source/state declarations. Actual source/copy and model
attestation remain false. Model include hashes are bound by the registration but
this comparison does not open or inspect PDK/model files.

The prepared manifest also has `execution_input_sha256`, binding settings, source,
model references, script bytes and operation identity beyond the existing operation
plan. A future provider must atomically bind and attest this identity before
reservation. The existing legacy plan alone does not authorize arbitrary generic
analysis settings. No generic dispatch is enabled by this change.

## Remaining native work

Native provider/shared-ledger/operator authenticity, preserved owned OA/ADE copy,
fresh vendor trust/API qualification, actual new DC/AC/TRAN and bounded extraction
remain incomplete. No new ledger, worker, grant writer, budget refund/reset,
protected chmod, license change, deployment or simulation occurs here. Existing
82-attempt/9,798,942,720-byte observations stay historical until freshly read.
Two fictional RC/MOS text inputs in synthetic tests are not the required genuinely
new native circuits or clean actual-app acceptance. GREL-05/06 and native GREL-07
still require their real execution evidence.
