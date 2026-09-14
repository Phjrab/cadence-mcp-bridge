# 자율 Custom IC 설계 에이전트를 위한 Cadence MCP 전체 로드맵

> **North Star:** 사용자가 회로 사양과 대상 PDK를 제공하면, 에이전트가 제한된 typed MCP 도구만 사용하여
> 사양 정리 → topology 선정 → schematic/testbench 생성 → DC/AC/TRAN/Noise/STB → sweep/PVT/Monte Carlo → sizing 최적화 → layout 생성 → DRC/LVS/ERC → PEX/RCX → post-layout 검증 → pad/top integration → tapeout-ready package → 실리콘 측정 비교까지 수행한다.

---

## 문서 정보

| 항목 | 값 |
|---|---|
| 대상 프로젝트 | `Phjrab/cadence-mcp-bridge` |
| 작성 기준 | 2026-08-31 `main` / `v1.0.0` 이후 확장 |
| 현재 개발 PDK | `gpdk090 v4.6` |
| 향후 제작 대상 | 사용자에게 공식 배포된 MyChip target PDK |
| 호스트 | Windows 11 + Codex Desktop |
| 원격 EDA 환경 | VMware CentOS 6.5 i686 |
| Cadence | Virtuoso IC6.1.5.500.15 |
| Simulator | Spectre 12.1.0.347.isr3 |
| 자동화 인터페이스 | MCP SDK v2, Windows OpenSSH, Bash, Python 2.6 helper, SKILL/OCEAN, Spectre |
| 최종 산출물 | 재현 가능한 설계 revision, 검증 evidence, tapeout-ready GDS/package, silicon correlation report |

### 이 문서의 범위

이 문서는 단순 기능 목록이 아니라 다음을 모두 포함한다.

- 현재 프로젝트 구현 수준과 한계
- 최종 자율 설계 플랫폼의 목표 아키텍처
- 보안·승인·증거 보존 원칙
- GPDK090에서 기능을 검증한 뒤 MyChip PDK로 재타깃팅하는 전략
- schematic, simulation, optimization, layout, DRC/LVS/PEX, tapeout, 실리콘 측정까지의 단계별 목표
- 각 단계에서 필요한 MCP tool, 데이터 계약, 테스트, 수락 기준, 산출물
- phase별 Codex 실행 프롬프트 작성 규칙
- 최종 “완전 자율” 정의와 사람의 최종 승인 지점

---

# 1. 현재 프로젝트 기준선

## 1.1 이미 구현된 기반

현재 `v1.0.0`은 다음 기반을 제공한다.

- Windows Python 3.12 기반 MCP SDK v2 stdio server
- `cadence-vm` 고정 SSH alias를 통한 CentOS runner
- arbitrary shell/SSH/SKILL/OCEAN을 노출하지 않는 closed tool surface
- Spectre smoke simulation
- asynchronous job lifecycle
  - submit
  - status
  - bounded log
  - result
  - cancel
- metadata-only library/cell/view discovery
- fixed simulation profile registry
- `Differential_Amplifier_TB2`의 fixed transient baseline 실행
- synthetic ADC measurement contract
- audit, timeout, process-group cancellation, sanitization
- copy-only design-write validation
- V4 clean write-validation 및 rollback evidence
- package build/install/uninstall 검증
- `v1.0.0` tag와 GitHub release

## 1.2 현재 actual Cadence profile

현재 actual profile은 다음 정보를 고정한다.

```yaml
profile_id: actual-differential-amplifier-tb2-transient
library: MyDesignLib
cell: Differential_Amplifier_TB2
view: schematic
ade_product: ADE L
ade_state: state1
pdk: gpdk090
pdk_version: "4.6"
model_section: NN
temperature_c: 27
analysis: tran
stop_time: 4m
variables: {}
outputs: []
```

현재 실행은 ADE L state를 runtime에서 열고 netlist하는 방식이 아니다.

```text
ADE에서 과거 생성된 고정 source netlist
                ↓ bounded copy
job-local reviewed Spectre wrapper
                ↓
Spectre CLI
```

따라서 현재 가능한 것은 **고정 snapshot 재실행**이며, 다음은 아직 구현되지 않았다.

- ADE state 직접 load
- 최신 schematic에서 headless netlisting
- design variable override
- DC/AC/Noise/STB profile
- actual waveform/measurement extraction
- 1D/2D sweep
- corner campaign
- Monte Carlo campaign
- schematic 생성·편집
- layout 생성
- DRC/LVS/PEX
- tapeout package

## 1.3 즉시 처리해야 할 P0 위험

### 저장소 visibility

초기 요구는 private repository였으나 검토 시점의 GitHub metadata는 public이었다. PDK, proprietary design, netlist, PSF, rule deck, MyChip 자료를 저장하기 전 반드시 visibility와 접근 정책을 다시 확인한다.

### Baseline 불일치

현재 repository actual profile은 다음을 고정한다.

```text
VBIASN = 300m
VBIASP = 650m
```

사용자의 과거 검증 결론은 다음이었다.

```text
VBIASN = 370m
VBIASP = 650m
```

모든 sweep, optimization, porting 전에 authoritative baseline을 한 번 결정하고 versioned contract로 고정해야 한다.

### 실제 PDK 데이터

MyChip PDK의 기술명, 공정 옵션, device/PCell 이름, corner, rule deck, pad library, stream map, submission rule은 **사용자에게 공식 제공된 PDK 문서와 파일만 source of truth로 사용**한다. 공개 인터넷 정보나 모델의 기억으로 hardcode하지 않는다.

---

# 2. 최종 자율 설계의 정의

## 2.1 자율성 레벨

| 레벨 | 이름 | 에이전트 기능 | 사람 역할 |
|---:|---|---|---|
| L0 | Read-only Observer | 설계/환경 조회 | 해석 및 조작 모두 사람 |
| L1 | Execution Assistant | 고정 simulation/verification 실행 | 설정과 판단은 사람 |
| L2 | Experiment Agent | bounded sweep, corner, measurement | 변수·범위 승인 |
| L3 | Schematic Author | work revision에 schematic/testbench 생성 | topology/변경 승인 |
| L4 | Circuit Optimizer | spec 기반 sizing·bias·topology 탐색 | objective와 budget 승인 |
| L5 | Layout Author | placement/routing/layout intent 적용 | layout plan 승인 |
| L6 | Verification Agent | DRC/LVS/ERC/PEX와 bounded 수정 반복 | 큰 변경 승인 |
| L7 | Tapeout-Ready Agent | pad/top/GDS/preflight/evidence 생성 | 최종 제출 승인 |
| L8 | Silicon Feedback Agent | 계측·sim-to-silicon 분석·재설계 | 실험 안전·장비 승인 |

이 프로젝트의 장기 목표는 **L7을 재현 가능하게 달성하고 L8까지 확장**하는 것이다.

## 2.2 완전 자율이라고 부르기 위한 최소 조건

다음 chain이 하나의 immutable design campaign으로 연결되어야 한다.

```text
Specification
  → Topology
  → Initial sizing
  → Schematic
  → Testbench
  → DC operating point
  → AC/Noise/STB/TRAN
  → Sweep/Optimization
  → PVT/Monte Carlo
  → Schematic freeze
  → Layout intent
  → Placement/Routing
  → DRC clean
  → LVS clean
  → PEX/RCX
  → Post-layout spec pass
  → Pad/Top integration
  → Final signoff
  → GDS/package
  → Human tapeout approval
```

완전 자율은 “모델이 마음대로 Cadence 명령을 실행한다”는 뜻이 아니다.

> **에이전트는 설계 결정을 내리고, MCP 서버는 허용 범위·예산·데이터 무결성을 강제한다.**

---

# 3. 핵심 설계 원칙

## 3.1 Typed semantic tools

허용:

```text
create_schematic_revision(...)
add_mos_instance(...)
connect_net(...)
set_device_parameter(...)
submit_ac_profile(...)
plan_parameter_sweep(...)
place_matched_pair(...)
submit_drc(...)
```

금지:

```text
run_shell(command)
ssh(command)
eval_skill(code)
execute_ocean(script)
read_any_file(path)
write_any_file(path)
```

## 3.2 모든 write는 revision/workspace에서 수행

```text
Authoritative source
       │ read-only
       ▼
Design Workspace / Revision
       │ controlled write
       ▼
Validated candidate
       │ explicit promotion
       ▼
Frozen release revision
```

원본, PDK, shared library, rule deck은 에이전트가 직접 수정하지 않는다.

## 3.3 계획과 실행 분리

모든 위험한 작업은 최소 두 단계로 나눈다.

```text
plan
  → canonical JSON
  → SHA-256
  → user/policy approval
  → execute exact plan
```

## 3.4 Fail-closed

다음 조건에서는 자동 보정하지 않고 중단한다.

- baseline drift
- unknown property
- unexpected OA metadata change
- lock/recovery artifact
- tool/version mismatch
- PDK hash mismatch
- output ambiguity
- DRC/LVS parser ambiguity
- point/run budget 초과
- evidence/audit 기록 실패

