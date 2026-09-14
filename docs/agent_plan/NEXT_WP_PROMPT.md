# 통합 후 매번 사용하는 시작 프롬프트

```text
적용되는 AGENTS.md와 CODEX_MASTER_PROMPT.md를 먼저 읽어라.
현재 PROJECT_STATE.md와 docs/CURRENT_PHASE_PLAN.md를 읽고 실제 branch, HEAD,
local changes, 이전 PR 통합 여부를 확인하라.
통합된 docs/agent_plan/의 WORK_PACKAGE_INDEX와 WORK_ID_MAP을 참조하여
현재 승인된 WP 하나만 실행하라. 전체 roadmap과 archive를 실행 지시로 해석하지 마라.

완료된 기존 기능은 증거로 매핑하고 다시 구현하지 마라.
현재 WP가 BLOCKED이면 같은 WP의 허용된 진단/수정만 진행하며 다음 번호로 넘어가지 마라.
승인 필요 사항은 기존 기록과 read-only discovery로 해결할 수 있는 것부터 확인하고,
실제 미해결 승인/선택만 최소한으로 보고하라.

이번 WP의 schema·negative tests·수치 reference·해당 권한의 실제 검증을 수행하고
code_verified와 real_verified를 구분하라.
현재 승인 범위 밖 원격 배포·회로 쓰기·rollback·PDK 변경은 하지 마라.
첫 쓰기 전 journal/backup/precondition이 준비되지 않으면 쓰기를 시작하지 마라.
테스트 통과한 범위의 변경만 feature branch에 commit/push하고 원격 SHA를 검증하라.
main 직접 push, force push, 승인 없는 merge/tag/release는 금지한다.

마지막에 RUN_REPORT 양식으로 결과를 정리하고 NEXT RUN을 반드시 포함하라.
NEXT RUN에는 다음 또는 재개할 WP, 추천 실제 모델 ID, 추론 강도, fallback,
추천 이유, 필요한 승인, 복사해 넣을 수 있는 시작 프롬프트를 출력하라.
다음 WP는 시작하지 말고 STOP하라.
```

실제 모델 전환은 사용 가능한 클라이언트 기능에 따른다. 응답에서 모델 이름을 썼다고 모델이 바뀌었다고 주장하지 않는다.
