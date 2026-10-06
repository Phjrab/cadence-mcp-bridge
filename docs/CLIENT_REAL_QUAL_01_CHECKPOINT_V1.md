# CLIENT-REAL-QUAL-01: actual application qualification checkpoint

Later [actual Codex read evidence](CLIENT_REAL_QUAL_CODEX_READS_V1.md) supersedes
this dated missing-bridge observation for Codex. Claude and full application
qualification remain pending; the checkpoint below is preserved history.

Date: 2026-10-06. Starting main:
`3432d580994bd825e5d650dd284d110342ac01e3` (merged #120).
Branch: `feat/client-real-qual-01`. **Phase status: BLOCKED, not complete.**
Checkpoint integration: [PR #121](https://github.com/Phjrab/cadence-mcp-bridge/pull/121),
with exact resulting remote SHA/tree recorded privately after permitted merge.
This checkpoint adds a concrete application handoff and evidence rubric; it does
not repeat completed CLIENT-COMPAT-01 or release readiness work.

## Fresh availability observations

| Observation | Result / precise limit |
| --- | --- |
| Windows Computer Use helper | Import and app inventory succeed; native helper is available |
| Running Codex package identity | `OpenAI.Codex_2p2nqsd0c76g0!App`, displayed as ChatGPT |
| Current global Codex config | Exists; parsed bridge entry absent; no config values disclosed or edited |
| Active agent tool catalog | No Cadence bridge tools; not a successful application initialization |
| Claude in returned app inventory | No matching app; this is not proof of every installation format being absent |
| Standard Claude configuration | Absent; queried uninstall entries and Windows PowerShell Appx queries return no matching Claude entry |
| PowerShell Core Appx query | Unsupported module; bounded Windows PowerShell query used instead, not silently reported as a successful Core query |
| Actual application version / bridge inventory / calls | NOT_TESTED; package identity and config presence do not prove these |

The earlier statement that native controls were unavailable is superseded for
this checkpoint: the helper is callable. However, the applicable Computer Use
skill (`docs/guidance.md`, Non-negotiable Windows Automation Safety) prohibits
automation of the **ChatGPT desktop app UI**, which is the returned Codex surface.
No alternative UI automation or hidden app protocol is used to evade that rule.
No targetable Claude app was returned. These are genuine application-access
blockers, not server implementation failures.

Current matrix remains:

| Client | Registration through app | Actual tools/list | Actual tools/call | Actual Cadence result through app |
| --- | --- | --- | --- | --- |
| Codex / ChatGPT desktop surface | NOT_TESTED; bridge global entry absent | NOT_TESTED | NOT_TESTED | NOT_TESTED |
| Claude Desktop | CONFIG_PREPARED only | NOT_TESTED | NOT_TESTED | CLAUDE_REAL_CLIENT_UNVERIFIED |

SDK configuration/protocol evidence from #119/#120 remains valid and separate.
The phase cannot be declared complete until direct application evidence exists.

## Human application handoff

Use the same reviewed bridge package/runtime and the existing operator-owned
environment/design/PDK profiles. Keep the original analysis admission journal and
historical sweep journal: **do not install a configuration pointing at an immutable
SDK replay fixture**, create a replacement ledger, or move/reset an old ledger.
The prior private exported SDK configs are evidence, not live app installation files.

1. Run the existing doctor/joined verify and `scripts/verify-release-readiness.py`
   from the reviewed checkout. Use the existing
   [client-config export workflow](ONBOARDING_CLI_V1.md) to create **new** private
   Codex TOML and Claude JSON fragments with the actual historical journals.
   Export does not install them or qualify a physical route.
2. Record the fragment/profile/registry digests privately. Review only the bridge
   entry; keep all other servers, client approval settings and protected data.
   Register that entry through the supported client settings/configuration.
   No credentials/license values, source/PDK data or raw results belong in client
   registration or a public report.
3. In the current Codex/ChatGPT desktop app, use **Settings → MCP servers** and
   its **Restart** control after registration. The agent cannot perform this UI
   step under the current skill. The official guide says `/mcp` in the composer
   shows connected servers. Record the actual app version and server state.
4. For Claude, make an authorized Desktop installation available and register the
   same server using the existing documented JSON mechanism. Quit/restart as
   required by that app. Do not configure a web client or Claude CLI and label it
   Desktop. No automatic installation or authentication is performed here.
5. Run the read-only prompts below in each application. Preserve direct tool cards
   and bounded structured outputs privately, identifying the application and time.
   Then return to this task with the observed outcomes; the agent can compare
   evidence without receiving raw private logs or sensitive configuration.

Current official Codex documentation was actually fetched on 2026-10-06:
[MCP registration](https://learn.chatgpt.com/docs/extend/mcp?surface=app).
It describes shared host `config.toml`, Settings/MCP servers/Restart and `/mcp`.
Use [Claude documentation and existing procedure](CLIENT_COMPATIBILITY_V1.md)
for its distinct registration mechanism. No HTTP listener/tunnel/remote MCP.

## Exact read-only application prompts

Paste this into each application's existing authorized test conversation:

```text
Use only Cadence MCP Bridge read-only tools for this check.
Call cadence_list_designs. Choose an ID returned by that tool, then call
cadence_describe_design and cadence_design_pdk_status for that same ID.
Report the exact called tool names and bounded structured results.
Do not submit/cancel jobs, run simulations, create targets, change a design,
perform cleanup, run shell commands, or request private paths/PDK/model data.
If the bridge/tools are unavailable, report unavailable; do not substitute
a shell or a separately launched SDK client for the application tool calls.
```

An application paraphrase is not enough: record the direct call/result cards.
Expected inventory is **69 full schemas** from
[the reviewed snapshot](contracts/MCP_RELEASE_READINESS_V2_SNAPSHOT.json).
If the app provides an actual tools/list diagnostic/export, retain it privately
and compare names, input/output schemas and annotations. A visible server badge,
model assertion or count alone does not prove full-schema equality. If that
evidence is unavailable, record names/count as observed and keep full-schema
qualification NOT_TESTED instead of fabricating it.

For an optional real Cadence **read**, first select an already admitted completed
native operation from existing private evidence and verify it belongs to the
unchanged configured journal. Request only its bounded status/result using the
existing typed tool. Do not generate a UUID, resubmit, reserve results or simulate
to prove client compatibility. Missing safe admitted identity means NOT_TESTED.

## Private evidence rubric

Record each item independently for **each named actual app**:

- Actual application name/version, observation time and reviewed bridge SHA/version.
- Registration observed after app-owned restart; config/profile/journal digests
  retained privately, without exposing paths or secret values.
- Actual initialization/version negotiation and capabilities, if app diagnostics
  expose them; otherwise NOT_TESTED, never inferred from a successful SDK probe.
- Actual tools/list export and comparison scope (complete schemas, names only,
  or unavailable). Use the 69-tool snapshot, not earlier 48/53/66 inventories.
- Direct read-only call cards and structured results from the prompts above.
- Same configured IDs/results across clients. An actual native read remains
  separate from local design discovery; absent read is NOT_TESTED.
- Stderr/protocol and normal app-owned process shutdown/restart observations,
  where directly exposed; don't kill workers or claim unseen lifecycle behavior.
- No new simulation/reservation/deletion; fixed protected/accounting checks where
  a reference read was actually performed under existing authority.

VERIFIED applies only to directly observed app operations. A screenshot proves
what it shows; it does not by itself prove full protocol/lifecycle/schema coverage.
Raw app logs/transcripts may contain private material: retain locally and return
only reviewed bounded facts. Do not upload a whole log/config bundle to this chat
or commit it to GitHub.

## Checkpoint gates and protection

This change is documentation only: MCP **69 → 69**, all runtime/remote source,
profiles, schemas, package/version/license metadata and budgets unchanged.
The exact #120 static/full-unit/security/package evidence remains applicable to
the unchanged code; this checkpoint reruns local contract and secret/diff checks.
No actual client E2E PASS is added. No remote contact, simulation, reservation,
deployment, deletion, global client config write, release/tag or optimization.
Prior **1,091 private records** are baselined and checked for unchanged bytes.
Cumulative reference counters remain the last observed **62/500** and
**7,114,588,160 / 10,737,418,240 reserved bytes**; no fresh guest observation is
claimed by this documentation-only checkpoint.

Integrate this handoff/checkpoint through its own reviewed feature PR. Resume
CLIENT-REAL-QUAL-01 after direct application access/evidence is available; do not
activate another development phase or public release. Imported planning rights
remain independently LEGAL_REVIEW_REQUIRED.
