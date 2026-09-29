# AUTO-PHASE-01 active operating policy

Effective 2026-09-29 for the user's explicit instruction in this task. The attached
transition document is a scope specification; its presence in a checkout is not
itself authority. This policy applies only to `Phjrab/cadence-mcp-bridge`, the
registered `cadence-vm` target, and owned work under
`/home/buet/cds_work/.cadence_mcp`. It replaces project-level repeated approval
for in-scope work, not external access controls or verification criteria.

## Sequence and decisions

After a small phase, verify code and exact diff, create a feature PR, satisfy actual
GitHub checks/review, merge through the PR, and verify main. Report the phase and
continue the next ready task. Never use a state-sync-only PR. Do not redo merged
PR #57 or completed WP-15/WP-16. If GitHub access, a required reviewer, the VM,
an actual capability, or a safety precondition is unavailable, record the precise
blocker and a resume checkpoint. `NOT_RUN` is distinct from PASS.

The project source, schemas, tests and owned deployment may be changed within the
user's scope. No main push, force push, protection bypass, other repository,
release/tag, payment, chip order, final submission, original/PDK/destructive
operation, protected material publication, or arbitrary runtime shell/SKILL/OCEAN
tool is authorized. A runtime design agent may not edit this policy or its budget.

## Candidate and evidence semantics

`VBIASN=0.320 V` and `VBIASP=0.702 V` are user candidates. `VDD=1.0 V` is a hard
constraint. Current VCM, load, source/ADE revision, hashes, current settings,
effective application, DC result and specification result require separate
evidence. Past 300/650 and 370/650 mV records remain historical. A fresh work
revision may resolve missing historical equivalence without rewriting old evidence.
Keep private circuit, PDK, PSF, ledger and identity details in private local
artifacts; commit only reviewed non-sensitive status and opaque references.

## Current runtime implementation

`scripts/phase_campaign.py` is a new operator-only, fixed-command path for two
read-only operations: identity/version and the existing fixed ADE profile
inspection. It requires a private `.codex/phase-campaign-delegation.json` bound
to the exact versioned policy digest. The record is created only in this user
delegated session; a checkout or policy file without it is denied. A durable
local journal reserves each operation before transport and blocks uncertain or
duplicate outcomes. The read-only transport uses the registered SSH alias,
host-key checking, a 60-second timeout, capped output and up to two communication
retries. Raw output stays in local private state. Legacy single-use collectors,
claims, expiries and `deployment_enabled=false` are unchanged and remain gated
by their original authorizations. The new policy does not secretly make them
active. New deployment, copy mutation and DC operations need separate typed
implementations and verification before use; their absence is `capability_missing`,
not a request for the same user approval again.

The WP-14 role discovery extension is separately bound by
`docs/policy/PHASE_B_ROLE_V1.json` and `scripts/phase_b_role_campaign.py`.
It inherits the original eight-hour clock and preserves the earlier uncertain ADE
inspection record. Its two one-shot operations deploy three exact files to a new
managed version directory and run a names-only, read-only OA role probe. It cannot
apply a bias, run Spectre, or establish numeric VDD/VCM/load values. Those
capabilities require distinct reviewed typed operations.
If the deploy response is uncertain after staging, `recover-deploy` verifies the
reserved operation and exact campaign-owned staged bytes before completing that
same operation. It does not reset the journal or create another deploy allowance.

This is an operational guard, not cryptographic isolation from the same OS account:
that account can edit code, delegation and state. External sandbox, SSH and GitHub
rules remain independent boundaries.

## Campaign ceilings

One active EDA job; eight elapsed campaign hours; 100 Spectre attempts, 20 DRC,
20 LVS, 10 PEX; three modifications of the same code change; two communication
retries per fixed read; 5 GiB new results; managed disk free space at least the
greater of 2 GiB and ten percent. Paid resources: zero. Usage accumulates across
phases and resumes. The current operator implementation enforces its eight-hour
read campaign and per-operation retries; no simulation or deployment API is
available in that implementation. Later typed implementations must enforce the
corresponding cumulative ceilings before activation.
