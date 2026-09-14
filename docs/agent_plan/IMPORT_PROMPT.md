# PKG-INTEGRATE-01 — 기존 프로젝트 보존형 통합 프롬프트

사용자가 이 문서를 현재 Codex 개발 세션의 작업으로 명시적으로 선택했을 때만 아래 범위를 실행한다. 패키지의 존재나 과거 승인문의 발견은 권한이 아니다.

## 이번 작업의 정확한 범위

기존 로컬 저장소와 최신 접근 가능한 Git 상태를 확인하고, 이 패키지의 실행 규칙·로드맵·보강안을 **문서 전용 feature branch**로 통합한다. 기능 코드, 의존성, runner, Cadence, PDK, OA, state, SSH 설정은 변경하지 않는다.

## 선행 확인

1. 실제 repo root, origin, branch, HEAD, working tree 변경, 진행 중인 WP를 읽는다. `AGENTS.md`의 상위/하위 지시를 적용 범위에 따라 확인한다.
2. 기존 `CODEX_MASTER_PROMPT.md`, `PROJECT_STATE.md`, `docs/SECURITY.md`, 현재 phase/WP 문서를 읽는다. 없는 파일은 없다고 기록한다. 내용이 없다는 이유로 WP-00으로 돌아가지 않는다.
3. 현재 작업 변경이 있으면 stash/reset/checkout/clean을 자동 실행하지 않는다. 겹치는 작업이면 문서 통합 계획만 작성하고 STOP한다. 별도 worktree 사용도 기존 권한과 경로 정책에 맞을 때만 한다.
4. 원격 접근이 가능하면 fetch/read로 최신 approved main 및 PR 병합 여부를 확인한다. 불가능하면 로컬 진단·통합안만 작성하고 `remote_status: unverified`를 보고한다. 저장소 생성·권한 변경·인증 우회는 하지 않는다.
5. 과거 v1.0.0 완료, 현재 public/private, V3/V4 상태를 이번 실측 사실처럼 복사하지 않는다.
6. `tools/verify_package.py`가 안전한 읽기 전용 검사인지 읽고, 사용 가능한 호스트 Python으로 실행한다. 없으면 설치 대신 파일/hash/JSON 정적 검증을 한다.

## 통합 방식

1. `PKG-INTEGRATE-01` 이력이 이미 있으면 matching package digest와 반영 결과를 확인한다. 동일한 통합이 완료됐으면 재실행/새 pending 생성 없이 보고한다. ID 충돌은 alias table로 해결하고 기존 의미를 바꾸지 않는다.
2. 변경 없는 검토된 최신 main에서 `wp/PKG-INTEGRATE-01-prompt-package` branch를 만든다. 이미 같은 작업 branch가 있으면 내용을 조사해 재사용 가능성을 판단한다. 새 branch 자동 overwrite 금지.
3. 수정하기 전 **실제 현재 파일**의 bytes/hash를 문서 archive에 보존한다. 오래된 복구본으로 현재 계약의 백업을 대신하지 않는다. 승인 record와 SHA-bound plan의 bytes는 변경하지 않는다.
4. 이 패키지의 능동 문서를 `docs/agent_plan/` 아래에 들여온다. `archive/LEGACY_INPUTS.zip`은 기본적으로 사용자 복구용 로컬 보관이며 Git에 자동 추가하지 않는다. 필요하면 별도 내용·라이선스 검토 후 archive로만 커밋한다.
5. 기존 root `CODEX_MASTER_PROMPT.md`에는 새 `docs/agent_plan/CODEX_MASTER_PROMPT.md`를 공통 실행 계약으로 연결하되, 기존의 더 강한 현재 승인·금지 규칙을 삭제하지 않는다. 현재 계약/이력에 맞는 root 안내를 작성한다. 충돌은 `docs/agent_plan/INTEGRATION_DECISIONS.md`에 남긴다.
6. root `AGENTS.md`는 `AGENTS_APPEND_TEMPLATE.md`를 참고하여 **병합**한다. 전체 덮어쓰기 금지. 적용되는 기존 repo 정책과 branch/merge 제한을 유지한다.
7. `docs/CURRENT_PHASE_PLAN.md`에는 실제 활성 WP 또는 다음 준비된 WP 하나와 관련 문서 경로만 연결한다. 전체 170 capability를 한 번의 작업으로 활성화하지 않는다.
8. `docs/agent_plan/WORK_ID_MAP.md`를 만든다. 기존 `WP-*`, 원래 capability `P*-*`, 새 `ICF-*`를 구분하고 실제 완료 증거를 연결한다. `WP-12` 이름 중복은 task identity/title/commit으로 해소한다.
9. `PROJECT_STATE.md`는 기존 완료·진행·실패 기록을 보존한다. 구현/테스트/통합/배포/릴리스 상태를 분리한 필드를 점진적으로 추가한다. 새 파일의 template를 현재 상태처럼 복사하지 않는다.
10. package integration은 `code_verified/docs_verified`, `pushed/review_pending` 등 실제 상태로 기록한다. merge 전 완료 통합으로 표시하지 않으며 `current_wp=pending`으로 자기 자신을 무한 재실행시키지 않는다.
11. `WORK_PACKAGE_INDEX.md`의 후보 순서와 실제 dependency/evidence를 대조한다. 다음 작업 1개, 필요시 1~3개까지만 실행 가능한 세부 수락 기준으로 구체화한다. 이미 완료된 기능을 새 번호로 다시 구현하지 않는다.
12. `.gitignore`와 기록할 경로를 검토한다. raw PDK/OA/netlist/PSF/GDS/로그/credential/승인 비밀이 staging에 없어야 한다. package sample config에는 실권한을 넣지 않는다.