## 3.5 Evidence first

각 design revision과 job은 다음을 가져야 한다.

- immutable manifest
- exact tool/profile/PDK version
- input hash
- source/revision fingerprint
- result summary
- artifact metadata
- audit sequence
- approval reference
- before/after diff
- rollback evidence
- parent revision

## 3.6 사람의 최종 승인 지점

다음 작업은 자동 수행하지 않는다.

- repository visibility 또는 권한 변경
- PDK 라이선스 동의
- foundry/MPW portal 제출
- 최종 GDS 제출
- 비용 발생 주문
- 실험실 고전압/고전류/장비 위험 동작
- 원본 tapeout revision 삭제
- signoff waiver 승인

---

# 4. 목표 시스템 아키텍처

```text
┌─────────────────────────────────────────────────────────────┐
│ User Specification / Approval                              │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Agent Orchestrator                                         │
│ - Planner                                                  │
│ - Circuit Architect                                        │
│ - Verification Agent                                       │
│ - Optimization Agent                                       │
│ - Layout Planner                                           │
│ - Physical Verification Agent                              │
│ - Signoff Agent                                             │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Policy and Contract Layer                                  │
│ - project/workspace/revision policy                        │
│ - PDK technology adapter                                   │
│ - variable/output/analysis allowlist                       │
│ - budget/approval/confirmation                             │
│ - data redaction                                           │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Typed MCP Tool Surface                                     │
│ Project | Schematic | Simulation | Sweep | Layout           │
│ DRC/LVS/ERC | PEX | Tapeout | Measurement                  │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ CadenceService / Campaign Engine                            │
│ - state machine                                             │
│ - revision DAG                                              │
│ - parent/child jobs                                         │
│ - retry policy                                              │
│ - evidence and audit                                        │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Windows OpenSSH Backend                                    │
│ fixed alias, argv, shell=False, strict host key             │
└──────────────────────┬──────────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ CentOS Fixed Runner                                        │
│ Bash + Python 2.6 helper + fixed SKILL/OCEAN templates      │
└──────────────┬──────────────────┬───────────────────────────┘
               ▼                  ▼
       Virtuoso / OA          Spectre / ADE/OCEAN
               │                  │
               └─────────┬────────┘
                         ▼
               Assura/PVS/Calibre adapter
                         ▼
                  PEX / Extracted view
                         ▼
               GDS/Submission/Measurement
```

---

# 5. 공통 데이터 모델

## 5.1 Design specification

```yaml
spec_id: diffamp-gpdk090-v1
technology_id: gpdk090-v4.6
supply:
  vdd_v: 1.0
environment:
  temperature_c: 27
functional:
  input_type: differential
  output_type: differential
performance:
  dc_gain_db:
    minimum: 60
  phase_margin_deg:
    minimum: 60
  power_mw:
    maximum: 1.0
  bandwidth_hz:
    minimum: 100e6
constraints:
  allowed_topologies:
    - simple_diff_pair
    - telescopic_cascode
    - folded_cascode
  maximum_simulation_runs: 200
  maximum_layout_iterations: 8
```

## 5.2 Design revision manifest

```yaml
revision_id: rev-00042
parent_revision_id: rev-00041
project_id: diffamp-agent-demo
technology_id: gpdk090-v4.6
source:
  library: AgentWorkLib
  cell: diffamp_rev_00042
  schematic_view: schematic
  layout_view: layout
intent_hash: sha256:...
schematic_fingerprint: sha256:...
layout_fingerprint: sha256:...
simulation_campaigns:
  - campaign_id: camp-dc-001
verification:
  drc: pass
  lvs: pass
  pex: pass
approval_refs:
  - approval:topology-003
created_by: circuit-optimizer
created_at: 2026-08-31T...
```

## 5.3 Technology adapter

```yaml
technology_id: mychip-target-v1
source_of_truth:
  pdk_manifest_sha256: ...
  documentation_revision: ...
libraries:
  device_library: ...
  io_library: ...
devices:
  nmos:
    cell: ...
    parameters:
      width: w
      length: l
  pmos:
    cell: ...
layers:
  metal1:
    purpose: drawing
vias:
  via1:
    from: metal1
    to: metal2
models:
  simulator: spectre
  nominal_section: ...
  corners: [...]
verification:
  drc:
    backend: ...
    fixed_deck_id: ...
  lvs:
    backend: ...
  pex:
    backend: ...
stream_out:
  map_id: ...
  top_cell_rule: ...
```

## 5.4 Sweep plan

```yaml
sweep_id: swp-...
profile_id: actual-diffamp-dcop-v2
revision_id: rev-...
axes:
  - name: VBIASN
    unit: V
    values: [0.34, 0.35, 0.36, 0.37, 0.38, 0.39, 0.40]
corner: NN
measurements:
  - tail_current
  - minimum_saturation_margin
budget:
  maximum_points: 21
  maximum_parallelism: 1
  automatic_retry: 0
plan_sha256: ...
```

## 5.5 Layout intent

```yaml
intent_id: li-...
revision_id: rev-...
groups:
  - id: input_pair
    kind: differential_pair
    devices: [M1, M2]
    matching: strict
    symmetry_axis: vertical
    orientation: same
    common_centroid: false
    dummies: both_sides
  - id: active_load
    kind: current_mirror
    devices: [M3, M4]
    matching: strict
routing:
  differential_nets:
    - [VINP, VINN]
    - [VOUTP, VOUTN]
  equal_length_tolerance_um: ...
guard_rings:
  - group: input_pair
power:
  preferred_metals: [...]
```

## 5.6 Verification violation

```yaml
violation_id: drc-000123
backend: assura
rule_id: M1_SPACING
severity: error
required_value_um: ...
observed_value_um: ...
bbox_um: [x1, y1, x2, y2]
object_refs:
  - shape:...
fix_class:
  - move_shape
  - reroute_segment
confidence: 0.92
raw_text_exposed: false
```

## 5.7 Tapeout manifest

```yaml
tapeout_id: to-...
technology_id: mychip-target-v1
top_cell: CHIP_TOP
frozen_revision: rev-...
signoff:
  drc: pass
  lvs: pass
  erc: pass
  pex: pass
  post_layout_spec: pass
stream_out:
  format: GDSII
  sha256: ...
padframe:
  verified: true
submission:
  portal_upload_performed: false
  human_final_approval_required: true
```

---

# 6. 승인 등급

| 등급 | 예시 | 기본 정책 |
|---|---|---|
| R0 | metadata 조회 | 자동 가능 |
| R1 | simulation 결과 조회 | 자동 가능 |
| C1 | 단일 simulation | profile budget 내 자동 가능 |
| C2 | small sweep | 승인된 budget 내 자동 가능 |
| C3 | large sweep/Monte Carlo | plan hash 승인 |
| W1 | work revision parameter 변경 | exact diff/rollback 필요 |
| W2 | schematic/layout 생성 | plan 승인 필요 |
| W3 | DRC auto-fix/LVS fix | iteration budget와 mutation cap 필요 |
| S1 | release revision freeze | 사용자 승인 |
| S2 | GDS stream-out | 사용자 승인 |
| S3 | MPW 제출/주문 | 반드시 사람 최종 승인 |

---

# 7. 버전 및 단계 로드맵

| 목표 버전 | 핵심 마일스톤 |
|---|---|
| v1.0.1 | 보안·문서·baseline 정리 |
| v1.1 | ADE/parameter/result extraction/1D sweep |
| v1.2 | full ADE state execution/DC/AC/TRAN/corner |
| v1.3 | schematic authoring과 revision system |
| v1.4 | circuit synthesis와 sizing optimization |
| v1.5 | layout DB foundation |
| v1.6 | analog layout intelligence |
| v1.7 | DRC/LVS/ERC 자동화 |
| v1.8 | PEX/post-layout closure |
| v1.9 | PDK abstraction과 MyChip migration |
| v2.0 | spec-to-tapeout autonomous campaign |
| v2.1 | silicon measurement feedback |
| v2.2+ | multi-project/multi-PDK/team platform |

---

# P0. 기준선·보안·거버넌스 정리 — 목표 버전 v1.0.1

## Phase 목표

v1.0.0 이후 확장 전에 repository, baseline, evidence, profile drift를 정리한다.

## 설계 방향

이 phase는 기능 추가보다 중요하다. baseline이 흔들리면 이후 sweep과 optimization이 잘못된 회로를 기준으로 진행된다.

필수 결정:

- repository를 private로 유지할지
- `VBIASN=300m`과 `370m` 중 authoritative baseline
- actual profile의 source netlist freshness
- `state1`과 netlist의 관계
- future branch/release 규칙
- MyChip PDK 자료의 저장 위치와 접근 권한

