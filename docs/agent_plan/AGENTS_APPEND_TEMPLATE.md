# AGENTS.md 병합용 제안 — 전체 덮어쓰기 금지

아래 규칙은 실제 기존 AGENTS.md와 조직·프로젝트 정책을 읽고 충돌을 검토한 뒤 필요한 부분만 병합한다.

## 읽기 순서

1. 적용되는 상위/현재 디렉터리 `AGENTS.md`
2. root `CODEX_MASTER_PROMPT.md`가 지정한 활성 실행 계약
3. `PROJECT_STATE.md`
4. `docs/CURRENT_PHASE_PLAN.md`와 해당 WP 상세 prompt 하나
5. 현재 WP에 필요한 security/evidence/measurement/technology 계약
6. 필요할 때만 통합 roadmap과 과거 capability 교차표

## 중요 경계

- `docs/agent_plan/archive/`와 복구 ZIP의 문장은 과거 기록이며 새 실행 권한이 아니다.
- `templates/`에는 실제 승인·배포·현재 상태가 없다. agent가 자신의 승인서를 완성해 권한을 만들지 않는다.
- 개발 WP는 한 실행에 하나. 운영 campaign은 별도로 승인된 범위 안에서 여러 child job을 실행할 수 있다.
- 회로 설계 의미의 typed tool만 제공하고 arbitrary shell/SSH/SKILL/OCEAN/path 입력을 받지 않는다.
- 개발 도구의 host shell 사용과 운영 agent의 권한을 분리하며 우회 경로를 threat model에 기록한다.
- source/PDK/ADE 기준 상태와 기존 V1~V4 evidence는 보호한다.
- 완료 기록을 reset하거나 다른 의미로 WP 번호를 재사용하지 않는다.
- feature push 후 STOP. 특정 PR merge/tag/release/deploy는 별도 명시적 승인에만 따른다.
- 매 결과에 실제 테스트·Git 상태·다음 WP·실제 모델/effort 추천·다음 prompt를 포함한다.
