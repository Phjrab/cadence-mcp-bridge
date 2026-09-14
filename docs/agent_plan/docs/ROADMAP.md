# 최종 통합 전체 로드맵 — Autonomous Custom IC Design

## 1. 최종 목표와 완료의 의미

사용자가 사양·대상 공정·제약·예산을 제시하면 에이전트가 지원되는 capability를 조합하여 설계 의도, schematic/testbench, simulation, optimization, layout, physical verification, post-layout와 제출 전 검증을 수행한다. 이후 공식 제작된 칩의 측정·분석으로 피드백을 연결한다.

이 목표는 특정 구형 설치에 존재하지 않는 모든 제품 옵션을 있다고 가정하는 것이 아니다. capability는 도구/버전/PDK/license/검증 evidence와 함께 등록한다. unsupported 기능은 적법한 별도 backend로 확장하며 source와 기존 환경을 손상시키지 않는다.

목표 사용자 요청:

> 승인된 대상 PDK와 사양에서 회로를 설계하고 검증하라. 현재 연구의 VDD=1.0 V 제약과 승인한 입력/출력/부하 조건을 유지하라. 성능 미달이면 원인을 보고하고 승인 범위 안에서 topology/sizing/layout을 탐색하라. DRC/LVS/PEX와 post-layout, chip-top 및 최종 제출 bytes 검증까지 증거를 연결하라. 실제 MPW 제출·비용 발생은 최종 승인 전 수행하지 마라.

기능 범위는 이전 170개 capability를 유지하고 ADC/AMS/RF·중단 복구·승인 경계 등 보강안을 통합한다. 120개 새 실행 계획은 업무 묶음이며 구현 완료 수가 아니다.

## 2. 성공 상태를 분리한다

| 상태 | 의미 | 의미하지 않는 것 |
|---|---|---|
| CODE_VERIFIED | local/schema/unit 검증 | 실제 Cadence 동작 |
| CAPABILITY_REAL_VERIFIED | 특정 도구/PDK 조합의 실제 fixture 통과 | 모든 회로 지원 |
| CIRCUIT_SPEC_VERIFIED | 고정 revision과 측정 계약에서 사양 충족 | layout/실리콘 사양 보장 |
| FLOW_VALIDATED_GPDK090 | generic PDK에서 흐름 검증 | 실제 제조 공정 signoff |
| FAB_PDK_VALIDATED | 공식 제작 PDK에서 필요한 검증 | 제출 파일·폼·패키지 준비 완료 |
| SUBMISSION_READY | 제출 대상 bytes와 모든 요구 evidence 일치 | 이미 제출/주문함 |
| HUMAN_APPROVED_FOR_SUBMISSION | 특정 package hash에 사람 승인 | 다른 파일/공정/비용 자동 승인 |
| SILICON_CHARACTERIZED | 안전하게 측정한 실리콘 결과 확보 | 모델의 예측만으로 측정 완료 |

GPDK090을 실제 제조 공정과 동일하게 취급하지 않는다.[E4] MyChip의 exact node/device/voltage/pad/deck/프로그램 규정은 공식 제공 자료를 import한 뒤 확인한다.

## 3. 아키텍처

```text
사용자 사양·운영자 승인
  ↓
설계 에이전트: 계획·가설·제안·불확실성 설명
  ↓
검토된 typed MCP semantic tools
  ↓
정책/승인/예산 + project/revision/campaign 서비스
  ├─ durable journal·상태·artifact·증거 DAG
  ├─ spec evaluator·precision measurement·수치 optimizer
  └─ TechnologyAdapter와 capability registry
  ↓
고정 SSH dispatcher / reviewed execution backend
  ├─ legacy CentOS runner: Bash/Python2.6/fixed SKILL/OCEAN/Spectre
  └─ 필요 시 별도 지원 환경의 reviewed runner
  ↓
Schematic / Simulation / Layout / DRC·LVS·ERC / PEX / Stream
  ↓
같은 revision의 유효한 결과 묶음 → freeze → 제출 준비
```

핵심 서비스는 초기에 최소 구현하고 고급 multi-user/multi-agent 기능은 뒤에서 확장한다. 모델이 policy·승인·평가자를 스스로 수정하는 구조는 금지한다.

## 4. 작은 완주 마일스톤

### M0 — 실행 기반을 믿을 수 있는 상태

문서/현재 이력 정리, 기본 PDK capability, approval/journal/소유권/예산/semantic hash, 실제 백업 복원. 새 설계 write 전에 first-write journal과 staging이 있어야 한다.

### M1 — 의미가 확인된 3-point 실험

기존 netlist의 실제 binding과 effective parameter를 검증하고 DCOP/적합한 metric을 추출한다. 3개 job 성공이 아니라 3개 의도한 조건이 실행됐음을 확인한다. 재접속/중복/취소와 원본 보존도 포함한다.

