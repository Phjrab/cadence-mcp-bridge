# Operator native storage integration

Status: implementation checkpoint, final standalone integration, review, hosted
checks and exact installed/VM qualification pending. General release is BLOCKED.
This document is a technical record, not additional approval or a frozen candidate.

The selected operator context now connects the existing five path-free storage
MCP tools to its immutable native provider, environment profile and accounting
identity. It does not inherit the reference developer address, account or managed
root. The public input/output declarations remain unchanged. No caller path,
shell, administrator command, retention registration or consent writer is added.

Requests use fixed storage_inventory/storage_cleanup actions on the registered
provider. Closed canonical envelopes bind the exact runtime SHA, resource anchor
and action. A changed host grant/provider binding requires review and restart;
transport loss is never automatically retried. Cleanup replies must preserve the
operation ID, selected IDs and plan ID, and a dry-run cannot claim deletion.
Independent exact selected-item operator consent remains mandatory remotely.

The native dispatcher verifies the complete immutable bundle before importing
storage, and rechecks bundle, active pointer and activation history at the locked
worker boundary. The root comes only from the validated profile. Busy inventory
must remain conservative/read-only; lock contention cannot authorize cleanup.
The worker factor and generic protected job-group coverage are still pending
PR151 integration at this checkpoint. Historical deployed providers that lack the
new actions reject; their prior results do not qualify the updated dispatch.

Local configured public MCP/transport/runtime tests:84 PASS,1 Windows symlink
skip; full mypy95 PASS and touched Ruff PASS. These use a synthetic wire and do
not claim remote storage or Cadence validation. No VM cleanup, chmod/chown,
simulation, reservation, ledger reset or refund occurred. The earlier actual
Codex reconnect/same-ID result remains evidence for40c/bf6 only. Final current-code
read-only storage inventory, source/model/content protection and package checks
remain required before candidate acceptance.
