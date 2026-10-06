# Licensing scope and third-party material

Apache-2.0 covers Cadence MCP Bridge's original source code where the project
has the right to license it. It does not relicense external software, vendor
material, or imported material with unverified rights. This file records scope;
it does not replace an external component's license or required attribution.

## Separately installed dependencies

| Component | Reviewed local version | Observed license | Classification |
| --- | --- | --- | --- |
| MCP Python SDK | 2.1.1 | MIT | DEPENDENCY_ONLY |
| mcp-types | 2.1.1 | MIT | DEPENDENCY_ONLY |
| Pydantic | 2.13.4 | MIT | DEPENDENCY_ONLY |
| pydantic-core | 2.46.4 | MIT | DEPENDENCY_ONLY |
| pydantic-settings | 2.15.0 | MIT | DEPENDENCY_ONLY |

Versions/licenses were read from installed distribution metadata and license
files, not inferred from product names. Direct runtime dependencies are MCP,
Pydantic and pydantic-settings. Extras/transitive/build/development dependencies
are separately installed and remain under their own terms; the private audit
records the full installed inventory. Bridge artifacts do not vendor these
packages, binaries or their license grant. Future bundling needs a new audit
and must retain applicable notices/license texts. MIT dependency notices remain
with those separately installed distributions; this table is not their license.

## External EDA environment

Cadence Virtuoso, Spectre, ADE and other Cadence software, license entitlement,
license-server access, MCP clients and PDKs are not supplied or licensed by this
project. Users must independently obtain and comply with their required licenses
and access only environments they are authorized to use. The bridge supplies
no commercial binary, key, license file, credential, model library, technology
file, rule deck or foundry data. It implements no licensing bypass.

The gpdk090 adapter is original integration/reference code containing logical
IDs, capabilities and registered local references. The actual gpdk090 PDK is
user-provided/local and outside the Apache-2.0 grant. No general redistribution
right for gpdk090 is asserted. No PDK files or model definitions are bundled.

## Imported planning material: LEGAL_REVIEW_REQUIRED

`docs/agent_plan/` was imported from the user-provided
`CADENCE_MCP_FINAL_PROMPT_PACKAGE` in PKG-INTEGRATE-01. Its integration manifest
records 178 imported files, including an adapted package-verification helper.
The import record proves provenance/integrity, not copyright ownership or a
redistribution license. No explicit licensing grant was found in that package.

Do not interpret the root LICENSE as relicensing this material. Human review
must establish its author/rights and distribution terms before including it in
an Apache-licensed repository bundle. It remains accessible in existing Git
history; no historical deletion/rewrite is performed. This uncertainty blocks
a blanket Apache claim for the whole repository, not the separately audited
original-code wheel/source package, which excludes this directory.

New Git archives at commits containing the reviewed `docs/.gitattributes`
exclude this directory. `IMPORT_EXCLUDED_VERIFIED` applies only to inspected
exact-commit artifacts; it is not rights clearance or publication authorization.
Web browsing, clones, forks, bundles, older commits and existing downloads retain
their separate scope. External references and decision adaptations outside the
directory are recorded in [the boundary audit](docs/AGENT_PLAN_EXPORT_BOUNDARY_V1.md);
path exclusion is not a blanket statement about all derived content.

`archive/LEGACY_INPUTS.zip` is referenced by that import record but was excluded
from Git and remains absent. No rights or redistribution claim is made for it.

## Generated and example material

Schemas, compatibility snapshots and hashes generated from original bridge
contracts, plus synthetic fixtures/fictional examples, are distinguished from
Cadence/PDK files and private results. Generated output is not evidence of a
vendor license grant. The curated source distribution includes only the package
source, metadata, lock, README, reviewed Git exclusions and these license/notice files; it is not a full
operator/deployment checkout. No imported planning archive or private evidence
is included. See the repository's licensing audit for verification and limits.
