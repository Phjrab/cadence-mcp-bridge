# <실제 작업 ID> 결과 보고서

> template. 모든 <...>는 실제 관측으로 대체한다. 모르면 unknown/not_run이며 결과를 만들지 않는다.

## 상태

- Result: PASS | PARTIAL | BLOCKED | FAILED
- 실제 수행 작업/범위: <...>
- Implementation: <planned/implementing/code_verified/environment_blocked/real_verified>
- Integration: <not_pushed/pushed/review_pending/merged>
- Deployment validation: <not_run/failed/verified/not_applicable>
- Release status: <not_evaluated/blocked/candidate/published>
- 실제 모델 ID / reasoning effort: <... 또는 not_observable>
- 적용한 승인/정책 reference: <... 또는 없음>

## 변경과 근거

| 파일/산출물 | 실제 변경 | 요구사항/보강 ID | 증거 |
|---|---|---|---|
| <...> | <...> | <...> | <...> |

## 검증

| command/check | 환경 | PASS/FAIL/NOT_RUN | evidence/오류 |
|---|---|---|---|
| <...> | <local/mock/real> | <...> | <...> |

코드가 컴파일된 것, EDA process 성공, 유효한 measurement, 사양 충족, chip signoff를 분리해서 기록한다.

## 원격·데이터·보안 영향

- 실제 Cadence 실행 / job IDs: <없음 또는 정확한 값>
- 실제 설계 write: <없음 또는 exact target/operation>
- source/state/PDK 보호 evidence: <not_run 또는 실제 비교>
- first-write journal와 recovery evidence: <not_applicable 또는 ID>
- metadata side effects와 semantic diff: <...>
- 누락/불확실한 evidence: <...>
- native shell/SSH bypass 및 데이터 노출 점검: <...>
- 승인 범위 확대 제안 / 실제 적용: <제안과 실행 분리>

## Git 동기화

- Repository와 실제 visibility 확인 결과: <... 또는 unavailable>
- Feature branch / base commit: <...>
- Commit / push된 remote SHA: <...>
- Push verification: <PASS/FAIL/NOT_RUN>
- main 직접 push / force-push: <no 또는 정확한 예외 위반 보고>
- Merge/tag/release: <수행하지 않음 또는 별도 승인 reference>
- Unrelated local changes 보존: <...>
- Working tree: <clean/관련없는 변경 보존/기타>

현재 commit SHA를 자기 commit 파일에 반복 갱신하는 self-reference loop를 만들지 않는다. 최종 SHA는 이 보고서/독립 evidence에 기록한다.

## 남은 위험·사용자 조치

<찾을 수 있는 정보는 먼저 조사한다. 필요한 승인/credential/UI/공정 사양만 정확히 제시한다. 실패를 새 target 이름으로 우회하지 않는다.>

# NEXT RUN

- Next actual work ID: <현재 task 유지 또는 준비된 다음 task>
- 선행 조건/merge/승인 상태: <...>
- Recommended model: <현재 선택 가능한 exact ID 또는 확인 필요>
- Reasoning effort: <현재 지원 옵션>
- Fallback: <...>
- 이유: <한 문장>
- 자동 시작: **하지 않음**

## 복사용 다음 프롬프트

```text
현재 저장소 실행 계약과 PROJECT_STATE를 읽고 <정확한 task ID> 하나만 실행하라.
이전 branch의 반영과 선행 evidence 및 실제 승인 범위를 확인하라.
<이번 결과에서 다음 실행에 꼭 필요한 사실/차단/승인 reference>
해당 task 명세의 검증·기록·feature commit/push를 수행하고 NEXT RUN 출력 후 STOP하라.
```
