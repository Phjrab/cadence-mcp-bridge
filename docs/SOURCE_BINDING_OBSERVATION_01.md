# Source binding preparation — unqualified development components

This work follows normally merged PR163 (`a713eb6b1db2a90652501bb71a3dacbe75c65460`).
It is separate from published2.1.0 and remains in2.2.0.dev0. Support remains the
professor-provided standard VM and its existing PDK. No other Cadence/PDK/host
qualification is implied. This document is a software contract, not user approval.

## Current usable scope

The operator can prepare a **local private description** of one registered
saved-operating-point DC route with one to four complete registered V/A variables:

```powershell
python -m cadence_mcp_bridge operator-binding-observation schema
python -m cadence_mcp_bridge operator-binding-observation prepare --settings RUNTIME.json --context CONTEXT --registration NATIVE_REGISTRATION.json --design-id DESIGN --analysis-id ANALYSIS --output NEW_PRIVATE_DIRECTORY
```

Use your own registered settings; the placeholders are not development credentials
or execution authority. Preparation validates the existing native registration
against the operator context and exports a request, a plan and a fixed collector
script into a new directory. Existing directories/files and all configured
contexts' journal/lock paths are rejected. Nothing is deployed, remotely read,
executed, reserved, claimed or rewritten. Repeating local preparation creates
another description, never another observation allowance.

The plan retains exact context/profile/catalog/registration, source/state tree,
request/collector and normalized packaged asset identities. Local hashes reference
content; they do not independently authenticate a remote source. The exported
collector is a review artifact. It has no standalone safe deployment or execution
procedure. Running it manually against original OA would bypass the unimplemented
operational boundary and is not this workflow.

## Fixed collector and parser

The closed request contains UUID4 observation identity, a64-hex nonce, registered
library/cell, literal `schematic`, and logical-ID/ADE-name pairs. It accepts no
property selector, expression, hierarchy traversal, script, command or filesystem
path. The shared fixed renderer matches only existing scalar string/symbol OA
property values equal to those ADE names. It returns the actual top-level instance
and master library/cell/view, property name/type/value and corresponding effective
CDF type/units/value if readable. It does not presume a voltage-source master or
infer an instance from a result node name. No callback/expression evaluation or
OA save API is requested. Cadence may load initialization code implicitly; that
runtime/library trust boundary is **not established by this template**.

The parser verifies the complete header, identity/nonce/request digest, exact
source/variable echoes, contiguous instance/property counts, complete matches,
master consistency and no aliased source property. It rejects missing bindings,
expressions, malformed/truncated/oversized data and ambiguous identities. Typed
CDF unavailable data remains partial evidence. Even a complete parsed frame is
`NOT_ESTABLISHED_BY_BINDING_SCAN` for numeric/effective qualification. Reimporting
a frame is local content validation, not fresh SSH/OA authenticity evidence.

Hard component bounds are64 top-level instances,32 properties per instance,
four matches per variable/sixteen total, and65,536 frame bytes including newlines
and framing. These are implemented and tested parser/renderer bounds, not proof
that the template executes successfully in the actual Cadence interpreter.

## Internal components and remaining operational work

The package includes review-only ordinary-user worker pieces for an exclusive
owned copy and private library mapping;64 combined source/state entries/1MiB;
8MiB stage logical/allocated usage; exact selected hashes; original/copy/ledger
guards; existing resource lock/disk floor; trusted executable/ancestor checks;
one dedicated process group;45-second EDA timeout and65,536 bytes per stream.
They are tested with disposable files/processes, not Cadence. Normal timeout
handling terminates only that group's retained identity. An uninterruptible
kernel task cannot be promised an absolute60-second remote exit; the resource
lock must not be released while its process remains active.

`BindingObservationWorker.observe()` always returns `CAPABILITY_NOT_QUALIFIED`,
`qualified=false`, runtime/library trust `NOT_ESTABLISHED`, and zero stage/process/
simulation/extraction/reservation counters. No request flag can enable it. There
is no remote dispatcher, activation command, observer SSH transport or public
MCP tool. Import, server startup, schema, preparation and doctor cannot run it.

Before enabling a real observation, finish a concrete trusted bootstrap and the
runtime/library-initialization closure guard for the exact registered source and
dependencies. Recheck the current standard VM through an appropriately authorized
bounded operation, freeze/review the final executable bytes and then obtain the
one finite observation decision. Do not present this missing operational
implementation as a mere pending approval or request simulation approval before
actual source bindings exist.

The internal claim primitive is scoped to the **retained current account/campaign**.
It uses the existing OS-account resource identity and kernel lock, preserves the
original physical predecessor and ten fixed follow-up slot records, and spends
one fixed `binding-observation-01.private.json` before any future remote dispatch.
Any existing/partial/failure record remains spent across processes, changed
helper/plan/nonce/hash and SSH aliases. Hashes of an approval record are not the
human approval itself. The primitive has no transport and preparation does not
call it. It neither reinterprets the non-EDA physical collection allowance nor
creates a new-operator initialization policy. A future supported fresh-install
observer needs its own explicit resource-domain initialization/authority contract.

## Resource and release boundary

The additive source checkpoint for this product change charges45/60, retaining
the source-bearing PR163 merge as44. Historical policies/checkpoints and spent
claims remain unchanged. That software ceiling does not authorize another
physical query, deployment, OCEAN start or candidate simulation. An OCEAN start
may consume an existing licensed session; zero simulation does not mean zero
license impact. License files/server/settings are not modified or queried here.

The next real source-binding observation needs one exact finite decision covering
one SSH/one OCEAN start, the selected owned copy/source/state, request and final
trusted package identities, strict output/stage/deadline limits and no retry.
This document is not that decision and no operational grant is generated.
Old expired/exhausted experiment grants and their consumption remain preserved.

The potential subsequent explicit V-only candidate trial is a separate step:
observed source bindings, current qualification, a valid finite grant/operator
confirmation, live shared ledger/disk and effective-input checks are required.
W/L, mixed geometry, numeric range/grid qualification and physical verification
are not added here. Published2.1.0 tag/assets are untouched; a new draft feature
PR is not approved for merge or publication by PR163's exact-head approval.

## Verification checkpoint, 2026-10-18

Ruff, mypy126 source modules, the85-tool/22-legacy declaration audit, security18
tests/secret preflight and strict locked dependency audit pass. The isolated
wheel/sdist/content/license and installed synthetic checker pass; reinstall and
uninstall preserve43 operator files and20 migration files. The new installed
checker validates schema, fixed renderer/parser, helper identities and blocked
observe; it explicitly does not claim successful installed preparation or
authenticated worker construction. Neither installed SDK checks nor synthetic
owned-process tests are actual Cadence or app evidence.

The local Windows full run reports4433 pass/428 platform skips/56 warnings and
five failures at the unchanged real physical-disk-floor gate: the C: test volume
had only180,244,480 bytes available. The failed records are retained. Targeted
accounting rechecks in a new disposable D: test directory with adequate physical
capacity pass85 tests/five Windows POSIX skips, including all five earlier failing
cases. No product disk check, existing result, consumed reservation or policy is
modified. Final exact-head hosted Windows/POSIX and
fresh automated review remain separate gates; do not treat this checkpoint as
their completion or as permission to activate the observer.
