# Standard VM operator setup (release work in progress)

Support is the professor-provided CentOS/Cadence/PDK VM, or an equivalent
reproduced installation, running in a personal VMware. Current VM observations
are Virtuoso IC6.1.5.500.15 and Spectre 12.1.0.347.isr3. OCEAN has no separately
observed version. Recheck executable paths, hashes and versions on your VM;
these observations are a reference, not hardcoded executable identities.
Other Cadence/PDK/OS/physical-PC combinations are unqualified.

This starter is included in the wheel and sdist. It contains fictional,
non-executing examples (zero resource authority). It contains no private journal,
SSH key, circuit, PDK model, results or license. Replace example settings with
observed operator data. Never copy another operator's authority or identifiers.
Current native routes require explicit configuration, a trusted installed bundle
and OS-operator confirmation. Import, doctor and server startup do not provision.
Release acceptance still requires installed fresh-operator and actual-client proof.

## Install and local configuration

Install Python 3.12 or 3.13 on the Windows host in a dedicated virtual environment;
do not change the guest system Python. Install the verified wheel and its locked
runtime dependencies from the release archive. Verify the archive SHA-256 list
before installing. Do not install this bridge or run EDA as root.

Use `python -m cadence_mcp_bridge operator-starter --output NEW_EMPTY_DIRECTORY`
to export this guide and three fictional templates. The command is local-only,
exclusive and never overwrites an installation. Run `doctor` for host prerequisites.
Every command below has `--help`; schema commands print the complete closed JSON
schema rather than accepting shell, SKILL or OCEAN text from a model.

Register your own SSH alias, known host key, ordinary guest account and private
workspace. Keep host-key checking on and credentials in your SSH agent/config.
Choose a managed root, job/result location and resource limits in environment.json;
protected roots cover executable installations and PDK/model dependencies. Set
observed executable digests and versions. The validation VM's 16GiB ceiling is
not a default for new operators. Zero example limits must be replaced by the
VM operator's explicitly authorized scope. Disk floors remain required.

`environment schema`, `design schema --schema-version 4`, `pdk schema` and
`runtime schema` describe the contracts. Use schema8 when registering native
Sweep and specification contracts. Set source library/cell/view and saved ADE L
state in the design registry. Choose `owned_copy_only` for execution. Record
all variables, units, bounds, step/fixed policies and explicit range review;
register allowed analyses and measurement contracts. PDK registration describes
the existing licensed adapter/corners; it does not install or modify the PDK.
Qualified reference adapters cannot be rebound to another circuit. Unqualified
metadata alone is not evidence of native compatibility or permission to execute.