이 phase가 끝나기 전에는 actual variable profile과 sweep를 활성화하지 않는다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P0-01` | Repository visibility 및 access audit | 실제 GitHub visibility, collaborators, branch protection, secret exposure를 확인한다. | visibility가 의도와 일치하고 PDK/proprietary data가 공개되지 않음 | security audit report |
| `P0-02` | 문서·release truth reconciliation | README, PROJECT_STATE, RELEASE, GitHub release body를 실제 상태와 일치시킨다. | 상태 문서 간 모순 0건 | state reconciliation report |
| `P0-03` | Actual baseline audit | state1, source netlist, profile fixed parameters와 과거 검증값을 비교한다. | 사용자 승인 baseline contract 1개 | baseline contract |
| `P0-04` | Golden fingerprint registry | source/state/PDK/profile/runner의 immutable hash 기준을 만든다. | golden hash set 생성 및 재검증 성공 | golden-fingerprints.json |
| `P0-05` | Evidence schema v2 | manifest/audit/approval/rollback/provenance 공통 schema를 정의한다. | 모든 신규 campaign에서 재사용 가능한 schema | evidence schema |
| `P0-06` | Regression gate consolidation | Ruff/mypy/pytest/security/package/real integration을 단일 검증 명령으로 묶는다. | clean checkout에서 full gate pass | verify-all script |
| `P0-07` | Maintenance branch policy | v1.0 hotfix와 future feature branch 정책을 분리한다. | direct main/force push 방지 | branch/release policy |

## P0 Codex phase kickoff 프롬프트

```text
P0 — 기준선·보안·거버넌스 정리의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
v1.0.0 이후 확장 전에 repository, baseline, evidence, profile drift를 정리한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P1. ADE·Simulation·Sweep 자동화 — 목표 버전 v1.1~v1.2

## Phase 목표

실제 회로를 parameterized profile로 실행하고, bounded result extraction과 sweep를 제공한다.

## 설계 방향

빠른 구현은 snapshot-netlist mode에서 시작한다. 기존 source netlist의 top-level parameter가 override 가능한지 확인하고, OA/state를 건드리지 않는 방식으로 1D sweep를 먼저 완성한다.

그 다음 fixed OCEAN template를 통해 ADE state-driven mode를 추가한다. 두 mode를 분리한다.

```text
snapshot_netlist
  - 빠르고 안전
  - 기존 netlist 재사용
  - schematic/state 변경 자동 반영 안 됨

ade_state
  - fixed state load
  - 최신 netlist 생성
  - 지원 API와 lock/state 불변성 검증 필요
```

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P1-01` | Fixed ADE profile introspection | allowlisted profile의 state, analyses, variables, outputs, model, lock을 read-only 조회한다. | raw content 없이 metadata 조회 성공 | ADE introspection tool |
| `P1-02` | Actual parameter binding discovery | VBIASN/VBIASP 및 후보 parameter의 exact Spectre/ADE binding을 확인한다. | parameter별 source of truth 확정 | variable contract draft |
| `P1-03` | User-approved variable contract | 단위/default/min/max/coarse/fine step을 승인한다. | unknown/out-of-range 거부 | approved variable schema |
| `P1-04` | Parameterized snapshot profile v2 | job-local wrapper에서 approved parameter를 변경한다. | 두 개 이상의 point 실제 Spectre 성공 | actual profile v2 |
| `P1-05` | PSF/OCEAN capability probe | IC6.1.5에서 scalar/waveform 추출 경로를 검증한다. | fixed signal 1개 bounded extraction 성공 | extraction capability report |
| `P1-06` | Bounded actual result extraction | logical output ID를 scalar/bounded waveform으로 반환한다. | raw PSF/path 미노출, units/provenance 포함 | measurement tools |
| `P1-07` | 1D sweep engine | plan/submit/status/result/cancel parent-child sweep를 구현한다. | 3-point actual sweep E2E 성공 | 1D sweep MCP tools |
| `P1-08` | Sweep recovery/idempotency | MCP/SSH interruption 후 child 중복 없이 resume한다. | duplicate child 0건 | sweep recovery |
| `P1-09` | 2D sweep | 두 axis Cartesian sweep와 deterministic ordering을 구현한다. | point cap 및 aggregate result 검증 | 2D sweep |
| `P1-10` | Corner campaign | 검증된 model section만 profile corner로 활성화한다. | 각 corner baseline E2E 성공 | corner registry |
| `P1-11` | Adaptive coarse-to-fine | approved budget 안에서 최대 2-stage refinement를 구현한다. | 무한 loop 없이 budget 준수 | adaptive sweep |
| `P1-12` | ADE state-driven runtime | fixed OCEAN/ADE template로 state load/netlist/run을 구현한다. | source/state/PDK 불변, baseline 성공 | ADE execution mode |
| `P1-13` | DC operating-point profile | device Id/gm/VDS/VDSAT/region/sat-margin를 구조화한다. | approved device allowlist만 반환 | DCOP contract |
| `P1-14` | AC/Noise/STB profiles | gain, bandwidth, phase margin, noise를 versioned contract로 제공한다. | 실제 baseline E2E와 units 검증 | AC/noise/stb tools |
| `P1-15` | Transient measurements | settling, slew, swing, power 등 approved metric을 actual waveform에 연결한다. | formula/provenance/reproducibility | transient contract |
| `P1-16` | Monte Carlo campaign | seed, run count, statistic contract를 bounded job으로 관리한다. | run cap, reproducible manifest | MC tools |
| `P1-17` | Simulation campaign dashboard artifact | sweep/corner/MC 결과를 machine-readable report로 생성한다. | raw design 없이 비교 가능 | campaign report |

## P1 Codex phase kickoff 프롬프트

```text
P1 — ADE·Simulation·Sweep 자동화의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
실제 회로를 parameterized profile로 실행하고, bounded result extraction과 sweep를 제공한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P2. Schematic 작성과 Revision 시스템 — 목표 버전 v1.3

## Phase 목표

에이전트가 원본이 아닌 controlled workspace에서 schematic과 testbench를 생성·수정한다.

## 설계 방향

이 phase부터 MCP가 단순 실행기를 넘어 설계 authoring 시스템이 된다.

핵심은 범용 SKILL eval이 아니라 semantic transaction이다.

```text
begin_revision
  → add_instance
  → set_parameter
  → create_net
  → connect_terminal
  → create_pin
  → validate
  → dry-run diff
  → commit revision
```

각 operation은 exact object ID와 typed parameter를 사용한다. 좌표/instance name/net name은 schema와 PDK adapter로 검증한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P2-01` | Project/workspace/revision model | project, workspace, revision DAG와 promotion 규칙을 구현한다. | 부모/자식 revision과 immutable manifest | revision service |
| `P2-02` | Library/cell/view controlled creation | approved work library 안에서 cell/view를 생성한다. | source/PDK write 0건 | cellview create tool |
| `P2-03` | Instance master registry | PDK/analogLib allowlist를 logical device ID로 추상화한다. | arbitrary lib/cell 입력 거부 | instance registry |
| `P2-04` | Add/remove/move instance | typed instance operation과 dry-run을 구현한다. | exact diff와 rollback | instance tools |
| `P2-05` | Device parameter mutation | W/L/m/intent parameter를 PDK schema로 검증한다. | unit/range/parameter allowlist | parameter tools |
| `P2-06` | Net and pin authoring | net 생성, terminal 연결, pin 생성/방향 검증을 구현한다. | connectivity hash 재현 가능 | net/pin tools |
| `P2-07` | Wire and schematic geometry | schematic presentation geometry를 deterministic하게 생성한다. | canonical placement, no overlap | schematic geometry |
| `P2-08` | Hierarchy and symbols | 하위 cell, symbol view, instance hierarchy를 관리한다. | symbol/schematic pin consistency | hierarchy tools |
| `P2-09` | Testbench generator | supply/source/load/clock/measure fixture를 profile template로 생성한다. | 실제 Spectre baseline 성공 | testbench tools |
| `P2-10` | Connectivity validator | floating pin, multiple driver, missing supply, illegal bulk 연결을 검사한다. | known bad fixtures 탐지 | schematic lint |
| `P2-11` | Canonical schematic fingerprint | instance/master/parameters/connectivity를 canonical hash로 만든다. | GUI metadata 변화에 안정적 | logical fingerprint |
| `P2-12` | Schematic semantic diff | revision 간 device/net/parameter diff를 구조화한다. | raw OA 파일 비교 없이 의미 diff | diff tool |
| `P2-13` | Transaction and rollback | multi-operation plan을 all-or-nothing으로 적용한다. | 실패 시 baseline 복원 | transaction engine |
| `P2-14` | Promotion/freeze | 검증된 revision을 schematic freeze 상태로 승격한다. | 승인·hash·evidence 요구 | freeze gate |
| `P2-15` | Golden inverter/diffamp authoring demo | 빈 work cell에서 두 회로를 생성하고 simulate한다. | DRC 이전 schematic E2E | authoring benchmark |

## P2 Codex phase kickoff 프롬프트

```text
P2 — Schematic 작성과 Revision 시스템의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
에이전트가 원본이 아닌 controlled workspace에서 schematic과 testbench를 생성·수정한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P3. 회로 합성·Sizing·최적화 — 목표 버전 v1.4

