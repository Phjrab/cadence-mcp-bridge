# WP-14 Fixed Names-Only Role Discovery Plan

Date: 2026-09-15

Plan: `WP14_FIXED_NAMES_ONLY_ROLE_DISCOVERY_PLAN`, version 1

Status: `PLAN_READY_FOR_REVIEW`

Normalized-LF SHA-256:
`2e44ca523c122744f6b16036785f285fc0f6a3d7b1b904326fe84ecc9165f12d`

## Scope and authority

This planning-only artifact defines a future fixed read-only discovery for opaque VDD, VCM, and
load candidates in exactly `MyDesignLib/Differential_Amplifier_TB2/schematic`. It is subordinate to
collector plan v1 SHA-256
`4588834378f38a65678880fd5c5a1a93fd85545b482a69a1f60a1ef96b5033fb`.
It contains no code or confirmation token and authorizes no implementation, deployment, execution,
Cadence invocation, simulation, MCP exposure, OA save, ADE-state change, or design/PDK mutation.

## Closed discovery contract

The planned operator command is `wp14-role-discovery`. It accepts no arguments and has no public
MCP route, raw shell route, or raw SKILL route. The target cellview, expected 35/14/8 structure, and
source fingerprint are compiled into reviewed code; every other target and fallback is denied.

Internally, only a closed analogLib master map may classify independent voltage/current sources,
resistors, and capacitors. Only fixed property slots may be classified for presence and type. No
property value is read. Unsupported masters, properties, or topology become blockers instead of
newly discovered schema.

The future implementation may enumerate bounded OA objects in memory, but its output contains no
actual instance, net, terminal, property, or master names. It reports only candidate counts,
allowlisted master-class enums, connection-role enums, property-slot-class enums, ambiguity status,
bounded blockers, and domain-separated selector commitment hashes bound to the exact source
fingerprint. A commitment is an opaque selector identity, not semantic proof.

## Candidate and ambiguity policy

The only candidate roles are `VDD`, `VCM`, and `load_condition`. Each role has at most 16 candidate
objects. Zero candidates produces `incomplete_evidence`; multiple candidates produce `ambiguous`;
unsupported candidates produce `blocked`. A single candidate is still not automatically accepted
as a role binding. No source value or scientific baseline is selected by discovery.

Connection output is limited to fixed enums such as reference-connected two-terminal,
global-supply candidate, common-mode-stimulus candidate, differential-input branch candidate, and
differential/single-ended output-load candidate. Actual connectivity names remain private.

## OA, fingerprint, and lock controls

The exact source opens only with OA mode `r` and closes without save. Source tree, source snapshot,
ADE-state tree, profile registry, and PDK-model fingerprints plus lock state are captured before and
after and must be identical. Expected topology is exactly 35 instances, 14 nets, and 8 terminals.

Active locks, stale or ownership-ambiguous locks, and panic/recovery artifacts cause `BLOCKED`.
Nothing is deleted, unlocked, renamed, repaired, retried, or redirected. Only bounded artifact
class, owner, timestamp, PID, and PID-running status may be reported.

## Bounds and sensitive output

Enumeration is limited to 256 instances, 256 nets, 256 terminals, 1,024 properties, and 16
candidates per role. Output is at most 16,384 bytes, each log at most 65,536 bytes, total runtime 60
seconds, OA open/close 30 seconds, and concurrency one with a nonblocking lock.

Actual OA names, property values, raw OA objects, netlists, ADE-state content, paths, PDK content,
waveforms, licenses, environment values, credentials, process commands, and unbounded logs/errors
are denied from stdout, stderr, logs, artifacts, and repository evidence.

## Acceptance and next gate

The normative JSON contains 20 acceptance criteria covering exact targeting, zero-input execution,
closed classification, no value reads, read-only OA lifecycle, fingerprint/lock invariants, bounded
opaque output, ambiguity preservation, injection and redaction tests, and independent future
approval gates.

After review, a later run may implement and locally test repository-side code only when explicitly
authorized against this plan's final hash. Deployment and one fixed invocation remain separately
prohibited until another explicit approval. Discovery success creates candidate evidence only; it
does not create a role binding or approve the scientific baseline.
