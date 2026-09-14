# 시스템 아키텍처와 공통 데이터 계약

## 1. 계층

```text
사용자 spec / 운영자 승인
       ↓
설계 planner·수치 optimizer·독립 evaluator
       ↓
project policy + revision DAG + budget + approval validator
       ↓
typed MCP API
       ↓
CadenceService / durable campaign engine
       ↓
fixed SSH transport / environment adapter
       ↓
reviewed runner + SKILL/OCEAN/Spectre/physical adapters
       ↓
protected artifacts + exact measurement + evidence ledger
```

미래에 MCP 전송이나 모델이 바뀌어도 domain service·권한·artifact·검증을 재사용한다. 범용성은 임의 코드 실행이 아니라 검증된 semantic operation 확장으로 확보한다.

## 2. 식별자

| ID | 의미 |
|---|---|
| package_version | 이 문서 패키지 버전; software version과 다름 |
| capability_id | 원래 P0-01 등 기능 범위; 완료 상태를 의미하지 않음 |
| work_package_id | 이번 개발 task. ICF-xx-yy와 기존 WP를 매핑 |
| project_id / workspace_id | 권한과 데이터 경계 |
| revision_id / parent_id | immutable 설계 계보와 후보 |
| profile_id / contract_version | 허용 실행·측정 정의 |
| campaign_id / job_id | 실험 묶음과 한 실행 |
| plan_digest / executor_digest | 승인 내용과 실행 코드의 identity |
| artifact_id / content_digest | 경로 아닌 결과 객체 identity |
| approval_id / principal_id | 운영자가 발급한 승인과 실행 주체 |

DB pointer, window:3, stdobj@주소, PID는 영속 설계 ID가 아니다. runtime locator에는 session/boot/epoch를 결부하고 외부 logical reference와 분리한다.

## 3. 기술 어댑터 최소 계약

기술 어댑터는 source-controlled 공통 schema와 로컬 보호 config로 나눈다. PDK 원문은 패키지나 공개 Git에 넣지 않는다.

필수: PDK identity/version/hash/문서 revision, supported OS/tool/solver, logical device master/model/pin order/body, CDF·simulation·PCell parameters/types/units/W_total/finger/m/nf, legal orientations, DBU/grid/LPP/vias, model·statistics·RC corners, fixed runset/deck identity, pad/IO/stream map, data policy.

`located`, `functional_verified`, `unsupported`, `license_unavailable`, `unknown`를 분리한다. 한 PDK에서 성공한 schema가 다른 PDK에서도 같은 device semantics라고 가정하지 않는다.

## 4. Specification contract

사양에는 metric name만이 아니라 input/output type, VDD/VCM, load, frequency/time domain, feedback/probe, startup/reset, operating region, noise band, temperature/PVT, stress limits, relevant package/pin constraints, tolerance, applicability가 필요하다.

- 목적과 hard constraint를 구분한다.
- 숫자/unit은 canonical SI 값과 원래 표현을 연결한다.
- 사양이 불가능하거나 모순이면 제안으로 보고하고 몰래 완화하지 않는다.
- current 1 V 연구와 target PDK의 feasibility를 분리한다.
- spec/measurement/evaluator는 optimizer의 mutation 대상이 아니다.

## 5. 입력 값·단위·범위

decimal string 또는 정해진 finite numeric representation을 versioned schema로 사용한다. UI 단위는 SI로 검증 후 변환한다. boolean-as-number, NaN/Inf, overflow, exponent edge cases, negative zero, duplicate keys, 개행, NUL 등을 검사한다.

Spectre suffix와 전기 단위를 혼동하지 않는다. 변수가 쓰인 exact property와 hierarchy를 통해 unit/binding을 확인한다. m·nf·W 정의는 device별 schema에 따른다.

이름은 syntactic validation뿐 아니라 registry·ownership·revision scope도 확인한다. source 이름이 case-sensitive면 자동 lowercase/normalization으로 바꾸지 않는다.

## 6. 요청·실행·관측 분리

```text
requested_parameters
rendered_parameters
simulator_effective_parameters
observed_metrics
```

모든 값이 같아야 하는 항목과 변환되는 항목을 계약으로 명시한다. manifest requested value를 effective value의 증거로 쓰지 않는다. 각 parameter 변경이 큰 출력 변화를 반드시 만들어야 한다고도 강제하지 않는다. known analytic fixture로 binding을 검증하고 실제 효과는 물리적으로 해석한다.

## 7. Result contract

execution success ≠ measurement valid ≠ spec pass ≠ physical signoff ≠ submission ready.

결과에는 status, validity reason, units, input/revision/profile/tool/model/deck/measurement digests, warnings policy, numerical tolerance, sampling, runtime/queue time, missing/truncated fields, artifact metadata가 필요하다.

unsupported는 0이 아니다. N/A는 해당 spec에서 제외 가능한 근거와 승인된 applicability가 있을 때만 쓴다. 필수 항목 unavailable은 제출 gate를 막는다.

## 8. Evidence dependency graph

```text
source + TB + state + includes + model + profile
  → generated netlist → simulation → extraction/measurement
schematic + layout + LVS deck → LVS
layout + DRC deck → DRC
layout + extraction config + RC model → PEX
PEX + TB + measurement contract → postlayout
final layout + stream map → final GDS
final GDS + official signoff flow → submission evidence
```

조합이 달라지면 cached PASS의 현행 유효성이 사라진다. input hash가 동일해도 initial condition·seed·measurement version이 다르면 같은 실험이 아니다.

## 9. Schematic interface와 layout intent

DUT/TB/chip top/package/board는 별도 객체로 관리한다. inst master, exact params, net incidence, ports, hierarchy, bulk domains를 structured graph로 표현한다. connectivity lint는 실제 LVS를 대체하지 않지만 known-bad 연결을 일찍 잡는다.

Layout intent는 matching group·ratio·symmetry axis·orientation·dummies·critical nets·guard rings·domain·area·coupling constraints다. 같은 길이/centroid만으로 성능 보증하지 않고 PEX/postlayout로 feedback한다.

## 10. API 확장 규칙

기존 도구와 profile behavior는 versioned compatibility로 유지한다. 새 도구 names는 카탈로그 제안이며 implemented가 아니다. runner/API/client contract version compatibility를 handshake에서 확인한다.

public MCP는 arbitrary source string을 받지 않는다. 내부 fixed SKILL/OCEAN template 수정은 코드 review/deploy digest 대상이다. table-driven typed mutations를 추가할 수 있으나 허용 op·object kind·schema·PDK·scope 제한을 없애지 않는다.

## 11. 작업 예산과 자율성

모든 campaign은 proposed/readiness 상태에서 points·runs·attempts·queue/runtime·disk·parallelism·iteration을 계산한다. plan-bound 또는 승인 envelope-bound가 확인돼야 실행한다. 서버가 전체 예산을 강제하고 agent가 child별 나누기로 우회할 수 없게 한다.

개발 one-WP-per-run 규칙은 문서/코드 변경 단위다. 운영자는 한 승인된 campaign에서 수십 child job을 자동 진행할 수 있도록 별도 정책을 설계한다.
