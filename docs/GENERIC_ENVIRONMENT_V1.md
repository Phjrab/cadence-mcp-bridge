# Operator environment contract v1

## What this enables

Describe and inspect an approved environment without changing source-code host
constants. This is an operator workflow outside the MCP server. It does not
register a design, change `BridgeConfig`, route existing tools to a new host,
grant simulation authority or create/reset a budget ledger.

Version 1 supports a Windows Python 3.12/3.13 client with Windows OpenSSH and a
Linux Cadence host with `/usr/bin/python` 2.6/2.7/3.x. Host architecture, runtime,
hostname and account must match the explicit profile. Other transports/host
OSes are unqualified. OCEAN presence/hash is checked; its version is not probed.

## Local workflow

```powershell
uv sync --all-groups
uv run cadence-mcp-bridge doctor
uv run cadence-mcp-bridge environment schema
uv run cadence-mcp-bridge environment validate --profile C:\private\environment.json
uv run cadence-mcp-bridge environment prepare --profile C:\private\environment.json --output C:\private\new-bundle
```

The [example profile](examples/environment-v1.fictional.json) is fictional and
non-executable: replace it with approved local facts in private operator storage.
Never copy a profile containing real identities, paths, hashes or budgets into
the public repository. The [JSON Schema](schemas/environment-v1.schema.json)
describes structure; `environment validate` also enforces cross-field path,
protection, executable and capability rules. Schema validation alone is insufficient.

`doctor` makes no remote call and reports only local runtime/OpenSSH/config
readiness. `validate` emits `valid_description`, never environment qualification.
`prepare` exclusively creates a new local bundle with `probe.py` and
`profile.json`, returning their byte hashes. It never deploys or overwrites.
Run preparation as the intended operator: private permissions can make a bundle
created by another OS account unreadable. Windows ACLs and Linux private modes
are platform controls; do not widen them to all users to transfer a bundle.

## Reviewed deployment prerequisite

An operator with separate deployment authority must provision existing workspace,
managed, job, result and protected roots and install exactly the prepared bytes at:

```text
<workspace_root>/.cadence_mcp/environments/<environment_id>/v1/probe.py
<workspace_root>/.cadence_mcp/environments/<environment_id>/v1/profile.json
```

Use private directories (0700), regular profile/probe files (0600), the intended
remote account and no symlink components. Verify hashes against `prepare`, and
compile the probe with the registered system Python without generating bytecode.
Use a fresh, approved version location and preserve any previous bundle/evidence;
this CLI supplies no arbitrary deployment or overwrite command. A site must
review byte changes before replacing an existing version. The filename/location,
private profile and probe digest are checked again during qualification.

The profile must specify canonical ASCII absolute paths with no traversal,
newline or shell characters. The managed root is exactly
`workspace_root + '/.cadence_mcp'`; job/result roots are descendants. Protected
roots must exist and be disjoint from managed writes. Qualifying roots checks
containment and `os.access` without writing test files; it is not a guarantee
that a future job succeeds or a content fingerprint of every protected object.

Only paths named `virtuoso`, `spectre`, `ocean` under protected roots are accepted.
Resolved executable bytes are hash-bound; executable files and their ancestors
must not be group/other writable. Symlinks can resolve only within protected
roots, and binding/inode/mode/content are rechecked after version observation.
This checks the selected wrappers, not every installation dependency. The
trusted account, SSH configuration, host OS and Cadence installation remain
operator trust boundaries. It is not isolation from that same OS account.

## Remote qualification

```powershell
uv run cadence-mcp-bridge environment qualify --profile C:\private\environment.json
```

Transport uses batch mode, strict host keys, a 10-second connection timeout,
45-second total bound, no retry and bounded stdout/stderr. The fixed operation
is `/usr/bin/python -B` on the profile-derived bundled probe location with the
two expected hashes and a fresh nonce. No caller command, Python body, SKILL,
OCEAN, raw netlist or result path is accepted. Profile documents are capped at
32 KiB. Virtuoso/Spectre receive only `-W`, each with an 8-second/4-KiB bound and
a dedicated process group. Version text is token-matched then discarded.

A successful report has `status=qualified_environment_preflight`, with scope
`identity_runtime_binary_roots_disk` and `execution_authorized=false`.
Observations are bound to environment/profile/probe/nonce and accepted within
60 seconds (at most 5 seconds of future clock skew). Disk free space must meet
the declared floor, at least the greater of 2 GiB and 10 percent. Declared
Spectre/storage limits and concurrency-one/paid-zero constants are descriptions;
existing runtime ledgers retain their own independent enforcement.

Only license-variable presence is observed. `configured_entitlement_unqualified`
does not prove a license checkout; values and raw banners are never returned.
DC/AC/TRAN/ADE/PSF capability requests remain `unqualified`. Separate registered
design/analysis evidence is necessary for supported execution.

Failures produce `status=blocked`, `execution_authorized=false` and either a
closed rejection code (for example `executable_permissions` or `disk_floor`) or
a generic contract/probe failure. Private exception messages are suppressed.
Fix the underlying approved environment rather than treating rejection as PASS.
The reference installation currently fails the new executable permission check;
this phase does not chmod its protected Cadence installation. Existing tools
continue to use their original policy and routes.
