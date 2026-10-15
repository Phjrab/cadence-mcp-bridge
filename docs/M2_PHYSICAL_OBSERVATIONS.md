# M2 physical capability observations

M2-FOUNDATION-01 provides a local, path-free physical capability inventory and
assessment API. It records the evidence available for the current standard VM;
it does not run Cadence, create OA objects, extract results, change configuration,
or qualify DRC/LVS/PEX. It is development code, not part of the published 2.0.0.

## Evidence contract

`cadence_mcp_bridge.physical_capabilities` exposes:

- `PhysicalScope`: the logical environment and PDK IDs and their exact registered
  binding SHA-256 values. Evidence from another binding cannot join an inventory.
- `PhysicalCapabilityObservation`: one capability/facet observation with its
  source origin, timezone-aware observation time, evidence/source SHA-256, and
  logical evidence ID. An observed subject also requires its own hash. Interfaces
  require a logical interface ID. No commands, paths, raw help, license values,
  PDK text, arbitrary diagnostic strings, or execution authorization are fields.
- `PhysicalCapabilityInventory`: at most one current observation per
  capability/facet. Older inventories remain separate evidence; a duplicate
  cannot silently replace a conflicting result.
- `assess_physical_capabilities(inventory, assessed_at=..., ...)`: pure local
  assessment, returning every fixed capability and all five facets, retaining the
  input observations and an inventory hash. Its default age bound is 24 hours;
  callers supply an explicit assessment time and can select a bounded age policy.

The capabilities are `layout-db`, `pcell`, `technology-library`, `dbu`,
`layer-purpose`, `via`, `drc`, `lvs`, and `pex`. The facets are installation,
interface, deck, license, and execution. `INSTALLED_OBSERVED`,
`INTERFACE_OBSERVED`, and `DECK_OBSERVED` report only the corresponding current
VM observation. They do not imply a usable combination. Each capability retains
`execution_qualified=false` and `signoff_qualified=false`.

License and execution start as `LICENSE_UNVERIFIED` and `EXECUTION_UNVERIFIED`.
Read failures, permission denial, timeout, malformed responses and a missing
candidate within a bounded search are `UNKNOWN`, never proof of VM-wide absence.
A known missing registration or explicitly unsupported registered combination
can be `BLOCKED`. A license environment variable being set cannot be submitted
as successful license or execution evidence.

Synthetic fixtures and repository contracts retain their provenance and remain
unverified. Historical VM observations outside the selected age bound and
future-dated observations cannot become current observations. The contract
deliberately has no accepted `VERIFIED` state: a future execution qualification
contract must bind exact inputs/revision/tool/deck/options and both known-clean
and deliberately bad controls. A file hash identifies bytes; it does not prove
their truth, safety, licensing or physical correctness. This API validates
operator-supplied evidence structure, not an independent attestation signature.

Example local API use with an already registered scope:

```python
from datetime import UTC, datetime
from cadence_mcp_bridge.physical_capabilities import (
    PhysicalCapabilityInventory, PhysicalScope, assess_physical_capabilities,
)

scope = PhysicalScope(
    environment_id=registered_environment_id,
    environment_sha256=registered_environment_sha256,
    pdk_id=registered_pdk_id,
    pdk_sha256=registered_pdk_sha256,
)
inventory = PhysicalCapabilityInventory(scope=scope)
assessment = assess_physical_capabilities(inventory, assessed_at=datetime.now(UTC))
print(assessment.model_dump_json(indent=2))
```

An empty inventory explicitly reports all unknown/unverified items. It is not
evidence that a remote probe took place. The returned `remote_contact=false`
describes the local assessment operation; individual supplied observations keep
their own current/retained VM or synthetic origin.

## Existing interface audit and current attempt, 2026-10-15

The existing source was inspected before selecting a read. The fixed legacy
`cadence-runner` `list-libraries` and `inspect-cellview` handlers invoke only
`discovery_json.py` with the registered allowlist. That helper reads the fixed
`cds.lib` definitions and checks allowlisted filesystem entries. These handlers
do not invoke EDA, reserve budget, create directories or append audit events.
The allowlist includes schematic/symbol views, not layout/technology data.

