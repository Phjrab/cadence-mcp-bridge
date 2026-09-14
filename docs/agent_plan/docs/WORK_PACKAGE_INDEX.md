# 전체 120개 작업 프롬프트 색인

16개 phase, 120개 실행 계획이다. 이 색인은 현재 프로젝트의 진행 상태가 아니다.
진행 순서는 현재 evidence·승인·DAG·마일스톤에 따라 결정한다. F00→F15 전체 직렬 완주를 첫 데모의 조건으로 만들지 않는다. 부족한 approval/API/장비를 발견해도 독립된 local 설계와 테스트는 가능한 범위에서 완료한다.

작업 ID는 stable하다. 기존 동일 기능이 완료돼 있으면 evidence를 연결하여 재사용한다. 큰 작업은 하위 ID로 분할하고 기존 ID를 다른 의미로 재사용하지 않는다.

## [F00 — 기록 복구·문서 통합·현재 상태 정합성](../phases/F00.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-00-01](../prompts/work_packages/ICF-00-01.md) | 현황·authority·작업 ID 매핑 | GPT-5.6 Terra / High | 통합 확인 |
| [ICF-00-02](../prompts/work_packages/ICF-00-02.md) | 저장소 접근·노출·데이터 분류 점검 | GPT-5.6 Terra / High | ICF-00-01 |
| [ICF-00-03](../prompts/work_packages/ICF-00-03.md) | 호환 baseline과 연구 baseline 정리 | GPT-5.6 Sol / High | ICF-00-02 |
| [ICF-00-04](../prompts/work_packages/ICF-00-04.md) | DUT·TB·chip-top·측정 경계 정의 | GPT-5.6 Sol / High | ICF-00-03 |
| [ICF-00-05](../prompts/work_packages/ICF-00-05.md) | 모델·SDK·환경 호환표 동기화 | GPT-5.6 Terra / High | ICF-00-04 |
| [ICF-00-06](../prompts/work_packages/ICF-00-06.md) | 다음 실행 전용 계획 생성 | GPT-5.6 Terra / High | ICF-00-05 |

## [F01 — 최소 공통 기반: 기술 계약·권한·journal·복구](../phases/F01.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-01-01](../prompts/work_packages/ICF-01-01.md) | 최소 TechnologyAdapter와 capability 모델 | GPT-5.6 Sol / High | ICF-00-06 |
| [ICF-01-02](../prompts/work_packages/ICF-01-02.md) | 권한 저장소·운영 역할 경계 | GPT-5.6 Sol / Extra High | ICF-01-01 |
| [ICF-01-03](../prompts/work_packages/ICF-01-03.md) | Durable intent journal·manifest 기초 | GPT-5.6 Sol / Extra High | ICF-01-02 |
| [ICF-01-04](../prompts/work_packages/ICF-01-04.md) | Durable job identity·소유권 복원 | GPT-5.6 Sol / Extra High | ICF-01-03 |
| [ICF-01-05](../prompts/work_packages/ICF-01-05.md) | 예산·queue·라이선스·디스크 상한 | GPT-5.6 Sol / Extra High | ICF-01-04 |
| [ICF-01-06](../prompts/work_packages/ICF-01-06.md) | Revision·semantic hash·stale evidence 기초 | GPT-5.6 Sol / Extra High | ICF-01-05 |
| [ICF-01-07](../prompts/work_packages/ICF-01-07.md) | 격리된 staging 변경·복구 framework | GPT-5.6 Sol / Extra High | ICF-01-06 |
| [ICF-01-08](../prompts/work_packages/ICF-01-08.md) | 백업·복원 연습 및 배포 rollback 기초 | GPT-5.6 Sol / High | ICF-01-07 |
| [ICF-01-09](../prompts/work_packages/ICF-01-09.md) | 공통 검증·보호 데이터·상태 gate | GPT-5.6 Terra / High | ICF-01-08 |