### M2 — 작은 회로 전체 경로

inverter 또는 current mirror를 typed 작업으로 생성한다. schematic/CDF/netlist/PCell 파라미터 일치, DRC/LVS clean·known-bad, 작은 PEX와 post-layout를 하나의 revision evidence로 묶는다. 많은 topology를 만들기 전에 이 경로를 검증한다.

### M3 — 증폭기 전체 경로

DUT/TB/bias/CMFB/startup/load 사양을 고정한다. gm/Id 근거, sizing, PVT·지원 MC, matching layout, DRC/LVS/PEX, 정밀 post-layout 및 holdout 검증으로 완주한다.

### M4 — 공식 제작 PDK와 실제 제출 준비

기술 어댑터·공식 tool/deck 조합을 검증하고 re-sizing·새 layout·pad/package·최종 stream 검증을 수행한다. GPDK 결과를 그대로 제조 근거로 가져가지 않는다.

### M5 — 회로군·자율성·실리콘·운영 확장

bounded campaign을 고도화하고 ADC/AMS/RF와 추가 PDK, 계측/실리콘 비교, 팀 서비스와 장기 운영을 확장한다. optional 기능의 미지원은 명시적으로 남긴다.

## 5. 16개 phase

| Phase | 범위 | 작업 수 | 목표 |
|---|---|---:|---|
| [F00](../phases/F00.md) | 기록 복구·문서 통합·현재 상태 정합성 | 6 | 실제 로컬 진행 이력과 통합 계획을 연결하고 다음 작업을 정확히 선택한다. |
| [F01](../phases/F01.md) | 최소 공통 기반: 기술 계약·권한·journal·복구 | 9 | 나중 모든 기능이 재사용할 단일 사용자 신뢰성 기반을 먼저 구현한다. |
| [F02](../phases/F02.md) | 실제 ADE·parameter·정밀 measurement | 10 | 현재 회로의 입력과 실제 적용·결과 해석을 연결한다. |
| [F03](../phases/F03.md) | 1D·2D·corner·Monte Carlo·adaptive campaign | 8 | 실험을 정확한 조건과 bounded parent-child 작업으로 재현한다. |
| [F04](../phases/F04.md) | Schematic 작성·revision·CDF round-trip | 9 | 원본이 아닌 승인된 작업 revision에서 에이전트가 회로와 testbench를 생성한다. |
| [F05](../phases/F05.md) | 초기 layout primitive와 DRC/LVS/PEX 검증기 | 7 | 큰 analog layout 이전에 작은 primitive 전체 물리 검증 경로를 완주한다. |
| [F06](../phases/F06.md) | 회로 특성화·사양·topology·sizing 최적화 | 8 | 측정된 모델 근거로 회로를 설계하고 독립 검증기로 사양 충족을 판정한다. |
| [F07](../phases/F07.md) | Analog layout intelligence·제약 routing | 9 | matching과 연결·기생 제약을 만족하는 실제 analog layout을 생성한다. |
| [F08](../phases/F08.md) | 정식 physical verification·PEX·post-layout closure | 8 | 작은 검증기에서 확장하여 증폭기와 chip 후보의 물리·수치 결과를 연결한다. |
| [F09](../phases/F09.md) | ADC·AMS·digital control·RF 확장 | 8 | 모든 회로 목표에서 빠지기 쉬운 혼합신호·클록·디지털·주기해석 capability를 추가한다. |
| [F10](../phases/F10.md) | 공식 제작 PDK onboarding·MyChip 재타깃팅 | 6 | GPDK 자동화 능력을 실제 제공받은 제작 공정의 검증된 조합으로 이관한다. |
| [F11](../phases/F11.md) | Chip top·pad/package·최종 stream·제출 준비 | 8 | 실제로 제출할 데이터와 검증 결과를 일치시키고 사람의 최종 승인 지점을 만든다. |
| [F12](../phases/F12.md) | End-to-end orchestrator·제한된 자율 설계 | 7 | 이미 검증한 도구들을 하나의 campaign으로 조합하되 지시·권한·평가를 분리한다. |
| [F13](../phases/F13.md) | 실리콘 계측·PCB·sim-to-silicon feedback | 6 | 칩을 받은 뒤의 측정 안전과 데이터 정확성을 별도 도메인으로 구현한다. |
| [F14](../phases/F14.md) | 운영 확장·다중 환경·multi-project | 6 | 기본 단일 사용자 시스템을 팀·다중 PDK·새 도구 환경으로 확장한다. |
| [F15](../phases/F15.md) | Release·문서·평가·포트폴리오 패키징 | 5 | 완료한 범위만 정확히 공개·배포하고 재현 가능한 연구·경력 증거를 만든다. |

## 6. 권장 실제 진행 경로