## Phase 목표

사양에서 topology 후보와 transistor sizing을 생성하고 simulation feedback으로 최적화한다.

## 설계 방향

에이전트가 회로를 “끝까지” 하려면 topology/parameter search를 단순 sweep보다 높은 수준으로 다뤄야 한다.

두 계층을 분리한다.

```text
Circuit reasoning layer
  - device role
  - gm/Id
  - headroom
  - gain/noise/speed trade-off

Execution layer
  - revision generation
  - profile execution
  - measurement
  - evidence
```

모델의 추론 결과는 반드시 typed design proposal로 변환되어야 하며, 직접 SKILL/넷리스트가 되면 안 된다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P3-01` | Specification contract | gain/BW/PM/power/noise/swing/input/output/load/yield 사양 schema를 만든다. | 모든 objective/constraint에 unit | spec schema |
| `P3-02` | Device role and intent model | diff pair, mirror, tail, cascode, gain stage, compensation 역할을 기록한다. | schematic와 layout intent에 재사용 | design intent |
| `P3-03` | Topology template library | inverter, mirror, diff pair, OTA/opamp 후보 template를 만든다. | template별 connectivity test | topology registry |
| `P3-04` | Initial sizing engine | gm/Id·current density·headroom 기반 초기값을 제안한다. | 공정 범위 내 finite proposal | sizing proposal |
| `P3-05` | Bias feasibility solver | operating region/headroom/current balance를 검사한다. | 불가능 topology early reject | bias solver |
| `P3-06` | Candidate revision generator | topology+sizing 조합을 work revision으로 생성한다. | deterministic revision | candidate generator |
| `P3-07` | Multi-objective score | spec margin, power, area, robustness를 score한다. | weight/provenance/version 고정 | objective engine |
| `P3-08` | Optimization campaign | grid/random/Bayesian/evolutionary 중 bounded algorithm을 plugin화한다. | run budget 강제 | optimizer |
| `P3-09` | Topology mutation | 승인된 template 간 topology 변경을 plan으로 생성한다. | 임의 netlist 생성 금지 | topology planner |
| `P3-10` | Stability compensation optimizer | Cc/Rz/second pole를 AC/STB feedback으로 조정한다. | PM 및 bandwidth constraint | compensation agent |
| `P3-11` | Noise/power optimizer | noise-power-speed Pareto frontier를 생성한다. | Pareto provenance | tradeoff explorer |
| `P3-12` | PVT robust optimization | nominal이 아닌 worst corner objective를 포함한다. | corner budget 및 yield report | robust optimizer |
| `P3-13` | Monte Carlo/yield closure | mismatch/process 분포에서 yield 기준을 검증한다. | seed/run count/confidence 기록 | yield campaign |
| `P3-14` | Human-in-the-loop topology gate | topology 변경 전 계획과 이유를 승인받는다. | 승인 없는 큰 구조 변경 0건 | approval gate |
| `P3-15` | Differential amplifier autonomous benchmark | spec→candidate→optimization→freeze까지 재현한다. | 최종 pre-layout spec pass | benchmark report |

## P3 Codex phase kickoff 프롬프트

```text
P3 — 회로 합성·Sizing·최적화의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
사양에서 topology 후보와 transistor sizing을 생성하고 simulation feedback으로 최적화한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P4. Layout DB Foundation — 목표 버전 v1.5

## Phase 목표

controlled work revision에서 PCell 배치와 geometry/routing을 생성하는 안전한 layout authoring 계층을 만든다.

## 설계 방향

처음부터 자동 analog layout을 시도하지 않는다. 먼저 OA layout DB를 안정적으로 읽고 쓰는 primitive와 transaction을 만든다.

모든 좌표는 technology database unit/grid에 맞게 quantize한다. layer-purpose pair와 via는 PDK adapter의 closed registry에서만 선택한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P4-01` | Layout read-only discovery | bbox, instances, shapes, pins, nets, layers를 metadata로 조회한다. | raw OA file 미노출 | layout inspect |
| `P4-02` | Layer-purpose registry | PDK의 허용 LPP와 grid를 logical ID로 매핑한다. | unknown layer 거부 | layer adapter |
| `P4-03` | PCell placement | approved device PCell을 parameterized inst로 생성한다. | master/parameter 검증 | layout add instance |
| `P4-04` | Move/rotate/orient | R0/R90/MX/MY 등 PDK 허용 orientation을 적용한다. | grid snap/overlap check | placement operations |
| `P4-05` | Primitive shapes | rect/path/polygon을 typed geometry로 생성한다. | bbox/layer/width validation | geometry tools |
| `P4-06` | Via/contact creation | fixed via definitions와 via array를 생성한다. | from/to layer consistency | via tools |
| `P4-07` | Layout pin creation | net/pin/layer/purpose를 검증하여 pin을 만든다. | schematic pin mapping | pin tool |
| `P4-08` | Floorplan boundary | cell boundary, keepout, routing region을 정의한다. | area/boundary contract | floorplan tool |
| `P4-09` | Net-aware route segments | schematic connectivity와 연결된 segment를 생성한다. | open/short precheck | routing primitive |
| `P4-10` | Layout transaction/dry-run | geometry plan, diff, backup, rollback을 구현한다. | exact semantic diff | layout transaction |
| `P4-11` | Connectivity extraction preview | layout 내 예상 net connectivity를 read-only 검사한다. | known open/short 탐지 | connectivity preview |
| `P4-12` | Layout revision fingerprint | instance/shape/pin/connectivity canonical hash를 만든다. | OA metadata에 안정적 | layout fingerprint |
| `P4-13` | Preview/export artifact | proprietary data를 보호하며 bbox/placement summary를 생성한다. | bounded preview | layout report |
| `P4-14` | Inverter layout primitive demo | PCell placement, contacts, routes, pins를 생성한다. | 첫 DRC 전 layout E2E | layout demo |

## P4 Codex phase kickoff 프롬프트

```text
P4 — Layout DB Foundation의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
controlled work revision에서 PCell 배치와 geometry/routing을 생성하는 안전한 layout authoring 계층을 만든다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P5. Analog Layout Intelligence — 목표 버전 v1.6

## Phase 목표

회로 역할과 matching intent를 실제 placement/routing 전략으로 변환한다.

## 설계 방향

analog layout의 핵심은 좌표 생성이 아니라 의도 보존이다.

```text
schematic role
  → matching group
  → placement pattern
  → routing symmetry
  → parasitic balance
  → DRC/LVS/PEX feedback
```

이 phase에서는 rule 기반 generator와 에이전트 planner를 결합한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P5-01` | Schematic-to-layout intent compiler | device role을 matching/symmetry/guard-ring constraint로 변환한다. | intent coverage report | intent compiler |
| `P5-02` | Finger/fold planner | W/L/m과 PDK max finger 규칙에서 finger arrangement를 계산한다. | electrical equivalence | finger planner |
| `P5-03` | Matched pair generator | 동일 orientation, shared environment, symmetric placement를 생성한다. | pair symmetry metrics | matched pair |
| `P5-04` | Current mirror generator | abutment/dummy/contact symmetry를 적용한다. | mirror matching intent pass | mirror template |
| `P5-05` | Common-centroid generator | ABBA/BAAB 등 pattern과 dummy를 생성한다. | centroid 계산 검증 | centroid tool |
| `P5-06` | Interdigitation | multi-device pattern과 edge dummy를 생성한다. | pattern/connectivity correctness | interdigitation tool |
| `P5-07` | Source/drain abutment | 전기적으로 허용된 diffusion sharing만 적용한다. | LVS equivalence precheck | abutment planner |
| `P5-08` | Guard ring/substrate contact | well/substrate tie와 ring을 PDK adapter로 생성한다. | latch-up/coverage rule | guard-ring tool |
| `P5-09` | Symmetric differential routing | VIN/VOUT differential pair routing balance를 관리한다. | length/via/layer symmetry metric | symmetry router |
| `P5-10` | Power/ground routing | current density-aware width/via array와 rails를 만든다. | IR/current density policy | power router |
| `P5-11` | Parasitic-aware placement heuristic | critical net length/coupling estimate로 배치를 score한다. | placement score reproducible | placement optimizer |
| `P5-12` | Density/fill planning | foundry-required fill을 functional layout과 분리한다. | LVS/PEX 영향 기록 | fill planner |
| `P5-13` | Layout plan approval artifact | floorplan·groups·estimated area·risks를 사용자에게 제시한다. | plan hash 승인 | layout plan |
| `P5-14` | Differential amplifier layout benchmark | input pair/mirror/tail/guard ring/routing을 생성한다. | DRC/LVS phase 진입 가능 | analog layout demo |

## P5 Codex phase kickoff 프롬프트

```text
P5 — Analog Layout Intelligence의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
회로 역할과 matching intent를 실제 placement/routing 전략으로 변환한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P6. Physical Verification: DRC·LVS·ERC — 목표 버전 v1.7

## Phase 목표