## [F02 — 실제 ADE·parameter·정밀 measurement](../phases/F02.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-02-01](../prompts/work_packages/ICF-02-01.md) | 고정 read-only ADE introspection | GPT-5.6 Sol / High | ICF-00-06, ICF-01-01 |
| [ICF-02-02](../prompts/work_packages/ICF-02-02.md) | Parameter binding·effective value 탐색 | GPT-5.6 Sol / High | ICF-02-01 |
| [ICF-02-03](../prompts/work_packages/ICF-02-03.md) | 실제 변수 contract와 profile v2 | GPT-5.6 Sol / High | ICF-02-02, ICF-01-03, ICF-01-04, ICF-01-05 |
| [ICF-02-04](../prompts/work_packages/ICF-02-04.md) | PSF·result 접근 capability probe | GPT-5.6 Sol / High | ICF-02-03 |
| [ICF-02-05](../prompts/work_packages/ICF-02-05.md) | 정밀 측정과 bounded preview 분리 | GPT-5.6 Sol / High | ICF-02-04 |
| [ICF-02-06](../prompts/work_packages/ICF-02-06.md) | DCOP·headroom·전력 reference | GPT-5.6 Sol / High | ICF-02-05 |
| [ICF-02-07](../prompts/work_packages/ICF-02-07.md) | 차동 AC·noise·loop stability | GPT-5.6 Sol / High | ICF-02-06 |
| [ICF-02-08](../prompts/work_packages/ICF-02-08.md) | Transient·startup·settling 계약 | GPT-5.6 Sol / High | ICF-02-07 |
| [ICF-02-09](../prompts/work_packages/ICF-02-09.md) | State-driven OCEAN·최신 netlisting | GPT-5.6 Sol / High | ICF-02-08, ICF-01-09 |
| [ICF-02-10](../prompts/work_packages/ICF-02-10.md) | Live ADE GUI bridge의 별도 경계 | GPT-5.6 Sol / High | ICF-02-09 |

## [F03 — 1D·2D·corner·Monte Carlo·adaptive campaign](../phases/F03.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-03-01](../prompts/work_packages/ICF-03-01.md) | Sweep plan와 실험 의미 schema | GPT-5.6 Terra / High | ICF-01-09, ICF-02-06 |
| [ICF-03-02](../prompts/work_packages/ICF-03-02.md) | 1D parent-child submit·status·result | GPT-5.6 Sol / High | ICF-03-01 |
| [ICF-03-03](../prompts/work_packages/ICF-03-03.md) | 중단 복구·취소·소유권·cache | GPT-5.6 Sol / Extra High | ICF-03-02 |
| [ICF-03-04](../prompts/work_packages/ICF-03-04.md) | 2D·list·log·native sweep 확장 | GPT-5.6 Sol / High | ICF-03-03 |
| [ICF-03-05](../prompts/work_packages/ICF-03-05.md) | PVT corner campaign | GPT-5.6 Sol / High | ICF-03-04 |
| [ICF-03-06](../prompts/work_packages/ICF-03-06.md) | Monte Carlo process·mismatch·yield | GPT-5.6 Sol / High | ICF-03-05 |
| [ICF-03-07](../prompts/work_packages/ICF-03-07.md) | Coarse-to-fine bounded refinement | GPT-5.6 Sol / High | ICF-03-06 |
| [ICF-03-08](../prompts/work_packages/ICF-03-08.md) | Campaign 비교·report·첫 실험 완주 | GPT-5.6 Terra / High | ICF-03-07 |

