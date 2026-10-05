# ONBOARD-CLI-01 result v1

Starting main: `730e5bcc7bcb718433d04db00658cef65fadfcbd`, merged PR #108.
Feature branch: `feat/onboard-cli-01`. The containing feature PR identifies
integration; the private final checkpoint records actual ending SHA/tree
equality. No merge-only state synchronization PR is needed.

## Implemented capability

- Operator `verify` joins existing environment v1, design v1/v2/v3 and PDK v2
  loaders and validates every design's environment, PDK, corner and analysis
  references. Local consistency is separate from execution qualification.
- Explicit optional `--remote-preflight` reuses the existing fixed read-only
  qualification probe, binding the inspected environment bytes before transport.
- Operator `client-config` exclusively exports private Codex TOML or common
  stdio MCP JSON with explicit registry/journal paths and fixed BridgeConfig
  defaults. It cannot overwrite an existing export, change live client settings,
  create/reset a journal or grant remote authority.
- `doctor` now rejects invalid explicitly configured catalogs. Exported fixed
  concurrency string `1` parses as the same integer constant; other strings and
  concurrency levels remain rejected.
- Coherent fictional examples and a complete operator installation/registration/
  verification/configuration guide; historical standalone examples are unchanged.

There remain 48 MCP tools. No new MCP execution/path/registration API, schema
revision, execution route, voltage range, source/PDK mutation or release/tag.
See [workflow](ONBOARDING_CLI_V1.md).

## Verification and corrections

Ruff and strict mypy pass (31 source files). Frozen all-group synchronization
checks 72 packages. Focused final tests: 136 passed, one Windows symlink skip.
Dedicated security tests pass (18); secret preflight and frozen dependency audit
pass with no known vulnerabilities. Package build/install/version/uninstall and
temporary cleanup pass on final production bytes.

The initial full unit gate passed 1,446 tests with three Windows symlink skips
and 56 existing warnings. This predates the exact environment-string correction
and seven additional rejection cases. Final full unit gate: **1,453 passed,
three Windows symlink skips, 56 existing warnings** (637.89 seconds).
Skipped symlink creation is not reported as executed. No GitHub CI success is
inferred from an absent check configuration.

Three corrections of three allowed were consumed:

1. Initial source/test import and line formatting.
2. Actual exported stdio startup failed closed because the integer Literal
   rejected environment string `1`. Accept only exact `1`, preserve fixed
   concurrency and add actual subprocess config-check to export tests.
3. Private E2E fixture construction used a dict with the model-only canonical
   digest helper. Validate existing DesignProfile/DesignVariables models before
   hashing. Production contract semantics were unchanged by this correction.

All original failed verifier scripts/seals/transcripts and private catalogs are
preserved. V2/V3 verification uses fresh exclusive output identities without
resetting simulation ledgers, old evidence or replay histories. This phase's
three-correction limit does not reuse the prior PDK phase's extra allowance.

## Actual E2E and resources

The CLI registers/verifies the coherent fictional catalogs, exports JSON, and
starts an actual stdio subprocess from that exported command/args/environment
in a different working directory. It exposes 48 tools and the registered logical
design. An unqualified analysis is denied before admission/database creation.

Combined verification with the already deployed reference probe returns the
expected `executable_permissions` rejection for mode-0777 wrappers. This verifies
the fail-closed route; it is not a successful environment qualification. No
installation chmod/deployment occurs. The separately exported Codex TOML parses,
retains `writes` and submission prompt settings, and launches actual stdio using
a private reference catalog and copied prior admission database.

Legacy and registered DC/AC/trap TRAN results equal the three preserved native
results. Same-ID replay, durable server-restart lookup and terminal cancellation
no-op remain reproducible. No new job UUID is dispatched. Before/after fixed
postflight and protected-tree guards prove accounting, job trees and protected
objects unchanged; prior private checkpoints retain their original byte hashes.

New Spectre attempts, result reservations, remote deployment and paid resources:
zero. Shared accounting remains 62/500 attempts and 7,114,588,160 reserved bytes.
The broader private result ceiling, independent native-v2 storage gate, one EDA
worker and previous correction histories remain binding. The elapsed ceiling
remains absent. Private client/catalog/evidence bytes are not published.

## What another user can now do

Describe/register contracts, detect cross-file mismatches in one command and
export explicit client settings without source edits or reliance on terminal
registry variables. The documentation explains review/installation of the
fragment and initial logical MCP inspection. Live global client configuration
was not modified in this phase. Codex syntax/subprocess behavior was verified;
installation inside other MCP clients remains untested.

Generic physical execution still needs qualified environment/design/PDK
adapters and scientific variable ranges. A positive second-installation
qualification, generic measurements, public licensing/compatibility review and
release readiness remain outstanding. The repository's Proprietary license,
package 1.0.0 and actual v1.0.0 release history are unchanged. No candidate is
claimed optimal or specification-compliant; specification remains not evaluated.
FS circuit changes remain paused.

Recommended next phase: PUBLIC-RELEASE-01 readiness review of actual releases,
installation/compatibility/license gaps and honest supported/experimental scope,
before choosing semver or any separately authorized publication. Report this
phase and ask once before activating that next phase.