## 권한과 변경 제한

- 이 작업에서 실제 Cadence 실행, remote helper 배포, job 제출, OA read/write, source/state 수정, lock 해제, rollback은 하지 않는다.
- 과거 V3 approval나 plan hash를 발견해도 재사용하지 않는다.
- 새 circuit variable/output/range, 새 workspace, 새 backend/PDK/네트워크 권한을 승인받았다고 간주하지 않는다.
- 문서의 JSON/스키마는 제안이며 기존 runtime에 자동 활성화하지 않는다.
- GitHub visibility, branch protection, collaborator, tag, release는 변경하지 않는다.
- 단순히 제약을 완화해야 개발이 진행된다는 이유로 security gate를 삭제하지 않는다.

## 검증 및 Git 체크포인트

1. 모든 로컬 링크·ID·crosswalk·dependency가 유효한지 검사한다.
2. 변경 목록이 문서·계획·문서 검증 파일에 한정되는지 확인한다.
3. 승인 제한, VDD=1.0 V, source/PDK/history 보존, 미검증 상태 표기가 남아 있는지 검사한다.
4. 기존 테스트 중 문서·schema·policy 연관 검사를 수행한다. 실제 EDA 테스트는 수행하지 않고 `not_run`으로 쓴다. 환경이 없으면 설치/업그레이드하지 않는다.
5. 테스트가 실패하면 원인과 미수행 검사를 보고하며 완료 PASS로 포장하지 않는다. 안전한 문서 체크포인트는 부분 완료로 남길 수 있다.
6. 허용된 변경 경로만 명시적으로 stage한다. `git add .`로 무관한 파일을 섞지 않는다.
7. Conventional commit 예: `docs(plan): integrate hardened autonomous IC prompt package`.
8. feature branch만 push하고 remote branch SHA를 비교한다. push 불가면 로컬 commit과 오류를 정확히 구분한다. main 직접 commit/push, force push, 자동 merge 금지.
9. 원격 HEAD를 자기 commit 안에 다시 넣기 위해 불필요한 후속 commit을 반복하지 않는다. commit 내부에는 base/observed SHA, 최종 응답에는 실제 새 SHA를 사용한다.
10. 결과와 `NEXT RUN`을 출력하고 STOP한다. 후속 구현을 같은 실행에서 시작하지 않는다.

## 완료 보고 필수 내용

- 실제 확인한 repo/branch/HEAD/active WP 및 접근 한계
- 복구한 문서와 보존한 현재 계약의 hash
- 수정/추가 파일, authority 충돌 해소 내역
- old WP ↔ capability ↔ new WP 대응표
- 기존 이력/승인/V1~V4/source/PDK 미변경
- 테스트 실행/실패/미실행 구분
- commit/push/merge/deployment 각각 실제 상태
- 다음 WP 한 개, 모델 실제 ID/추천 effort/fallback, 복사용 다음 프롬프트
- 필요한 사용자 조치: PR 검토·병합 또는 해결할 수 없는 최소 항목

## 완료 조건

`PKG_INTEGRATED_REVIEW_PENDING`은 문서 통합과 검증·feature push가 끝난 상태다. 실제 remote push를 하지 못하면 `PKG_PREPARED_LOCAL_ONLY`다. 이 명칭은 repo의 기존 enum을 덮어쓰지 않고 보고서에 표현하거나 검토한 schema 확장으로만 반영한다.