## [F04 — Schematic 작성·revision·CDF round-trip](../phases/F04.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-04-01](../prompts/work_packages/ICF-04-01.md) | Workspace·revision DAG·promotion | GPT-5.6 Sol / Extra High | ICF-01-09, ICF-02-03, ICF-01-07 |
| [ICF-04-02](../prompts/work_packages/ICF-04-02.md) | Logical device·pin·parameter registry | GPT-5.6 Sol / High | ICF-04-01 |
| [ICF-04-03](../prompts/work_packages/ICF-04-03.md) | Typed instance·parameter 작성 | GPT-5.6 Sol / Extra High | ICF-04-02 |
| [ICF-04-04](../prompts/work_packages/ICF-04-04.md) | Net·terminal·pin 연결과 검증 | GPT-5.6 Sol / Extra High | ICF-04-03 |
| [ICF-04-05](../prompts/work_packages/ICF-04-05.md) | Schematic 표현·symbol·hierarchy | GPT-5.6 Sol / Extra High | ICF-04-04 |
| [ICF-04-06](../prompts/work_packages/ICF-04-06.md) | DUT와 TB generator·startup interface | GPT-5.6 Sol / Extra High | ICF-04-05 |
| [ICF-04-07](../prompts/work_packages/ICF-04-07.md) | Semantic diff·metadata policy·rollback | GPT-5.6 Sol / Extra High | ICF-04-06 |
| [ICF-04-08](../prompts/work_packages/ICF-04-08.md) | 설계 lint·ERC preview·freeze gate | GPT-5.6 Sol / Extra High | ICF-04-07 |
| [ICF-04-09](../prompts/work_packages/ICF-04-09.md) | M2 schematic benchmark | GPT-5.6 Sol / Extra High | ICF-04-08 |

## [F05 — 초기 layout primitive와 DRC/LVS/PEX 검증기](../phases/F05.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-05-01](../prompts/work_packages/ICF-05-01.md) | Physical backend·license·deck probe | GPT-5.6 Sol / High | ICF-01-01 |
| [ICF-05-02](../prompts/work_packages/ICF-05-02.md) | Layout read·DBU·LPP·via inventory | GPT-5.6 Sol / High | ICF-05-01 |
| [ICF-05-03](../prompts/work_packages/ICF-05-03.md) | PCell·geometry·pin primitive | GPT-5.6 Sol / Extra High | ICF-05-02, ICF-04-03, ICF-01-07 |
| [ICF-05-04](../prompts/work_packages/ICF-05-04.md) | DRC lifecycle·false-clean oracle | GPT-5.6 Sol / High | ICF-05-03, ICF-01-09 |
| [ICF-05-05](../prompts/work_packages/ICF-05-05.md) | LVS lifecycle·connectivity oracle | GPT-5.6 Sol / High | ICF-05-04, ICF-04-04 |
| [ICF-05-06](../prompts/work_packages/ICF-05-06.md) | 작은 PEX·extracted representation 검증 | GPT-5.6 Sol / High | ICF-05-05 |
| [ICF-05-07](../prompts/work_packages/ICF-05-07.md) | Inverter end-to-end physical benchmark | GPT-5.6 Sol / Extra High | ICF-05-06, ICF-04-09, ICF-02-06 |

## [F06 — 회로 특성화·사양·topology·sizing 최적화](../phases/F06.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-06-01](../prompts/work_packages/ICF-06-01.md) | Spec·feasibility·평가자 contract | GPT-5.6 Terra / High | ICF-02-08, ICF-03-02, ICF-04-09 |
| [ICF-06-02](../prompts/work_packages/ICF-06-02.md) | 소자 characterization·gm/Id table | GPT-5.6 Sol / High | ICF-06-01 |
| [ICF-06-03](../prompts/work_packages/ICF-06-03.md) | Design intent·역할·topology templates | GPT-5.6 Terra / High | ICF-06-02 |
| [ICF-06-04](../prompts/work_packages/ICF-06-04.md) | 초기 sizing·headroom·bias feasibility | GPT-5.6 Sol / High | ICF-06-03 |
| [ICF-06-05](../prompts/work_packages/ICF-06-05.md) | Candidate revision·multi-objective optimizer | GPT-5.6 Sol / High | ICF-06-04 |
| [ICF-06-06](../prompts/work_packages/ICF-06-06.md) | 보상·noise·전원·common-mode closure | GPT-5.6 Sol / High | ICF-06-05 |
| [ICF-06-07](../prompts/work_packages/ICF-06-07.md) | PVT·통계·독립 holdout 검증 | GPT-5.6 Sol / High | ICF-06-06, ICF-03-05, ICF-03-06 |
| [ICF-06-08](../prompts/work_packages/ICF-06-08.md) | Amplifier schematic freeze·수동 기준 비교 | GPT-5.6 Sol / Extra High | ICF-06-07 |

