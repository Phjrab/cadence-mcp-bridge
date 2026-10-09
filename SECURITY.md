# Security reporting and verification

For sensitive findings, use the repository's GitHub private vulnerability report
when available. If that channel is unavailable, first open a minimal issue asking
for a private contact channel, without exploit details or private project data.
Do not assume a private reporting channel exists until GitHub confirms it.

Include affected package/source versions, a fictional reproduction, expected and
observed behavior, and a description of the trust boundary involved. Remove
credentials, license endpoints, proprietary circuits, PDK/model contents, raw
results, private paths and unrestricted logs before sending evidence.

The current generic operator route is unqualified and denies native execution.
Configuration or a locally matching grant form is not execution authorization.
Executable/dependency trust, physical resource identity, shared accounting and
operator confirmation must all pass before a future native path can be enabled.
No generic shell, SSH, SKILL or OCEAN evaluation interface is supported.

Public CI uses disposable GitHub-hosted Windows runners, read-only token permission,
pinned reviewed actions, a fixed uv binary checksum and locked dependencies. It
runs no Cadence/PDK/laboratory VM calls and uploads no artifacts or private evidence.
Fork PR code is never automatically run on a self-hosted licensed system. Workflow
changes need the same security review as source changes; administrator settings
and branch protection are not changed by the workflow.

Detailed historical boundaries and local security checks are in docs/SECURITY.md.
Operator preservation and unsupported migration/deletion capabilities are recorded
in docs/generic_release/OPERATIONAL_PRESERVATION.md.