PDK verification deck을 고정 adapter로 실행하고 structured violation feedback과 bounded auto-fix를 제공한다.

## 설계 방향

verification backend는 PDK마다 다를 수 있으므로 공통 MCP contract와 backend adapter를 분리한다.

```text
MCP verification contract
        ↓
AssuraAdapter | PVSAdapter | CalibreAdapter
        ↓
fixed runset/deck
```

rule deck/path는 caller 입력이 아니라 technology adapter에서 고정한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P6-01` | Verification capability probe | assura/pvs/calibre executable, license, deck, batch mode를 read-only 확인한다. | backend matrix 확정 | capability report |
| `P6-02` | DRC plan contract | top cell, revision, backend, deck hash, budget을 canonical plan으로 만든다. | plan hash/approval | DRC plan |
| `P6-03` | DRC async lifecycle | submit/status/log/result/cancel을 기존 job system에 통합한다. | real layout DRC run | DRC tools |
| `P6-04` | DRC result parser | rule ID, bbox, count, severity를 structured JSON으로 만든다. | raw log 미노출 | DRC parser |
| `P6-05` | Violation-to-object mapping | bbox와 layout object reference를 안전하게 매핑한다. | ambiguous mapping 표시 | violation mapper |
| `P6-06` | DRC fix proposal | spacing/width/enclosure/via 등 fix class를 계획한다. | 실행 전 exact diff | fix planner |
| `P6-07` | Bounded DRC auto-fix loop | iteration/shape mutation/area budget 내에서 수정·재실행한다. | 무한 loop 없음, rollback | DRC agent |
| `P6-08` | LVS plan/lifecycle | fixed schematic/layout pair로 LVS를 실행한다. | real LVS run | LVS tools |
| `P6-09` | LVS result parser | open/short/missing/extra/parameter/pin mismatch를 구조화한다. | device/net mapping | LVS parser |
| `P6-10` | LVS fix proposal | connectivity/label/pin/device mismatch에 bounded fix를 제안한다. | topology 변경 승인 gate | LVS planner |
| `P6-11` | ERC/checks | floating gate, bulk tie, supply conflict, illegal connection을 검사한다. | ERC profile pass | ERC tool |
| `P6-12` | Antenna/DFM hooks | PDK가 제공할 경우 별도 adapter로 활성화한다. | unsupported는 명확히 보고 | optional checks |
| `P6-13` | Verification evidence bundle | deck/version/hash/result/fixes/iterations를 immutable bundle로 저장한다. | 재현 가능 evidence | signoff bundle |
| `P6-14` | DRC=0/LVS=PASS benchmark | agent-generated differential amplifier layout을 clean하게 만든다. | physical verification pass | benchmark report |

## P6 Codex phase kickoff 프롬프트

```text
P6 — Physical Verification: DRC·LVS·ERC의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
PDK verification deck을 고정 adapter로 실행하고 structured violation feedback과 bounded auto-fix를 제공한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P7. PEX·Post-layout Closure — 목표 버전 v1.8

## Phase 목표

추출된 parasitic을 이용해 post-layout simulation과 spec closure를 수행한다.

## 설계 방향

LVS pass 후에만 PEX를 허용한다. extracted view 또는 DSPF/SPEF 등 실제 PDK 지원 형식은 technology adapter가 정한다.

pre-layout와 post-layout 비교는 동일한 measurement contract를 사용한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P7-01` | PEX/RCX capability probe | 지원 backend, output view/file, corner, runset을 확인한다. | technology-specific path 확정 | PEX capability |
| `P7-02` | PEX plan/lifecycle | LVS-passed revision만 extraction 가능하게 한다. | LVS gate enforcement | PEX tools |
| `P7-03` | Extracted artifact validation | output 존재, top cell, net/device count, hash를 검증한다. | corrupt output fail-closed | PEX validator |
| `P7-04` | Post-layout config/profile | extracted view를 사용하는 fixed simulation profile을 만든다. | baseline post-layout E2E | postlayout profile |
| `P7-05` | Pre/post metric comparison | 동일 contract로 gain/BW/PM/power/noise 등을 비교한다. | delta와 margin report | comparison tool |
| `P7-06` | Parasitic hotspot analysis | critical net R/C와 성능 저하 상관을 구조화한다. | bounded summary | hotspot report |
| `P7-07` | Layout optimization loop | placement/routing/metal/via 변경을 plan하고 재검증한다. | iteration budget/rollback | postlayout optimizer |
| `P7-08` | Schematic resize feedback | layout만으로 해결 안 되면 sizing revision을 생성한다. | cross-domain approval | resize planner |
| `P7-09` | Post-layout PVT/MC | 필요 corner와 mismatch까지 post-layout에서 검증한다. | budgeted campaign | postlayout robustness |
| `P7-10` | Signoff-ready revision freeze | DRC/LVS/PEX/post-layout spec가 모두 pass한 revision을 freeze한다. | immutable signoff manifest | signoff gate |

## P7 Codex phase kickoff 프롬프트

```text
P7 — PEX·Post-layout Closure의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
추출된 parasitic을 이용해 post-layout simulation과 spec closure를 수행한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P8. PDK Abstraction 및 MyChip 재타깃팅 — 목표 버전 v1.9

## Phase 목표

GPDK090에서 검증한 설계 의도와 플랫폼 기능을 사용자에게 공식 제공된 MyChip PDK로 안전하게 port한다.

## 설계 방향

PDK migration은 파일 변환이 아니다.

재사용되는 것:

- specification
- topology intent
- device roles
- measurement contracts
- optimization framework
- layout intent
- verification orchestration

다시 수행해야 하는 것:

- device/PCell mapping
- supply/headroom feasibility
- W/L/current/bias sizing
- model/corner validation
- layout generation
- DRC/LVS/PEX
- pad/top integration
- post-layout signoff

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P8-01` | Technology adapter framework | PDK-dependent device/layer/model/deck/stream 정보를 plugin contract로 분리한다. | gpdk090 adapter로 regression pass | technology API |
| `P8-02` | PDK secure onboarding | MyChip PDK manifest, license, hash, access boundary를 등록한다. | raw PDK Git commit 0건 | PDK registry |
| `P8-03` | Device/PCell inventory | 공식 PDK에서 NMOS/PMOS/R/C/diode/IO 등 exact device schema를 추출한다. | approved device map | device adapter |
| `P8-04` | Model/corner inventory | Spectre model, section, temperature, mismatch 지원을 등록한다. | baseline smoke per section | model adapter |
| `P8-05` | Layer/via/grid inventory | LPP, routing metals, via, grid, purpose를 등록한다. | layout primitive capability | layout adapter |
| `P8-06` | Verification deck inventory | DRC/LVS/PEX backend와 fixed runset을 등록한다. | deck hash/version verified | verification adapter |
| `P8-07` | IO/pad/ESD inventory | 공식 pad library와 integration rule을 등록한다. | pad mapping approved | IO adapter |
| `P8-08` | Topology feasibility review | GPDK090 topology가 MyChip supply/device에 가능한지 분석한다. | feasible/modify/reject 판정 | porting report |
| `P8-09` | Initial re-sizing | MyChip model에서 gm/Id/headroom 기반 초기 sizing을 생성한다. | DC feasibility pass | ported revision |
| `P8-10` | Bias and operating-point closure | 새 공정에서 bias/current/saturation margin을 최적화한다. | DCOP criteria pass | bias campaign |
| `P8-11` | Pre-layout spec re-optimization | AC/TRAN/Noise/PVT/MC를 다시 수행한다. | MyChip pre-layout spec pass | ported schematic freeze |
| `P8-12` | Layout regeneration | GPDK090 좌표 scaling 없이 MyChip PCell/rule로 재합성한다. | layout intent preserved | ported layout |
| `P8-13` | MyChip DRC/LVS/PEX | 공식 deck으로 physical signoff를 수행한다. | DRC=0/LVS=PASS/PEX pass | MyChip signoff evidence |
| `P8-14` | Cross-PDK comparison | spec, area, power, speed, robustness 차이를 기록한다. | technology-neutral report | migration report |
| `P8-15` | MyChip design freeze | 제작 대상 revision을 immutable하게 freeze한다. | PDK/hash/approval complete | target freeze |

## P8 Codex phase kickoff 프롬프트

```text
P8 — PDK Abstraction 및 MyChip 재타깃팅의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
GPDK090에서 검증한 설계 의도와 플랫폼 기능을 사용자에게 공식 제공된 MyChip PDK로 안전하게 port한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P9. Chip Top·Padframe·Tapeout Package — 목표 버전 v1.9.x

## Phase 목표

core block을 chip top으로 통합하고 최종 GDS 및 제출 전 evidence를 생성한다.

## 설계 방향

이 phase에서 에이전트는 tapeout-ready package를 만들 수 있으나 MPW portal 제출과 비용 발생 작업은 사람만 수행한다.