## [F07 — Analog layout intelligence·제약 routing](../phases/F07.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-07-01](../prompts/work_packages/ICF-07-01.md) | Intent compiler·floorplan·preview | GPT-5.6 Terra / High | ICF-05-07, ICF-06-03 |
| [ICF-07-02](../prompts/work_packages/ICF-07-02.md) | Finger/fold·orientation·abutment | GPT-5.6 Sol / Extra High | ICF-07-01 |
| [ICF-07-03](../prompts/work_packages/ICF-07-03.md) | Matched pair·current mirror generator | GPT-5.6 Sol / Extra High | ICF-07-02 |
| [ICF-07-04](../prompts/work_packages/ICF-07-04.md) | Common centroid·interdigitation generator | GPT-5.6 Sol / Extra High | ICF-07-03 |
| [ICF-07-05](../prompts/work_packages/ICF-07-05.md) | Guard ring·substrate·well contacts | GPT-5.6 Sol / Extra High | ICF-07-04 |
| [ICF-07-06](../prompts/work_packages/ICF-07-06.md) | Net-aware·differential·power routing | GPT-5.6 Sol / Extra High | ICF-07-05 |
| [ICF-07-07](../prompts/work_packages/ICF-07-07.md) | Semantic layout diff·bounded repair | GPT-5.6 Sol / Extra High | ICF-07-06 |
| [ICF-07-08](../prompts/work_packages/ICF-07-08.md) | Fill·density·parasitic scoring | GPT-5.6 Sol / High | ICF-07-07 |
| [ICF-07-09](../prompts/work_packages/ICF-07-09.md) | Amplifier analog layout benchmark | GPT-5.6 Sol / Extra High | ICF-07-08, ICF-06-08 |

## [F08 — 정식 physical verification·PEX·post-layout closure](../phases/F08.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-08-01](../prompts/work_packages/ICF-08-01.md) | Hierarchical verification·violation mapping | GPT-5.6 Sol / High | ICF-05-07 |
| [ICF-08-02](../prompts/work_packages/ICF-08-02.md) | DRC 자동 수정·LVS 보존 | GPT-5.6 Sol / Extra High | ICF-08-01 |
| [ICF-08-03](../prompts/work_packages/ICF-08-03.md) | LVS mismatch 해결·ERC·reliability hooks | GPT-5.6 Sol / High | ICF-08-02 |
| [ICF-08-04](../prompts/work_packages/ICF-08-04.md) | PEX identity·artifact·config 검증 | GPT-5.6 Sol / High | ICF-08-03, ICF-07-09 |
| [ICF-08-05](../prompts/work_packages/ICF-08-05.md) | Pre/post 동일 계약 비교·hotspot | GPT-5.6 Sol / High | ICF-08-04 |
| [ICF-08-06](../prompts/work_packages/ICF-08-06.md) | Layout/sizing feedback closure | GPT-5.6 Sol / Extra High | ICF-08-05 |
| [ICF-08-07](../prompts/work_packages/ICF-08-07.md) | Post-layout PVT·MC·수치 검증 | GPT-5.6 Sol / High | ICF-08-06, ICF-03-06, ICF-06-07 |
| [ICF-08-08](../prompts/work_packages/ICF-08-08.md) | Signoff candidate freeze·M3 완주 | GPT-5.6 Sol / Extra High | ICF-08-07 |

## [F09 — ADC·AMS·digital control·RF 확장](../phases/F09.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-09-01](../prompts/work_packages/ICF-09-01.md) | Actual ADC contract·code interface | GPT-5.6 Terra / High | ICF-02-05, ICF-03-02, ICF-04-06 |
| [ICF-09-02](../prompts/work_packages/ICF-09-02.md) | Clock·reset·non-overlap·startup 모델 | GPT-5.6 Sol / High | ICF-09-01 |
| [ICF-09-03](../prompts/work_packages/ICF-09-03.md) | AMS/cosimulation backend | GPT-5.6 Sol / High | ICF-09-02 |
| [ICF-09-04](../prompts/work_packages/ICF-09-04.md) | FFT·dynamic ADC 측정 | GPT-5.6 Sol / High | ICF-09-03 |
| [ICF-09-05](../prompts/work_packages/ICF-09-05.md) | Static linearity·code statistics | GPT-5.6 Sol / High | ICF-09-04 |
| [ICF-09-06](../prompts/work_packages/ICF-09-06.md) | Digital/AMS verification와 physical 연계 | GPT-5.6 Sol / High | ICF-09-05 |
| [ICF-09-07](../prompts/work_packages/ICF-09-07.md) | RF/periodic analysis capability | GPT-5.6 Sol / High | ICF-09-06 |
| [ICF-09-08](../prompts/work_packages/ICF-09-08.md) | 선택 회로군 전체 benchmark | GPT-5.6 Sol / High | ICF-09-07 |

