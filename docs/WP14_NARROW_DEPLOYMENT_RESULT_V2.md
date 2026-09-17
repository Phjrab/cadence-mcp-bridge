# WP-14 narrow deployment result v2

Result: BLOCKED. One approved attempt failed during the first read-only preflight transport.

The user's 2026-09-17 instruction approved continuing the remaining work without repeated
approval prompts. This was applied to the existing bounded WP-14 deployment contract only.
No original design/PDK write or retry authority was inferred. Base main is PR #36 merge
`b9e138c5fefdafd9dc0101776a694199517cd6e6`.

## Fixed bindings and evidence

- Package: `96d8f001776eb61da5ef09ba3945d988bf587c716fea95a35ad890aa95ba2431`
- Deployer: `3251100bafde66c0df4179d36462de8029c6856b59111629dba627c1b668fddc`
- Reviewed preimages: `0a469a94880383ffeada740c3b19e261ba5b50382ddf360a91243c7054782ba7`
- Activation record: `095bbda61bf7f0a8d11fe1428aec0ce2139183586b8edcaf98346ed646bc08c5`
- Durable claim consumed at: `2026-09-17T08:20:37.8800486+00:00`
- Local WhatIf package/assets/authorization validation: PASS; no transport or claim.
- Live invocation count: 1; retry count: 0.

The first `Invoke-FixedSsh` did not return the required preflight success marker. The
deployer raised `A fixed WP-14 transport failed. No retry, cleanup, or fallback was attempted.`
The corresponding code path means nonzero process exit or nonempty stderr; it deliberately
suppresses raw stderr and does not report the exit code. Consequently the exact failing
remote assertion, SSH cause, and old-runner version execution status are unknown.
An active Virtuoso process, missing parent, identity/preimage drift or SSH failure must not
be asserted without evidence.

The snapshot, SCP uploads, installs and final verification are sequentially after the failed
preflight and were not reached. No deployment or discovery success is claimed. No subsequent
remote diagnostic, cleanup, retry, Cadence invocation or design access was performed.
The consumed authorization is preserved locally, excluded using `.git/info/exclude`, and
not published. The durable claim is preserved and must not be reset or removed.

## Remaining work

First design a bounded diagnostic that distinguishes the preflight conditions without
re-running deployment or disclosing raw output. Existing authority may support local work,
but does not make a consumed deployment attempt reusable. Any future retry requires a
reviewed recovery contract; there is no automatic retry, UUID replacement or ledger reset.
WP-14 remains blocked; PUBLIC and deployment_enabled=false remain unchanged.