PDK와 프로그램의 최신 submission rules를 매 tapeout campaign마다 다시 import하고 승인해야 한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P9-01` | Top-level architecture | core, bias, IO, supply, ground, test pin 구조를 정의한다. | top plan 승인 | chip top plan |
| `P9-02` | Padframe generation | official pad cells과 orientation/sequence를 배치한다. | pad list/pin map pass | padframe |
| `P9-03` | ESD/IO connectivity | pad-to-core protection과 IO rule을 검증한다. | ERC/LVS connectivity pass | IO evidence |
| `P9-04` | Power domain/decoupling | supply ring, rails, decap, current path를 설계한다. | IR/current density policy | power plan |
| `P9-05` | Seal ring/keepout/chip boundary | 공식 rule에 따라 top boundary를 구성한다. | die size/boundary pass | boundary layout |
| `P9-06` | Top routing | core-pad, supply, ground, sensitive nets를 route한다. | open/short 0건 | top routing |
| `P9-07` | Fill/density/DFM | 공식 deck에 맞는 fill/density를 적용한다. | density/DRC pass | fill evidence |
| `P9-08` | Final DRC/LVS/ERC | chip top 전체 verification을 수행한다. | final clean | top signoff |
| `P9-09` | Final PEX/post-layout | pad/package model 포함 여부를 명확히 하여 최종 simulation한다. | final spec pass | top postlayout report |
| `P9-10` | Stream-out map validation | official map으로 GDS/OASIS를 생성하고 layer summary를 검증한다. | unknown/forbidden layer 0건 | stream-out report |
| `P9-11` | GDS integrity checks | top cell, hierarchy, bbox, cell count, hash, reopen 검증을 수행한다. | round-trip open 성공 | GDS manifest |
| `P9-12` | Submission package builder | GDS, reports, pin map, checksums, forms checklist를 묶는다. | tapeout-ready package | submission bundle |
| `P9-13` | Independent signoff review | 별도 reviewer agent와 사람이 evidence를 검토한다. | critical issue 0건 | review report |
| `P9-14` | Human tapeout approval gate | 최종 GDS hash와 submission package에 explicit approval을 요구한다. | 승인 전 업로드 0건 | approval record |
| `P9-15` | Archive and reproducibility | source revision, PDK hash, tools, evidence를 장기 보관한다. | clean restore rehearsal | tapeout archive |

## P9 Codex phase kickoff 프롬프트

```text
P9 — Chip Top·Padframe·Tapeout Package의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
core block을 chip top으로 통합하고 최종 GDS 및 제출 전 evidence를 생성한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P10. 자율 Orchestrator와 Spec-to-Tapeout Campaign — 목표 버전 v2.0

## Phase 목표

모든 capability를 하나의 제한된 campaign state machine으로 연결한다.

## 설계 방향

v2.0에서 에이전트는 역할별 논리 단계를 갖지만, tool 권한은 하나의 policy engine이 통제한다.

권장 역할:

- Requirements Agent
- Circuit Architect
- Schematic Author
- Verification Agent
- Optimization Agent
- Layout Planner
- Layout Author
- Physical Verification Agent
- Post-layout Agent
- Signoff Reviewer

한 모델이 순차적으로 역할을 수행해도 되지만 각 단계의 input/output contract는 분리한다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P10-01` | Campaign state machine | spec부터 tapeout-ready까지 stage/status/transition을 정의한다. | invalid transition 거부 | campaign engine |
| `P10-02` | Task graph planner | dependency-aware plan과 budget을 생성한다. | cycle/unknown capability 거부 | task graph |
| `P10-03` | Agent role contracts | 각 역할의 허용 도구와 output schema를 분리한다. | least privilege | role policies |
| `P10-04` | Approval scheduler | topology/layout/large compute/signoff/tapeout gate를 관리한다. | 승인 reference 강제 | approval engine |
| `P10-05` | Budget manager | simulation points, MC runs, layout iterations, verification runs를 제한한다. | budget 초과 0건 | budget service |
| `P10-06` | Failure taxonomy/recovery | recoverable, blocked, unsafe, operator-required를 구분한다. | automatic retry policy 준수 | recovery engine |
| `P10-07` | Revision selection/Pareto archive | 후보 revision과 Pareto frontier를 보존한다. | best revision provenance | revision scorer |
| `P10-08` | Cross-domain feedback | simulation→sizing→layout→PEX feedback을 typed proposal로 변환한다. | unbounded mutation 금지 | feedback planner |
| `P10-09` | Independent reviewer agent | plan/diff/evidence를 별도 pass로 검토한다. | self-approval 금지 | review service |
| `P10-10` | End-to-end reproducibility | 동일 spec/seed/tool/PDK에서 campaign 재현을 검증한다. | deterministic evidence | replay system |
| `P10-11` | Benchmark suite | inverter, mirror, diffamp, opamp 등 점진 benchmark를 만든다. | 각 benchmark DoD | benchmark registry |
| `P10-12` | Spec-to-tapeout demo | GPDK090에서 전체 chain을 한 번 재현한다. | L7 acceptance pass | v2.0 demo |
| `P10-13` | MyChip tapeout-ready demo | 공식 PDK에서 제출 전 단계까지 재현한다. | human approval 직전 상태 | target demo |

## P10 Codex phase kickoff 프롬프트

```text
P10 — 자율 Orchestrator와 Spec-to-Tapeout Campaign의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
모든 capability를 하나의 제한된 campaign state machine으로 연결한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P11. 실리콘 측정과 Feedback — 목표 버전 v2.1

## Phase 목표

제작된 칩의 측정 데이터를 simulation과 비교하고 재설계 feedback으로 연결한다.

## 설계 방향

실리콘 단계는 EDA 자동화와 별도 safety domain이다. 계측기는 전용 instrument adapter와 limits를 사용하며, arbitrary SCPI를 모델에 노출하지 않는다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P11-01` | Measurement specification | DC/AC/transient/noise/power 측정 절차와 limits를 정의한다. | 사양/안전 승인 | measurement plan |
| `P11-02` | PCB/package/pin map model | package와 board connectivity를 machine-readable로 만든다. | pin map consistency | hardware manifest |
| `P11-03` | Instrument adapter | approved instrument와 bounded command template를 제공한다. | arbitrary SCPI 금지 | instrument MCP |
| `P11-04` | Calibration workflow | open/short/load/reference/calibration record를 관리한다. | calibration evidence | calibration service |
| `P11-05` | Automated characterization | voltage/frequency/temperature sweep를 안전 budget으로 수행한다. | hardware limits 준수 | silicon campaign |
| `P11-06` | Data ingestion | CSV/binary 측정 데이터를 versioned schema로 저장한다. | source hash/provenance | measurement store |
| `P11-07` | Sim-to-silicon comparison | pre/post/silicon metric을 동일 contract로 비교한다. | uncertainty 포함 | correlation report |
| `P11-08` | Discrepancy diagnosis | model/package/PCB/measurement/design 원인을 rank한다. | evidence-based hypotheses | diagnosis agent |
| `P11-09` | Model/design feedback | 다음 revision의 sizing/layout/test 개선안을 생성한다. | approval 기반 redesign | feedback plan |
| `P11-10` | Silicon learning archive | 설계·simulation·layout·실리콘 데이터를 연결한다. | 재사용 가능한 lesson | silicon knowledge base |

## P11 Codex phase kickoff 프롬프트

```text
P11 — 실리콘 측정과 Feedback의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
제작된 칩의 측정 데이터를 simulation과 비교하고 재설계 feedback으로 연결한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---


# P12. 플랫폼 확장과 운영 — 목표 버전 v2.2+

## Phase 목표

개인 연구용 시스템을 multi-project/multi-PDK/team 환경으로 확장한다.

## 설계 방향

이 phase는 완전 자율 기능 이후에 진행한다. 먼저 한 회로를 끝까지 재현하는 것이 다중 사용자 기능보다 우선이다.

## Work packages

| WP | 작업 | 목표 | 종료 기준 | 핵심 산출물 |
|---|---|---|---|---|
| `P12-01` | Multi-project registry | 프로젝트별 workspace/evidence/policy를 분리한다. | cross-project access 차단 | project service |
| `P12-02` | Multi-PDK adapter registry | gpdk090/MyChip/기타 PDK adapter를 versioning한다. | PDK drift detection | adapter registry |
| `P12-03` | Remote HTTP MCP | 필요할 때만 authentication을 갖춘 service mode를 추가한다. | stdio regression 없음 | service deployment |
| `P12-04` | Role-based access | read/compute/write/signoff/tapeout 권한을 사용자별로 분리한다. | least privilege | RBAC |
| `P12-05` | License-aware scheduler | Cadence/verification license capacity를 고려한다. | 과다 checkout 방지 | scheduler |
| `P12-06` | Artifact store | 대규모 PSF/GDS/evidence를 policy 기반 저장한다. | hash/retention/access | artifact service |
| `P12-07` | Observability | job/campaign/verification/agent decision metrics를 수집한다. | secret/design content 미노출 | monitoring |
| `P12-08` | Backup/disaster recovery | repository, runner config, evidence, work library 복구를 연습한다. | restore test pass | DR plan |
| `P12-09` | Policy-as-code | tool/PDK/project 승인 정책을 versioned policy로 관리한다. | policy test | policy engine |
| `P12-10` | Plugin capability framework | 새 simulator/DRC/PEX/instrument backend를 adapter로 추가한다. | core security 유지 | plugin SDK |
| `P12-11` | Compliance/export controls | PDK/license/organization policy를 enforce한다. | policy violation fail-closed | compliance gate |