## [F10 — 공식 제작 PDK onboarding·MyChip 재타깃팅](../phases/F10.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-10-01](../prompts/work_packages/ICF-10-01.md) | 공식 PDK secure onboarding·tool 환경 | GPT-5.6 Sol / High | ICF-01-01, ICF-00-02 |
| [ICF-10-02](../prompts/work_packages/ICF-10-02.md) | Device/model/layer/deck/pad inventory | GPT-5.6 Sol / High | ICF-10-01 |
| [ICF-10-03](../prompts/work_packages/ICF-10-03.md) | Feasibility·supply·package 결정 | GPT-5.6 Terra / High | ICF-10-02 |
| [ICF-10-04](../prompts/work_packages/ICF-10-04.md) | Target characterization·re-sizing·bias | GPT-5.6 Sol / High | ICF-10-03, ICF-06-02 |
| [ICF-10-05](../prompts/work_packages/ICF-10-05.md) | Layout 재생성·target physical 검증 | GPT-5.6 Sol / Extra High | ICF-10-04, ICF-07-09, ICF-08-07 |
| [ICF-10-06](../prompts/work_packages/ICF-10-06.md) | Cross-PDK report·제작 후보 freeze | GPT-5.6 Sol / Extra High | ICF-10-05 |

## [F11 — Chip top·pad/package·최종 stream·제출 준비](../phases/F11.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-11-01](../prompts/work_packages/ICF-11-01.md) | Chip top·power domain·test interface | GPT-5.6 Terra / High | ICF-10-03 |
| [ICF-11-02](../prompts/work_packages/ICF-11-02.md) | Padframe·ESD·seal ring·boundary | GPT-5.6 Sol / Extra High | ICF-11-01, ICF-10-06 |
| [ICF-11-03](../prompts/work_packages/ICF-11-03.md) | Top power·sensitive routing·decoupling | GPT-5.6 Sol / Extra High | ICF-11-02 |
| [ICF-11-04](../prompts/work_packages/ICF-11-04.md) | Fill/density·final top verification | GPT-5.6 Sol / High | ICF-11-03 |
| [ICF-11-05](../prompts/work_packages/ICF-11-05.md) | Top PEX·package/board postlayout | GPT-5.6 Sol / High | ICF-11-04 |
| [ICF-11-06](../prompts/work_packages/ICF-11-06.md) | Stream-out·round-trip·최종 bytes 검증 | GPT-5.6 Sol / High | ICF-11-05 |
| [ICF-11-07](../prompts/work_packages/ICF-11-07.md) | Submission package·forms·checksums | GPT-5.6 Terra / High | ICF-11-06 |
| [ICF-11-08](../prompts/work_packages/ICF-11-08.md) | 독립 signoff·human approval·archive | GPT-5.6 Terra / High | ICF-11-07 |