The similarly named `discovery-health` starts OCEAN and Virtuoso and creates
logs. The general `health` handler runs Virtuoso/Spectre version commands and
ensures runtime directories. Neither was called for this investigation. The
environment qualification probe also runs bound version switches; its native
DC/AC/TRAN evidence does not establish physical tool support.

Two bounded attempts are retained privately:

1. A direct installed-package harness checked the configured runner hash against
   the reviewed legacy metadata handler before SSH. The current operator runner
   binding differs, so the guard stopped before transport. No handler was
   substituted, no pin was weakened and no second transport was invented.
2. The existing connected `cadence-native-qa.cadence_list_libraries` returned
   `invalid_configuration` / `RUNNER_SETUP_REQUIRED` with `retryable=false`.
   That interface did not yield current VM metadata. No inspect call, bootstrap,
   deployment, EDA launch or further retry followed.

The private receipts are `.tmp/m2-fixed-discovery-v1/` and
`.tmp/m2-physical-interface-attempt-v1.private.json`; they are not distribution
files. These failures show the current read path is unavailable for this
investigation. They do not establish that any installed physical tool, API,
library, via or deck is absent.

| Requested capability | Current actual physical evidence | Required next bounded method |
|---|---|---|
| Layout DB / PCell | UNKNOWN | Fixed read-only API inventory on a registered disposable or owned cellview; no object creation |
| Technology library / DBU | UNKNOWN | Registered technology binding and typed DBU read; distinguish declared units from observed database units |
| Layer-purpose / vias | UNKNOWN | Bounded typed inventory for the bound technology; no proprietary technology text |
| DRC tool / deck | UNKNOWN | Fixed installed executable metadata plus bound deck identity; version/help side effects reviewed separately |
| LVS tool / deck | UNKNOWN | The same bounded metadata strategy with the exact LVS combination |
| PEX / extracted representation | UNKNOWN | Exact installed backend/interface/deck and supported representation metadata |
| Licenses for all physical capabilities | LICENSE_UNVERIFIED | An approved feature-specific status mechanism; never infer entitlement from environment SET |
| Actual physical execution for all capabilities | EXECUTION_UNVERIFIED | Separate authorization and same-revision clean/bad-control lifecycle qualification |

The checked reference PDK contract still marks layout/DRC/LVS/PEX unqualified.
The older technology description leaves DBU, layers, vias and physical backend
bindings unset. Those are repository declarations, not new VM absence evidence.
The retained fast-step native preflight identifies a previous ordinary-user
native success; it has no physical API/deck/license observation and is not
promoted into this matrix. Historical environment versions remain historical;
this read did not freshly verify them.

## Next investigation boundary

First reconcile the existing configured metadata discovery route with its
reviewed installed runner using the current operator context. A new physical
collector is not deployed in this foundation. Before such a collector is run,
review its exact fixed targets from registered technology/installation bindings,
bounded output, timeout, ordinary-user behavior, source hashes and any potential
tool startup/license/cache effects. Keep private source material local and return
only typed metadata plus evidence hashes. Do not perform a whole-VM scan.

Actual SKILL/OCEAN invocation, new remote probe deployment, OA creation, DRC/LVS/
PEX computation or administrator repair require the next specific execution
scope. Current lack of that collector does not block local revision and
schematic-plan development. A later physical execution proof must also keep the
design revision, deck/tool identity, process success, result validity and signoff
claims separate; file presence and an exit-zero banner are insufficient.

## Local validation scope

The focused tests cover observed-versus-qualified separation, negative read
outcomes, synthetic/history/future timestamps, environment/PDK substitution,
conflicting duplicate facets, deterministic round trips, invalid hashes,
unapproved fields and constructor-bypass revalidation. These are local contract
tests, not physical execution or license tests. No new simulation, extraction,
reservation, remote deployment or protected-data modification was requested by
the selected metadata routes.
