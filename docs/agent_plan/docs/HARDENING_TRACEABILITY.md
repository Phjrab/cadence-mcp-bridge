# 21개 재점검 보강 요구사항 추적

이 목록은 기존 review의 R01~R21을 통합 contract와 각 작업의 검증 기준으로 연결한다. feature count와 완료 상태가 아니라 보강 요구사항 추적표다.

| ID | 보강 요구 | 주요 작업 | 필수 검증 예 |
|---|---|---|---|
| R01 | 작업 ID와 authority 충돌 | `ICF-00-01`, `ICF-00-06` | 완료 이력 reset·중복 WP·재통합 시험 |
| R02 | 핵심 선행 기반 앞당김 | `ICF-01-01`, `ICF-01-03`, `ICF-01-04`, `ICF-05-01` | DAG 선행 누락과 unsupported capability 거부 |
| R03 | 실제 승인과 plan hash 분리 | `ICF-01-02`, `ICF-12-02` | self-approval·만료·다른 executor digest 거부 |
| R04 | 첫 쓰기 전 durable evidence | `ICF-01-03`, `ICF-01-07` | apply 직전/직후 crash·audit write 실패 |
| R05 | count/semantic/bytes/metadata 분리 | `ICF-01-06`, `ICF-04-07` | 개수 유지한 pin swap·W/L 변경 탐지 |
| R06 | 두 baseline provenance·1 V 유지 | `ICF-00-03`, `ICF-02-03` | 300m/370m 전역 치환과 VDD 확대 거부 |
| R07 | 실제 effective parameter 검증 | `ICF-02-02`, `ICF-02-03`, `ICF-03-02` | shadowed parameter와 request-only 변경 탐지 |
| R08 | 정밀 측정과 preview 분리 | `ICF-02-05`, `ICF-02-07`, `ICF-09-04` | decimation 기반 FFT/settling 오류 fixture |
| R09 | sweep 초기조건·방향 의미 | `ICF-03-01`, `ICF-03-04` | cold/warm/native 모드를 바꾼 cache 사용 거부 |
| R10 | gm/Id 실제 특성화 | `ICF-06-02`, `ICF-06-04` | table 범위 밖 외삽·다른 PDK table 재사용 거부 |
| R11 | CDF/PCell/netlist round-trip | `ICF-04-02`, `ICF-04-03`, `ICF-05-03`, `ICF-07-02` | W_total/finger/nf/m mismatch 탐지 |
| R12 | 초기 DRC/LVS oracle | `ICF-05-01`, `ICF-05-04`, `ICF-05-05` | clean/known-bad/empty/truncated 결과 matrix |
| R13 | 변경 영향·evidence 무효화 | `ICF-01-06`, `ICF-08-04`, `ICF-11-06` | 다른 revision/deck의 PASS 재사용 거부 |
| R14 | DUT/TB/top/package 경계 | `ICF-00-04`, `ICF-04-06`, `ICF-11-01` | ideal source를 fabrication core로 포함한 fixture |
| R15 | ADC/AMS/digital/RF 명시 | `ICF-09-01`, `ICF-09-03`, `ICF-09-06`, `ICF-09-07` | unsupported simulator/license를 다른 기능으로 위장 금지 |
| R16 | MCP 밖 우회 경로 통제 | `ICF-01-02`, `ICF-12-02`, `ICF-14-03` | host shell/key·approval store 접근 threat test |
| R17 | 필요한 설계 관찰과 기밀 균형 | `ICF-02-01`, `ICF-04-02`, `ICF-05-02` | 승인된 typed graph는 허용, raw model/secret 노출 거부 |
| R18 | 통계·holdout·수치 재현성 | `ICF-03-06`, `ICF-06-07`, `ICF-08-07` | seed 누락·MC 모델 미적용·optimizer 평가 계약 변경 거부 |
| R19 | 초기 백업·disk·time | `ICF-01-05`, `ICF-01-08`, `ICF-14-04` | disk-full·restore rehearsal·host/guest clock skew |
| R20 | 최종 stream bytes signoff | `ICF-11-06`, `ICF-11-08` | layer map/pin/hierarchy 변환·최종 hash 불일치 탐지 |
| R21 | capability·모델·상태 정직성 | `ICF-00-05`, `ICF-15-01`, `ICF-15-03` | 미실행/미지원/역사 자료를 verified로 승격 금지 |

machine-readable 연결은 `planning/hardening_requirements.json`에 있다. 실제 완료 판정에는 각 테스트의 command/result/evidence를 연결한다. 구현한 model이 자신이 생성한 문자열만 비교해 PASS하는 방식은 허용하지 않는다.