## [F12 — End-to-end orchestrator·제한된 자율 설계](../phases/F12.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-12-01](../prompts/work_packages/ICF-12-01.md) | Task DAG·capability-aware planning | GPT-5.6 Terra / High | ICF-01-09 |
| [ICF-12-02](../prompts/work_packages/ICF-12-02.md) | Role contracts·least privilege·관찰 데이터 | GPT-5.6 Sol / Extra High | ICF-12-01 |
| [ICF-12-03](../prompts/work_packages/ICF-12-03.md) | Spec→candidate→layout cross-domain planning | GPT-5.6 Sol / High | ICF-12-02 |
| [ICF-12-04](../prompts/work_packages/ICF-12-04.md) | Recovery·operator handoff UX | GPT-5.6 Terra / High | ICF-12-03 |
| [ICF-12-05](../prompts/work_packages/ICF-12-05.md) | Independent reviewer·numeric oracle·eval | GPT-5.6 Terra / High | ICF-12-04 |
| [ICF-12-06](../prompts/work_packages/ICF-12-06.md) | GPDK end-to-end autonomous benchmark | GPT-5.6 Sol / High | ICF-12-05, ICF-08-08 |
| [ICF-12-07](../prompts/work_packages/ICF-12-07.md) | Target PDK submission-ready campaign | GPT-5.6 Sol / High | ICF-12-06, ICF-11-08 |

## [F13 — 실리콘 계측·PCB·sim-to-silicon feedback](../phases/F13.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-13-01](../prompts/work_packages/ICF-13-01.md) | Measurement spec·pin map·PCB 계획 | GPT-5.6 Terra / High | ICF-00-04 |
| [ICF-13-02](../prompts/work_packages/ICF-13-02.md) | Instrument adapter·interlock | GPT-5.6 Sol / Extra High | ICF-13-01 |
| [ICF-13-03](../prompts/work_packages/ICF-13-03.md) | Calibration·reference·uncertainty | GPT-5.6 Sol / Extra High | ICF-13-02 |
| [ICF-13-04](../prompts/work_packages/ICF-13-04.md) | Silicon characterization·safe sweeps | GPT-5.6 Sol / Extra High | ICF-13-03 |
| [ICF-13-05](../prompts/work_packages/ICF-13-05.md) | 데이터 ingestion·correlation | GPT-5.6 Terra / High | ICF-13-04 |
| [ICF-13-06](../prompts/work_packages/ICF-13-06.md) | 불일치 진단·재설계·학습 archive | GPT-5.6 Terra / High | ICF-13-05 |

## [F14 — 운영 확장·다중 환경·multi-project](../phases/F14.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-14-01](../prompts/work_packages/ICF-14-01.md) | Multi-project·multi-PDK registry | GPT-5.6 Sol / Extra High | ICF-01-09 |
| [ICF-14-02](../prompts/work_packages/ICF-14-02.md) | 새 EDA environment·backend 호환 | GPT-5.6 Sol / High | ICF-14-01 |
| [ICF-14-03](../prompts/work_packages/ICF-14-03.md) | Authenticated HTTP MCP·팀 권한 | GPT-5.6 Sol / Extra High | ICF-14-02 |
| [ICF-14-04](../prompts/work_packages/ICF-14-04.md) | Artifact store·quota·retention·restore | GPT-5.6 Sol / High | ICF-14-03 |
| [ICF-14-05](../prompts/work_packages/ICF-14-05.md) | Observability·license scheduling·usage | GPT-5.6 Sol / High | ICF-14-04 |
| [ICF-14-06](../prompts/work_packages/ICF-14-06.md) | Plugin SDK·policy compliance | GPT-5.6 Sol / Extra High | ICF-14-05 |

## [F15 — Release·문서·평가·포트폴리오 패키징](../phases/F15.md)

| ID | 작업 | Primary / effort | 선행 ID |
|---|---|---|---|
| [ICF-15-01](../prompts/work_packages/ICF-15-01.md) | Capability 문서·도구 목록 동기화 | GPT-5.6 Terra / High | ICF-00-06 |
| [ICF-15-02](../prompts/work_packages/ICF-15-02.md) | Regression·package·deployment rehearsal | GPT-5.6 Sol / High | ICF-15-01 |
| [ICF-15-03](../prompts/work_packages/ICF-15-03.md) | Benchmark·수치·failure report | GPT-5.6 Terra / High | ICF-15-02 |
| [ICF-15-04](../prompts/work_packages/ICF-15-04.md) | Release candidate·tag/publication gate | GPT-5.6 Terra / High | ICF-15-03 |
| [ICF-15-05](../prompts/work_packages/ICF-15-05.md) | 유지보수·next frontier·문서 백업 | GPT-5.6 Terra / High | ICF-15-04 |