## P12 Codex phase kickoff 프롬프트

```text
P12 — 플랫폼 확장과 운영의 첫 번째 미완료 WP 하나만 실행하라.

반드시 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md,
docs/VERIFIED_ENVIRONMENT.md, docs/SECURITY.md를 먼저 읽어라.

규칙:
- 최신 승인된 origin/main에서 해당 WP 전용 feature branch를 생성한다.
- 한 실행에서 한 WP만 수행한다.
- main 직접 commit/push, force-push, 자동 merge를 금지한다.
- arbitrary shell/SSH/SKILL/OCEAN/path tool을 추가하지 않는다.
- PDK/source/shared library를 수정하지 않는다.
- 위험 작업은 plan SHA-256과 별도 승인 없이는 실행하지 않는다.
- unit/static/security/package/real integration 중 해당 WP 수락 기준에 필요한 검증을 수행한다.
- PROJECT_STATE.md를 갱신하고 conventional commit 후 feature branch를 push한다.
- push SHA를 검증한 뒤 STOP한다.

이번 phase 목표:
개인 연구용 시스템을 multi-project/multi-PDK/team 환경으로 확장한다.

완료 보고서:
WORK PACKAGE RESULT
- WP
- Status
- Branch
- Commit
- Push verification
- Implemented
- Acceptance evidence
- Security evidence
- Real integration evidence
- Remaining risks
- User action required

NEXT RUN
- Next WP
- Recommended agent/model class
- Reasoning effort
- Exact start prompt

핵심 implementation과 signoff에는 사용 가능한 가장 강한 coding/reasoning model과 high/max effort를 사용하라.
문서/format-only 수정에는 빠른 모델을 사용할 수 있으나 acceptance 판단은 강한 모델로 재검토하라.
```

---

# 8. Cross-phase 의존성

```text
P0 Baseline/Governance
   ↓
P1 ADE/Simulation/Sweep
   ↓
P2 Schematic Authoring
   ↓
P3 Circuit Synthesis/Optimization
   ↓
P4 Layout Foundation
   ↓
P5 Analog Layout Intelligence
   ↓
P6 DRC/LVS/ERC
   ↓
P7 PEX/Post-layout
   ↓
P8 MyChip PDK Porting
   ↓
P9 Tapeout Package
   ↓
P10 Autonomous Orchestrator
   ↓
P11 Silicon Feedback
   ↓
P12 Platform Scaling
```

병렬 진행 가능한 항목:

- P0 evidence schema와 P1 read-only introspection
- P4 layout read-only discovery와 P6 verification capability probe
- P8 technology adapter framework와 MyChip secure onboarding
- P11 measurement schema와 PCB/pin-map 문서화

병렬 진행하면 안 되는 항목:

- baseline 결정 전 actual sweep
- schematic transaction 검증 전 topology mutation
- DRC parser 검증 전 auto-fix
- LVS pass 전 PEX
- MyChip adapter 검증 전 ported layout
- final signoff 전 GDS submission package
- explicit approval 전 MPW 업로드

---

# 9. Capability별 최종 MCP Tool Catalog

실제 이름은 versioning 과정에서 조정할 수 있으나 기능 경계는 유지한다.

## 9.1 Project/Revision

```text
cadence_project_list
cadence_project_create_workspace
cadence_revision_create
cadence_revision_get
cadence_revision_diff
cadence_revision_validate
cadence_revision_rollback
cadence_revision_freeze
cadence_campaign_status
```

## 9.2 Schematic

```text
cadence_schematic_inspect
cadence_schematic_plan
cadence_schematic_add_instance
cadence_schematic_remove_instance
cadence_schematic_set_parameter
cadence_schematic_create_net
cadence_schematic_connect
cadence_schematic_disconnect
cadence_schematic_create_pin
cadence_schematic_validate
cadence_testbench_create
```

## 9.3 Simulation/ADE

```text
cadence_inspect_ade_profile
cadence_list_profiles
cadence_get_profile
cadence_submit_profile
cadence_job_status
cadence_job_log_tail
cadence_job_result
cadence_cancel_job
cadence_get_profile_measurements
cadence_get_waveform_summary
```

## 9.4 Sweep/Optimization

```text
cadence_plan_sweep
cadence_submit_sweep
cadence_sweep_status
cadence_sweep_result
cadence_cancel_sweep
cadence_plan_optimization
cadence_submit_optimization
cadence_optimization_status
cadence_optimization_result
cadence_compare_revisions
```

## 9.5 Layout

```text
cadence_layout_inspect
cadence_layout_plan
cadence_layout_add_pcell
cadence_layout_move_instance
cadence_layout_create_shape
cadence_layout_create_via
cadence_layout_create_pin
cadence_layout_route_net
cadence_layout_create_matched_pair
cadence_layout_create_current_mirror
cadence_layout_create_common_centroid
cadence_layout_add_dummy
cadence_layout_add_guard_ring
cadence_layout_validate
```

## 9.6 Physical verification

```text
cadence_drc_plan
cadence_drc_submit
cadence_drc_status
cadence_drc_result
cadence_drc_propose_fix
cadence_drc_apply_approved_fix
cadence_lvs_plan
cadence_lvs_submit
cadence_lvs_result
cadence_lvs_propose_fix
cadence_erc_submit
cadence_erc_result
```

## 9.7 PEX/Post-layout

```text
cadence_pex_plan
cadence_pex_submit
cadence_pex_result
cadence_submit_postlayout_profile
cadence_compare_pre_post_layout
cadence_analyze_parasitic_hotspots
```

## 9.8 Technology/Porting

```text
cadence_technology_get
cadence_technology_capabilities
cadence_plan_pdk_port
cadence_generate_ported_revision
cadence_compare_technology_results
```

## 9.9 Tapeout

```text
cadence_chip_top_plan
cadence_padframe_plan
cadence_tapeout_preflight
cadence_stream_out_plan
cadence_stream_out_execute
cadence_submission_package_build
cadence_submission_package_verify
```

MPW portal upload tool은 기본적으로 만들지 않는다. 만들더라도 사람의 최종 confirmation token이 없는 실행을 거부한다.

## 9.10 Silicon

```text
lab_measurement_plan
lab_submit_characterization
lab_measurement_status
lab_measurement_result
lab_compare_sim_silicon
lab_generate_redesign_plan
```

---

# 10. 단계별 사용자 입력 체크리스트

## 10.1 P1 전

- [ ] repository visibility 확인
- [ ] authoritative VBIASN baseline 선택
- [ ] authoritative VBIASP baseline 확인
- [ ] 변수 min/max/default 승인
- [ ] output signal exact 이름 승인
- [ ] corner 목록 승인
- [ ] simulation budget 승인

## 10.2 P2 전

- [ ] work library와 위치 승인
- [ ] 생성 가능한 device/PCell 목록 승인
- [ ] schematic naming policy
- [ ] source library read-only 정책
- [ ] rollback/promote 정책

## 10.3 P4 전

- [ ] layout work library 승인
- [ ] 허용 layer-purpose/via registry
- [ ] grid/database unit
- [ ] PCell parameter schema
- [ ] 최대 geometry mutation budget

## 10.4 P6 전

- [ ] verification backend/executable
- [ ] license availability
- [ ] fixed DRC/LVS/PEX deck
- [ ] deck/version/hash
- [ ] result format
- [ ] maximum verification iteration

## 10.5 P8 전

- [ ] 공식 MyChip PDK package
- [ ] PDK license/usage policy
- [ ] official user guide
- [ ] device/PCell libraries
- [ ] models/corners
- [ ] DRC/LVS/PEX deck
- [ ] IO/pad library
- [ ] stream-out map
- [ ] submission rule
- [ ] PDK 자료의 Git 저장 금지 정책

## 10.6 P9 전

- [ ] 최종 top cell naming
- [ ] pad/pin map
- [ ] supply/ground plan
- [ ] die/area constraint
- [ ] package option
- [ ] final measurement plan
- [ ] tapeout cost/portal 담당자
- [ ] human final approval 절차

---

# 11. 테스트 전략

## 11.1 테스트 피라미드

```text
Schema/property tests
        ↓
Pure Python unit tests
        ↓
Mock SSH/runner tests
        ↓
Remote read-only integration
        ↓
Remote compute integration
        ↓
Controlled write validation
        ↓
DRC/LVS/PEX golden design integration
        ↓
End-to-end campaign
```

## 11.2 Golden fixtures

최소 fixture:

- RC smoke
- inverter schematic
- current mirror schematic
- differential pair schematic
- known DRC-clean inverter layout
- intentionally failing DRC layouts
- LVS pass/fail pairs
- small PEX golden case
- differential amplifier benchmark
- porting benchmark

