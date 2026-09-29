# WP-15 — PDK abstraction design v1

## Decision and scope

This is a repository-only design contract, not a PDK inventory, loader, deployment,
simulation profile, MCP tool, or execution approval. The machine-readable public
shape is `docs/schemas/technology-adapter-v1.schema.json`; the gpdk090 regression
seed is `docs/technology/gpdk090-v4-6-regression.json`. The seed is deliberately
`draft`, `execution_authorized=false`, and contains no physical bindings. No
repository or remote runtime consumes either file.

The user explicitly requested WP-15 while WP-14 remains blocked. This design
does not resolve the VBIASN/VBIASP scientific baseline, ADE analysis drift, VDD,
VCM, load condition, source/ADE-state semantic equivalence, or snapshot freshness.
The VDD=1.0 V, VCM=0.5 V, and no-added-external-load entries in WP-14 history are
review hypotheses, not observations or adapter defaults. Parameterized execution
and PDK porting remain disabled.

## Authority and trust separation

| Layer | Allowed content | Forbidden content or authority |
| --- | --- | --- |
| Public adapter document | Schema version, logical technology ID and release, semantic roles, opaque binding IDs, capability status, evidence IDs and digests | PDK file bytes, model/deck paths, actual library/cell/layer numbers, license terms, credentials, raw design data |
| Operator-protected binding | Exact PDK-approved master, CDF/PCell, pin/parameter, model section, layer/purpose, grid, deck and stream mappings after official onboarding | Caller-supplied path/code or publication to this public repository |
| Runtime policy | A future fixed, versioned loader that checks both layers and independent approval before any operation | Automatic promotion of a schema-valid document into execution authority |

The public schema accepts only bounded logical identifiers, never a path, command,
SKILL/OCEAN fragment, netlist, model file, rule deck, or raw PDK property. A binding
reference is an opaque identifier; resolving it is outside WP-15. The v1 schema
cannot claim `reviewed` or `execution_authorized=true`; both require a future
separately reviewed schema/loader change and user approval. A reviewed label
alone would still not prove that a physical mapping is valid.

## Semantic contract

| Domain | Public semantics | Protected binding and later validation |
| --- | --- | --- |
| Devices | NMOS/PMOS/R/C/diode/IO roles, logical pin roles, parameter roles and units | Exact library/cell/view, CDF/PCell parameters, total versus finger width, m/nf, bulk and pin order; round-trip against official PDK |
| Models and corners | Simulator ID, logical process and RC corner IDs, capability status | Exact approved model/section binding, temperature/mismatch support and source digest; no inferred NN/FF/SS completeness |
| Layers and vias | Routing/via role IDs and nullable grid/DBU metadata | Exact layer-purpose pair, via definition, grid and stream mapping from official source |
| Verification | DRC/LVS/PEX backend IDs and status | Fixed executable/version/license/deck/runset/result parser; known-clean and deliberately failing fixtures before any PASS claim |
| IO and stream | Logical pad/stream capability status | Approved pad/ESD registry, stream map, hierarchy and top-cell rules; no tapeout authorization |
| Provenance | Official release ID, protected manifest digest, documentation/approval references, evidence IDs | Operator verifies source bytes, license/access policy, environment compatibility and drift before activation |

Process and RC corners are separate axes. A model or deck ID is never a caller
path. A missing, ambiguous, stale, or conflicting binding is `unverified` and
blocks the associated capability. Schema validity alone cannot prove electrical
equivalence, DRC/LVS/PEX signoff, or fabrication readiness.

## gpdk090 regression seed

The seed records only the existing repository's `gpdk090` v4.6 identity and the
case-preserved historical Spectre `NN` actual-profile observation. It does **not** claim a full
corner set or validated device, layer, PCell, deck, pad, model-file, or stream
binding. All such collections are empty/unverified. Its regression role is to
test that the public schema preserves the known identity and rejects promotion,
extra fields and path-like identifiers. It is not a functional Cadence regression
run and does not alter the fixed v1.0.0 profile.

MyChip (or any fabrication target) receives no guessed technology ID, process
node, voltage, device name, layer, corner, pad, or deck in this WP. Officially
provided and license-permitted source material, exact hashes, secure storage and
separate onboarding approval are prerequisites. A port must revalidate device
mapping, supply/headroom, sizing and bias, layout, verification and signoff; it
cannot scale gpdk090 geometry or reuse its simulation PASS as signoff.

## Threat model and gates

| Failure mode | Required control |
| --- | --- |
| Arbitrary path/code injected through adapter | Closed public schema, path-free opaque IDs, no loader/MCP interface in WP-15; future private binding must use fixed reviewed allowlists |
| Public leak of proprietary PDK or license data | No physical mappings or content in Git, semantic review plus secret scan before push, private operator storage only after policy review |
| Cross-PDK or stale binding substitution | Exact technology/release, schema version, protected manifest/documentation digests and approval reference must match the current environment |
| Invented capability or false clean result | Unknown stays unverified; backend/parser requires positive and negative fixtures with complete evidence; no inference from tool banner |
| Model/corner or source/state drift | Process/RC/temperature and source revision independently checked; WP-14 baseline blocker remains separate |
| Accidental activation of a draft | `execution_authorized=false` in schema and seed; no runtime consumer; future activation needs a new explicit contract |

## Acceptance criteria for this WP

1. PR #53 reviewed HEAD and merge are in latest `origin/main`; the branch starts
   from that exact commit, with a clean tree and PUBLIC visibility.
2. The public schema parses and validates the gpdk090 regression seed.
3. Negative schema checks reject `execution_authorized=true`, unknown fields,
   path-like logical IDs and wrong schema version.
4. The seed contains no device/layer/deck/stream/PCell physical bindings and
   makes no signoff, simulation, freshness or scientific-baseline claim.
5. Device, parameter, model/corner, layer/via, verification, IO/stream and
   protected source-of-truth responsibilities are specified.
6. Threats and fail-closed activation, provenance, secrecy and drift gates are
   documented without exposing an arbitrary execution interface.
7. WP-14 remains blocked and its unverified conditions remain unpromoted;
   `deployment_enabled=false` and parameterized execution remain unchanged.
8. No source code, MCP tool, remote runner, profile, PDK, OA/ADE/design data,
   authorization, claim or lock is changed; no SSH/Cadence/simulation runs.
9. Documentation/schema validation, existing local static/tests/security gates,
   feature-only commit/push and remote SHA verification pass before STOP.

## Deferred work

A later exact WP must define and privately validate protected bindings, official
PDK provenance and license policy, gpdk090 functional regression fixtures, and
MyChip secure onboarding. WP-16 remains the next planned capability inventory,
but neither it nor any adapter activation starts in this execution.
