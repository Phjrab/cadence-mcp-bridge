# Release notes draft: 2.0.0

**NOT_FROZEN / NOT_RC_READY / DO_NOT_PUBLISH.** Version2.0.0 reflects the required
launch migration. Exact installed2.0.0 has actual new Codex job/extraction/result/
same-ID retry/restart evidence. Final integrated artifacts, installation transitions
and candidate commit/file/hash set remain pending; the release gate is **BLOCKED**.

## Breaking launch change and migration

A bare `cadence-mcp-bridge` or `python -m cadence_mcp_bridge` launch now selects
the operator setup path. Missing private setup returns SETUP_REQUIRED and cannot
contact the historical developer VM. Published1.0.0 used the historical reference
path for a bare launch, including its generated Codex configuration. This required
migration is why2.0.0 is recommended instead of an additive1.1.0 number.

Existing users who intentionally retain historical reference behavior must back
up their client configuration and append explicit `serve`:

```toml
args = ["-m", "cadence_mcp_bridge", "serve"]
```

Keep the existing legacy runner, policy, accounting, results and journals. New
operators must export the installed starter, register their own environment and
circuits, complete trust/domain/authority setup and use an exported explicit
`serve-operator` configuration. Installation and registration alone do not grant
execution authority. A context cannot silently fall back to the reference circuit.

The original22 MCP input/output schemas and annotations are preserved; explicit
legacy routing exposes the85-tool compatibility surface. Eleven native tools are
conditional on complete operator bindings. These counts describe the surface,
not successful execution or universal environment support.

## Intended standard-VM capabilities

The release targets the professor-provided CentOS/Cadence/PDK VM, or an equivalent
reproduced installation, run in personal VMware. Each operator supplies private
SSH/host identity, ordinary guest account, workspace, circuit library/cell/view/
ADE state, registry, result paths, journals and confirmed resource scope. The
bridge does not bundle the VM, Cadence, PDK or license entitlement.

The common implementation registers owned circuits and saved ADE inputs, creates
work copies, checks effective inputs, runs allowed DC operating point/typed AC/
typed TRAN, extracts registered bounded results and coordinates a registered
bounded1D Sweep. It uses common fixed helpers rather than circuit-specific code.
Registered measurement/specification definitions remain bound to provenance,
units and conditions. Missing targets yield NOT_EVALUATED; these tests make no
claim that a QA circuit meets an invented performance goal or is optimal.

Current actual standard-VM evidence covers two distinct new inverter/comparator
sources through the same registered implementation. Installed8aad03d/721fd231
completed inverterAC/TRAN, comparatorDC/AC/TRAN and AC two-point Sweep; exact
installed32acbb4/553b90fa completed a new inverterDC through actual Codex.
All six analysis routes automatically extract bounded results and protect effective
inputs/source/model baselines. The later bundle changes installer.py alone; all
worker/rendering/input/reader and other native bytes match. Same-ID/new-process
Sweep recovery and actual Codex restart/query/retry add no spend. QA specification
controls cover PASS/FAIL/NOT_EVALUATED/CONDITION_MISMATCH without invented goals.
Final integrated artifacts and installation transitions remain separate gates.

Observed reference versions are CentOS6.5 i686/Python2.6.6, Virtuoso
IC6.1.5.500.15 and Spectre12.1.0.347.isr3, with ordinary OCEAN execution observed
but no standalone OCEAN version. Actual host evidence is Windows/Python3.12.10.
Operator preflight must observe the actual installation instead of hardcoding
these reference values. Other physical PCs, host OS combinations, Cadence versions,
PDKs and cloud/multi-user EDA are unqualified or deferred.

## Installation, accounting and recovery

The wheel/sdist include fixed helpers and fictional operator templates. New
operators do not import a developer UUID, authority file or journal. Genuine
zero-history initialization and retained-installation reuse are separate flows;
the current already-used VM refuses fresh accounting. New host settings can
retain the same remote ledger and replay protection. Imports, doctor and server
startup do not provision or perform administrator repair automatically.

Operators choose and approve their own resource limits. The current validation VM
retains all consumed attempts and reservations under its existing authorized policy;
those settings are not defaults for another operator. Each admission reads current
accounting/consent/disk conditions. Failures remain charged, disk floors and per-job
size checks stay active, and no automatic refund/reset/deletion exists.

Minimum installation metadata repair requires the actual VM owner's authority,
exact targets and recoverable records. MCP, SSH, OA/ADE copies, EDA, extraction
and journals run as the ordinary user. There is no public sudo/chmod/chown/shell
or arbitrary SKILL/OCEAN interface, and no license or PDK content modification.

Keep old exact wheels, client settings, bundles, grants and journals when updating.
Immutable stage/update/repeat and append-only history preserve prior evidence.
A private published-v1/40c host code swap and rollback/re-upgrade preserves
original schemas and eight disposable durable/legacy files. Historical versioned1.0-to2.0 rehearsals passed; the final artifact transition
must still be checked at the exact candidate.
Old v1 cannot run `serve-operator`; restore explicit old client settings and do
not reset new operator state. Host package rollback and native bundle rollback
are separate compatibility checks. Uninstall must preserve operator/remote data.

## Unsupported and deferred capabilities

Fresh generic destructive storage is disabled. Active simulator termination is
unsupported; cancellation is pending-only. Historical legacy capabilities keep
their own policy and evidence. General PM/offset/slew, arbitrary PVT/PDK and
unlimited optimization are not claimed. Claude actual app qualification is
separately deferred; SDK protocol checks do not establish real app support.

Unsupported netlist dialects, hidden analyses, expressions or unregistered model
includes fail closed. No generic shell, caller script/netlist execution, unrestricted
OA/PSF access or automatic repair of live locks is exposed. Preserve failed and
unknown jobs rather than retrying with new identities or deleting their journals.

## Distribution and pending public decision

Apache-2.0 covers original bridge material within the reviewed rights scope.
Cadence/PDK/client/dependency terms remain separate. Imported planning remains
LEGAL_REVIEW_REQUIRED and is excluded from curated packages and audited new
source archives; exclusion does not clear history or external adaptations.
Exact final source ZIP/tar.gz, wheel/sdist, install contents, secrets/notices,
upgrade/downgrade and asset hashes must pass before this draft can be finalized.

The proposed initial destination is `Phjrab/cadence-mcp-bridge` GitHub Releases.
No tag, Release or upload is authorized yet. Final publication needs one approval
of the exact version/commit/files/hashes and verified scope. PyPI/MCPB/marketplace
publication and external promotion are separate decisions. This draft does not
change the published1.0.0 release or its historical notes.