```text
PKG-INTEGRATE-01 (문서 통합, 기존 작업 진행 상태 유지)
 → F00 현재 이력·baseline·DUT 경계
 → F01 최소 권한/journal/소유권/예산/기술계약
 → F02 binding·실제 변수·DCOP/measurement
 → F03 1D 3-point + recovery (M1)
 → F04 작은 schematic + F05 기본 DRC/LVS/PEX (M2)
 → F06 sizing + F07 analog layout + F08 postlayout (M3)
 → F10 공식 target onboarding/retarget + F11 top/최종 bytes (M4)
 → F12 bounded full campaign과 F09/F13/F14 확장 (M5)
```

F10의 PDK 확보·license/tool feasibility와 F13의 pin/측정 계획은 공식 자료를 받을 수 있는 시점에 일찍 병행한다. F05의 read-only tool/deck probe도 layout 완성까지 기다리지 않는다.

F15는 모든 미래 기능 완료 후에만 한 번 수행하는 phase가 아니다. 마일스톤별 release 범위를 검토할 때 재사용하는 유지보수 capability다. 새 실제 실행 ID와 승인 범위를 기록한다.

## 7. 주요 설계 결정

### 7.1 고정 profile에서 범용 semantic capability로

v1의 고정 source/profile을 그대로 유지하고 versioned actual profile을 추가한다. 이후 project/workspace/revision·device registry로 일반화한다. caller가 arbitrary shell/SKILL/OCEAN/path를 전달하는 우회 API로 넓히지 않는다.

### 7.2 ADE의 세 가지 실행 mode

snapshot은 과거 netlist 재생이다. state-driven은 고정 OCEAN/state 설정에서 job-local 최신 netlist를 생성한다. live GUI는 저장되지 않은 상태/lock/window identity를 가진 별도 기능이다. batch 기능 완료를 모든 ADE GUI 조작 완료로 표현하지 않는다.

### 7.3 측정과 탐색의 책임

agent는 실험 방향을 제안하고, 수치 엔진이 후보·grid·Pareto를 계산하며, 고정된 evaluator가 사양을 판정한다. optimizer는 목표·허용오차·측정식을 바꾸어 통과할 수 없다.

### 7.4 Layout과 physical oracle

CDF/netlist/PCell 파라미터가 일치하는 작은 primitive부터 생성한다. 기본 DRC/LVS parser와 known-bad fixture를 먼저 갖춘 뒤 analog matching·router·auto-fix를 확장한다. DRC 위반 감소를 위해 연결을 삭제하거나 LVS 통과를 위해 기준 schematic을 임의로 바꾸지 않는다.

### 7.5 PEX와 결과 유효성

LVS-passed pair에서 extraction을 수행하고 실제 simulator가 extracted representation을 사용했는지 확인한다. device 이중 포함, schematic fallback, 잘못된 RC corner를 잡는다. layout 변경은 기존 DRC/LVS/PEX/postlayout/final-stream evidence의 현재 유효성을 잃게 한다.

### 7.6 제작 경계

이상적인 TB 전원·자극은 온칩 회로가 아니다. DUT/온칩 bias/reference/IO/ESD/pad/package/PCB를 구분한다. 최종 stream bytes와 rule/runset/top/signoff/pinmap을 연결한다. portal submission/order는 별도 책임자 승인이다.

## 8. 아직 확정되지 않은 항목

현재 branch/HEAD, 실제 repository visibility, WP 진척, 설치 SDK/model selector, Assura/PVS/Calibre/PEX license, 실제 waveform/device IDs, 현재 연구 baseline, approved variable 범위, MyChip process/node/voltage/device/deck/pad/package/submission 규정은 필요한 시점에 확인한다.

전부를 지금 사용자에게 다시 질문하지 않는다. 먼저 기존 state/로컬 metadata/승인/공식 PDK에서 찾는다. 진짜 미확정 결정만 exact 대상과 필요한 이유를 모아 질문한다. 조사 권한이 없는 데이터를 임의로 읽거나 공개하지 않는다.

## 9. 지원 범위의 성장

- 초기: 단일 gpdk090 profile, 동시 실행 1개, default no automatic execution retry.
- 중기: 승인 envelope 안 variable/sweep/revision/layout repair; staging 변경과 resume.
- 후기: 추가 PDK/도구/회로군·최종 제출 준비·계측.
- 고급: 역할 분리·team/RBAC·authenticated HTTP·license-aware scheduling.

범위를 늘릴 때마다 schema/version/capability evidence·threat model·negative tests를 갱신한다. 미래 기능 명세를 현재 구현/권한으로 승격하지 않는다.

## 10. 원래 자료와 보강안 추적

[170개 원래 기능 대응표](LEGACY_CAPABILITY_CROSSWALK.md), [21개 보강 요구사항](HARDENING_TRACEABILITY.md), [120개 프롬프트](WORK_PACKAGE_INDEX.md)를 함께 사용한다. 누락 없는 범위와 실제 완료 여부는 별개다.