## 11.3 Negative tests

반드시 검증:

- unknown profile/variable/output
- NaN/Inf/overflow
- range 방향 오류
- point cap 초과
- arbitrary path
- shell metacharacter
- SKILL/OCEAN code injection
- PDK/source write attempt
- symlink escape
- active OA lock
- stale baseline
- changed PDK hash
- mismatched plan hash
- evidence write failure
- timeout/cancel
- process identity reuse
- duplicate retry
- DRC parser ambiguity
- LVS mapping ambiguity

## 11.4 Physical verification golden acceptance

- known clean layout → DRC 0
- known violation fixture → exact rule/count
- known LVS pass → matched
- known open/short fixture → exact mismatch class
- PEX fixture → expected extracted artifact
- pre/post scalar within defined tolerance

---

# 12. 운영 KPI

기능 수보다 다음 지표가 중요하다.

## Simulation/Optimization

- spec convergence rate
- simulation count
- failed job rate
- human intervention count
- average spec margin
- PVT worst-case margin
- MC yield/confidence

## Schematic

- invalid connectivity detection rate
- rollback success rate
- revision reproducibility
- semantic diff accuracy

## Layout

- initial DRC violation count
- DRC iterations to clean
- LVS iterations to pass
- layout area
- matching symmetry score
- critical net parasitic score

## Post-layout

- pre/post gain degradation
- bandwidth degradation
- phase-margin degradation
- power change
- yield change

## Platform/Safety

- unauthorized tool attempt rejection
- arbitrary path/script exposure count
- source/PDK mutation count
- evidence completeness
- recovery success
- duplicate job count
- audit integrity

## Final tapeout

- final DRC/LVS/ERC/PEX status
- GDS round-trip validity
- submission package completeness
- reproducibility from frozen revision
- human signoff count

---

# 13. Risk Register

| 위험 | 영향 | 완화 |
|---|---|---|
| CentOS 6.5/IC6.1.5 legacy API | 지원 함수 부족, crash | capability probe, fixed compatibility scripts |
| OA lock/recovery artifact | 설계 손상 가능 | read-only preflight, Cadence-supported recovery, fail-closed |
| ADE snapshot stale | 잘못된 회로 실행 | state/source freshness hash, ADE state mode |
| parameter baseline 오류 | optimization 무효 | user-approved baseline contract |
| arbitrary code exposure | 시스템/PDK 손상 | semantic typed tools only |
| DRC/LVS log parser 오류 | 잘못된 clean 판정 | golden fixtures, raw evidence local retention, ambiguity block |
| PDK hardcoding | MyChip port 어려움 | technology adapter |
| 자동 DRC fix 무한 반복 | 설계 파괴/시간 낭비 | iteration/mutation/area budget |
| model overconfidence | 잘못된 topology/tapeout | independent reviewer, formal gates, human final approval |
| proprietary data Git 노출 | 라이선스/보안 문제 | private repo, secret scan, no raw PDK/netlist/PSF |
| license capacity | job starvation | concurrency 1 → license-aware scheduler |
| GDS 제출 오류 | 제작 실패 | round-trip validation, checksum, independent signoff |
| MyChip rule 변경 | outdated submission | campaign마다 official docs re-import |
| 실리콘 측정 오차 | 잘못된 feedback | calibration, uncertainty, board/package model |

---

# 14. 최소 데모와 최종 데모

## 14.1 첫 강력한 포트폴리오 데모

대상을 `Differential_Amplifier_TB2` 하나로 제한한다.

```text
사용자 사양
→ agent가 bias/sizing 최적화
→ DC/AC/TRAN/PVT
→ schematic revision freeze
→ matched input pair layout
→ DRC clean
→ LVS pass
→ PEX
→ post-layout spec 비교
```

필수 공개 결과:

- 목표 사양
- topology/역할
- simulation iterations
- pre-layout 결과
- layout intent
- DRC count 변화
- LVS 결과
- post-layout 결과
- agent decision log
- safety/approval architecture

## 14.2 GPDK090 최종 검증 데모

```text
Specification → GPDK090 tapeout-ready equivalent
```

실제 fabrication submission은 하지 않더라도 GDS, DRC/LVS/PEX, post-layout, evidence까지 완료한다.

## 14.3 MyChip 최종 목표 데모

```text
GPDK090 verified intent
→ MyChip technology adapter
→ re-sizing/re-optimization
→ MyChip layout regeneration
→ official DRC/LVS/PEX
→ pad/top
→ GDS/package
→ human-approved MPW submission
```

## 14.4 실리콘 데모

```text
Pre-layout vs Post-layout vs Measured Silicon
```

같은 measurement contract로 비교한다.

---

# 15. Definition of Done

## v1.1 Done

- actual variables 승인·실행
- bounded actual measurement
- 1D sweep
- source/state/PDK unchanged

## v1.3 Done

- blank work cell에서 schematic/testbench 생성
- semantic diff/rollback
- actual simulation pass

## v1.4 Done

- spec 기반 sizing campaign
- pre-layout spec pass
- PVT/MC evidence

## v1.6 Done

- differential amplifier analog layout 생성
- matching/symmetry intent 반영

## v1.7 Done

- DRC 0
- LVS pass
- structured fix loop

## v1.8 Done

- PEX pass
- post-layout spec pass

## v1.9 Done

- MyChip adapter
- ported schematic/layout
- official deck signoff
- tapeout-ready frozen revision

## v2.0 Done

- 한 번의 approved campaign에서 spec-to-tapeout-ready chain 재현
- 모든 stage evidence와 approval
- 임의 shell/SKILL/OCEAN/path interface 없음
- source/PDK 무단 변경 0건

## v2.1 Done

- 실리콘 계측 campaign
- sim-to-silicon correlation
- redesign feedback

---

# 16. 바로 다음 실행 순서

가장 현실적인 순서:

```text
1. P0-01 repository visibility/security
2. P0-03 authoritative baseline
3. P1-01 ADE introspection
4. P1-02 parameter binding
5. P1-03 user-approved variable contract
6. P1-04 parameterized actual profile
7. P1-05/P1-06 result extraction
8. P1-07 1D sweep
9. P1-12 ADE state runtime
10. P1-13~16 analyses/corner/MC
11. P2 schematic revision/authoring
12. P3 optimization
13. P4/P5 layout
14. P6 DRC/LVS
15. P7 PEX
16. P8 MyChip porting
17. P9 tapeout package
18. P10 autonomous campaign
```

현재 가장 먼저 사용자와 확정할 항목:

```yaml
authoritative_actual_baseline:
  VBIASN: 300m_or_370m
  VBIASP: 650m

initial_sweep_policy:
  variable: VBIASN
  unit: V
  minimum:
  maximum:
  coarse_step:
  fine_step:
  automatic_point_limit:
  confirmed_point_limit:

initial_outputs:
  - exact_signal_or_measurement:
```

---

# 17. 최종 설계 철학

1. **GPDK090은 automation sandbox이자 golden regression PDK로 사용한다.**
2. **MyChip PDK는 실제 fabrication target adapter로 취급한다.**
3. **공정 간에는 topology와 design intent를 이동하고 W/L과 layout은 재최적화·재생성한다.**
4. **MCP는 임의 명령 통로가 아니라 EDA semantic API다.**
5. **모든 변화는 revision, plan hash, evidence, rollback을 가진다.**
6. **DRC clean만으로 성공이 아니며 LVS·PEX·post-layout spec까지 필요하다.**
7. **에이전트 자율성은 실험 budget과 approval gate 안에서만 증가한다.**
8. **최종 MPW 제출과 비용 발생은 사람이 승인한다.**
9. **실리콘 결과는 다음 설계 campaign의 학습 evidence로 연결한다.**
10. **한 회로를 끝까지 재현 가능하게 완성한 뒤 회로 종류와 PDK를 확장한다.**

---

# 18. 최종 비전

최종 사용자 경험:

```text
“공식 MyChip PDK를 사용해서 1 V differential amplifier를 설계해.
DC gain, bandwidth, phase margin, power, swing, noise 조건을 만족시키고,
PVT/Monte Carlo를 확인해. layout은 matching을 고려해서 생성하고,
DRC/LVS/PEX와 post-layout 검증을 끝낸 다음,
padframe과 GDS 제출 패키지를 준비해.
실제 MPW 제출은 내 최종 승인 전에는 하지 마.”
```

에이전트의 최종 결과:

```text
CAMPAIGN_COMPLETE_TAPEOUT_READY

- Frozen design revision
- Authoritative PDK manifest
- Schematic and testbench
- Pre-layout verification
- Optimization history
- PVT/Monte Carlo evidence
- Layout intent and layout revision
- DRC clean
- LVS pass
- PEX pass
- Post-layout spec pass
- Chip-top/padframe verification
- GDS SHA-256
- Submission package
- Independent review report
- Human approval required: YES
```

이 상태가 프로젝트의 장기적인 완료 목표다.