Profiles and contracts are bound by SHA-256. File bindings use exact file bytes;
profile/variable/analysis/measurement bindings use canonical JSON (sorted keys,
compact separators, UTF-8, the model's validated JSON representation). Editing a
contract requires updating its dependent binding hashes; never substitute zero
hashes as approval. `design validate`, `pdk validate` and
`verify --profile ENV --design-registry DESIGNS --pdk-registry PDKS` catch local
binding mismatch. `verify --remote-preflight` adds a read-only VM qualification.

Create runtime settings from `runtime schema`, with absolute host paths to your
three registries and their exact hashes, a distinct context ID, your explicit
authority reference, logical `shared-ledger`, and private analysis/sweep journals.
Bind the installed runner hash. `runtime verify --settings RUNTIME --context ID`
checks selection. Remote identity is the same managed resource domain regardless
of the host journal; changing a local journal cannot reset remote accounting.

## Trust, installation and resource domain

Run the read-only runner trust/preflight path for your observed environment.
`runner repair-plan --profile ENV --output NEW_PLAN` enumerates exact code
paths, symlinks, metadata, contents and proposed shared-write-bit removals.
`runner export-repair-helper --output NEW_HELPER` exports the fixed helper.
Your VM owner must approve that exact bounded plan, preserve rollback information,
and apply only its listed targets via their normal administrator access. See the
exported helper's `--help` for apply/verify/rollback and exact plan hash arguments.
No recursive broad chmod/chown, license changes or security disabling is needed.
Do not blindly trust unexplained content changes. Recheck under the normal user.
Writable caches, logs and results must remain separate from executable code.

`runner bundle`, `runner export-installer`, fixed `runner preflight`,
`runner install` and `runner verify` prepare/install the coexisting operator
runner. Each accepts only package-bound assets and expected hashes. Old runtime
versions, legacy launcher and pointers are retained. Stage/update is never an
import side effect. Follow command output and help for exact plan/installer paths.

Fresh install: `domain export-setup-helper-bundle`, `domain stage-setup-helper`,
`domain plan-fresh` then explicitly authorized `domain apply-fresh` create an
empty domain only when no prior ledger/history exists. Record the resulting
identity-manifest hash. Existing install: use `domain plan-existing` and
`domain register-existing`/`domain apply-existing` to preserve the actual ledger,
locks, identity and journals. A fresh domain is not a remedy for quota exhaustion.
Keep the old policy versions, failure evidence and reservations. No refunds,
deletions, reset or quota increase are part of ordinary installation.

## Enroll your circuit and automatic reader

Save an ADE L state for each intended analysis. Export its baseline Spectre input
from an operator-owned working copy and keep the file privately on the host.
Do not modify the original OA/ADE or PDK to create a baseline. The current parser
supports saved DC operating point, typed AC start/stop/points-per-decade and typed
TRAN stop/max-step. Hidden extra analyses, expressions in explicit parameters,
unregistered includes and unsupported static statements fail closed. A baseline
netlist is input evidence; it is not a successful simulation.

`native-registration schema` defines the observation request: an explicit
OperationRequest with all registered values/units and result reservation, source
cell/state, named library paths, selected model paths/sections, analysis inputs
and the absolute local baseline_netlist path. The baseline's proprietary contents
stay local. The fixed read-only SSH collector observes source/state/library tree
hashes and the complete trusted model closure; it does not netlist, reserve or run.
Source lock/recovery files cause rejection and must never be removed to pass it.

Run once per design/analysis:

```
python -m cadence_mcp_bridge native-registration observe --settings RUNTIME --context ID --request REQUEST --output NEW_PRIVATE_RECORD
```

Prepare reader definitions using `native-registration reader-schema`: logical
node selectors, positive-terminal source current `/SOURCE/PLUS`, supply/bias/
stimulus roles, explicit power scope, AC transfer input/output references and
frequencies, and maximum bounded samples. Select actual intended circuit signals;
the bridge cannot infer scientific output meanings. Native standard-VM rendering
maps these logical selectors to the verified PSF naming, without circuit helpers.

Assemble one or more routes, repeating the three aligned arguments per route:

```
python -m cadence_mcp_bridge native-registration assemble --settings RUNTIME --context ID --request REQUEST --record RECORD --reader-definition READER --identity-manifest-sha256 DOMAIN_SHA --output NEW_REGISTRATION
```

The assembler checks baseline, profile, model, source and measurement bindings,
automatically fills canonical ADE/reader hashes, and validates the common native
projection. It neither manufactures approval nor contacts the VM. Outputs are
exclusive private records. No circuit-specific Python helper or developer journal
is required. Re-observe and use a new output filename after source/baseline drift;
do not overwrite historical evidence.

## Confirm, activate, run and recover

`native-runtime bundle --settings RUNTIME --context ID --registration REGISTRATION
--output NEW_BUNDLE` prepares an immutable local bundle and reports its manifest
hash. Follow the output's native provider binding for your runtime context.
`native-runtime stage --bundle BUNDLE --expected-manifest-sha256 SHA
--operator-authority EXPLICIT_OWNER_RECORD` installs the fixed assets as the
ordinary user. `operator-authority export-helper`, `stage`, `confirm` bind your
explicit grant to the same domain/runner/registry/policy. Plan files are not user
approval; that authority must come from the VM operator's actual decision.

For new narrowly scoped grants use the versioned design/analysis pair schema;
retained v1 grants have their historic all-design/all-analysis product meaning.
The remote confirmation/native gate accepts the same exact v2 pairs and rejects
unselected combinations. Its parser/gate is tested on the standard VM Python2.6;
a new deployment must still qualify its actual jobs. Unsupported versions reject.
Do not silently broaden a retained grant.
Check its expiry, per-grant scope and current global ledger before each new job.
Use `native-runtime activate`, then `native-runtime preflight`/`inspect` to prove
active installation, normal UID, executable trust, current policy/disk and counters.
A stage/plan/activation success is not Cadence simulation acceptance.

Set native provider and grant paths/hashes in the explicit runtime context.
`operation plan` produces the immutable plan hash; `operation submit` requires
that hash and a unique chosen operation UUID. `operation reconcile`, `result` and
`journal-status` query the original identity. Reuse the SAME UUID and plan after
response loss/restart; do not generate a fresh UUID to bypass an uncertain job.
Prior reservation/extraction failures stay charged. Cancellation is pending-only;
no generic kill, sudo or arbitrary shell is available in MCP.

`native-sweep schema` and plan/submit/advance/status/result coordinate a bounded
registered 1D series. Each point is an ordinary job under the same accounting;
repeat/restart preserves parent/child identities. Specification targets must be
explicit registered contracts. No target yields NOT_EVALUATED; wrong conditions
cannot be promoted to PASS. No automatic optimization or unlimited search exists.

Export the client fragment with `client-config --runtime-settings RUNTIME
--context ID --profile ENV --design-registry DESIGNS --pdk-registry PDKS
--journal ANALYSIS_JOURNAL --sweep-journal SWEEP_JOURNAL --format codex
--output NEW_FRAGMENT`. Review and add that fragment to your own client config,
then restart that MCP connection. The launch command is `serve-operator`; legacy
`serve` does not select operator routing. Validate one NEW actual job in the client,
query result, repeat the same ID and restart the connection to check no extra spend.
SDK tool negotiation alone is not actual-client acceptance.

## Update, troubleshooting and preservation

Keep the exact old wheel/runtime/registration/settings and journals. Install the
new host wheel in its isolated environment; import/startup cannot update the VM.
Stage the new immutable bundle; use explicit `native-runtime update` with both
previous and replacement manifest hashes. Bind any replacement grant to remaining
scope, not the original unspent limit. Pending/update/history records preserve
partial publication; retry the same command. `native-runtime revoke` is append-only
and never deletes jobs or refunds reservations. Read its scope before invoking it.
Rollback uses preserved exact predecessors and metadata, not a broad reset.

For executable_permissions, obtain a bounded repair plan and preserve content
hashes/metadata before an owner-approved repair; never run the whole server as root.
For lock/recovery rejection, preserve the files and identify the live owner's work.
For stale digests, confirm the actual files and propagate only intended changes.
For expired authority, ask the VM operator for the remaining explicit scope, keeping
ledger consumption. For quota/disk denial, inspect current consumption and physical
space; do not delete/refund/reset or disable floors. For extraction failure retain
raw job evidence, diagnose the common reader and qualify a correction on a new job.
For unsupported syntax stop at a concrete parser/compatibility limitation; do not
hash an unverified input as trusted. Keep private paths and raw reports out of Git.

The public package may contain bridge code, these fictional templates, the fixed
helpers and this guide. It must exclude VM images, Cadence/PDK binaries/models,
OA/ADE, proprietary netlists/raw results, journals, keys and licenses. Use your
existing Cadence/PDK entitlement; this bridge never changes license restrictions.
Publication still needs approval of the exact tested candidate commit and artifacts.
