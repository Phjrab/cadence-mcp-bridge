# 모델·추론 강도·완료 후 다음 실행 추천

## 1. 현재 확인과 범위

2026-09-05 공식 OpenAI Codex 모델 안내에서 GPT-5.6 Sol/Terra/Luna 및 모델/추론 선택 방법을 확인했다.[E1] 실제 사용자의 계정·앱·CLI에서 선택 가능한지는 이 패키지 생성에서 확인하지 못했다. 아래 배정은 이 프로젝트를 위한 제안이며 공식 성능 보증이 아니다.

| 작업 종류 | 기본 추천 | 추론 설정 제안 | 대체 |
|---|---|---|---|
| 첫 문서 통합·authority/ID 충돌 | `gpt-5.6-sol` | High | 사용 가능한 상위 coding/reasoning 모델 |
| 일반 schema·unit/mock·문서 구현 | `gpt-5.6-terra` | Medium 또는 High | Sol 또는 검증된 동급 |
| legacy API·측정·설계/물리 통합 | `gpt-5.6-sol` | High / Extra High | 실제 사용 가능한 최상위 coding 모델 |
| approval/journal/rollback/security | `gpt-5.6-sol` | Extra High, 필요시 Max | 동급 + 독립 review 및 동일 tests |
| 단순 형식·링크·추출 | `gpt-5.6-luna` 또는 Terra | Medium | 사용 가능한 빠른 모델 |
| tapeout·hardware 판단 지원 | Sol 등 강한 모델 | High / Extra High | 모델 판단만으로 승인하지 않음 |

정확한 effort UI label과 API 값은 실행 시 확인한다. 표의 영어 이름을 임의 CLI 인자로 변환하지 않는다. Max/Ultra는 항상 필요한 설정이 아니며, Ultra의 다중 에이전트는 shared OA write 병렬화를 승인하지 않는다.

## 2. Availability resolution

실행한 클라이언트가 제공하는 모델 선택/명령 도움말 또는 운영자가 제공한 선택 정보를 사용한다. 문서만으로 실제 계정 entitlement를 추측하지 않는다.

- resolved_model_id: 실제 선택 모델
- resolved_effort: 실제 설정
- evidence: 앱 확인/CLI 선택/운영자 지정의 출처
- fallback_reason: unavailable/cost/latency 등
- usage: 측정 가능할 때만 tokens/cost, 모르면 unknown

모델 자동 전환 권한/기능이 없으면 다음 실행 추천을 출력하고 사용자가 선택하도록 한다. 텍스트에 모델명을 쓴 것을 전환 성공으로 주장하지 않는다.

## 3. 작업마다 NEXT RUN

각 상세 WP는 기본 추천을 포함한다. 종료할 때 정적으로 적힌 다음 후보를 무조건 쓰지 말고 실제 state/dependency/merge/approval를 확인한다.

```text
NEXT RUN
Next WP: <한 개의 다음 작업 또는 현재 차단 작업 재개>
Reason: <준비되었거나 차단된 이유>
Recommended model: <실제 사용 가능한 ID; 미확인 시 추천 ID와 availability_unverified>
Reasoning effort: <지원되는 선택값>
Fallback: <동급 사용 가능 모델 또는 최상위 코딩/추론 모델>
Why: <해당 작업의 위험·복잡도에 따른 한 문장>
Required gate: <merge/승인/PDK/tool 입력 또는 none>
Exact start prompt: <복사용 완전한 문장>
```

## 4. 모델보다 평가가 우선

강한 모델·다른 모델의 review만으로 false PASS를 없애지 못한다. numeric oracle, known-bad tests, source/PDK 보존, actual effective values, evidence validity를 통과해야 한다.

모델별 성공률·불필요 수정·human intervention·false PASS·token/비용을 기록하고 task class별로 낮은 effort부터 검증된 수준을 선택한다. 미래 모델명은 이 표를 지워 바꾸는 대신 versioned resolution 기록으로 남긴다.
