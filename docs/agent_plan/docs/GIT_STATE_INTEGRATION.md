# Git·실행 상태·기존 계획 이관

## 1. 파일 분실과 프로젝트 초기화를 구별

프롬프트 파일이 없어졌다는 것은 구현 저장소와 Cadence 데이터가 없어졌다는 뜻이 아니다. 실제 repo가 있으면 해당 code/state를 기준으로 잃어버린 문서만 통합한다. 코드도 없으면 기존 remote/backup 복원을 조사하되 새 저장소를 같은 이름으로 임의 생성하지 않는다.

복구된 CODEX_MASTER_PROMPT는 초기 문서 버전이다. 이후 실제 repo에서 바뀐 merge policy·승인·작업 완료 이력을 덮어쓰면 안 된다. archive 원본을 되찾았다는 것과 최신 계약을 확보했다는 것은 별개다.

## 2. ID 전략

- `WP-00...`: 기존 개발 실행 이력. 변경하지 않는다.
- `P0-01...P12-11`: 원래 170 capability. 기능 범위 catalog로 보존.
- `R01...R21`: 최신 보강 요구사항.
- `ICF-00-01...`: 새 통합 작업 prompt ID. 계획안이며 실제 완료 상태가 아님.
- `PKG-INTEGRATE-01`: 문서 통합 전용. 이미 있으면 내용/hash/기록을 검사하여 무의미한 재실행을 막는다.

`WP-12`의 두 이름은 문자열만으로 매핑하지 않는다. 실제 title·branch·commit·결과로 resolve한다. matching capability를 이미 verified한 이력이 있으면 새 task를 중복 수행하지 않고 `covered_by_existing_evidence`로 연결하되 적용 revision/version을 확인한다.

## 3. 문서 위치

권장 live repo 구조:

```text
AGENTS.md                       # 실제 기존 내용을 유지하며 병합
CODEX_MASTER_PROMPT.md           # 활성 공통 계약과 더 강한 기존 제한 연결
PROJECT_STATE.md                 # 실제 기록을 보존하여 증분 갱신
 docs/CURRENT_PHASE_PLAN.md      # 현재 active WP 하나의 index
 docs/agent_plan/                # 이번 패키지의 통합 문서
   CODEX_MASTER_PROMPT.md
   docs/...                     # 패키지 내부 상대 경로 유지
   prompts/work_packages/...
   planning/...
```

원하는 repo 구조가 다르면 상대 링크와 file validator를 함께 조정한다. 경로 이동은 문서 통합에서만 하고 source/runner layout까지 구조 개편하지 않는다.

## 4. 상태 축

```yaml
observed_repo_head: null
active_wp: null
implementation_status: unknown
integration_status: unknown
deployment_status: unknown
release_status: unknown
last_verified_evidence: null
```

위는 예시다. 실제 파일에 그대로 넣어 기존 known 값을 지우지 않는다. nullable unknown은 재조사가 필요하다는 뜻이다.

작업 완료 후 자기 자신을 pending으로 두지 않는다. feature pushed/review_pending와 real_verified를 분리한다. 다음 WP candidate를 적을 수 있지만 predecessor merge/approval 전에는 active로 실행하지 않는다. state가 missing이면 복구·조정 작업부터이며 WP-00 bootstrap을 자동 시작하지 않는다.

## 5. Checkpoint policy

실제 head와 current branch를 확인한 뒤 같은 WP를 계속하거나 최신 승인 main에서 branch를 만든다. unrelated changes를 stash/reset/clean하지 않는다. 충돌할 경우 안전한 read-only 계획 또는 별도 승인 worktree를 이용한다.

허용된 파일 목록만 stage하고 tests를 수행한 뒤 conventional commit. 불완전하나 안전한 local docs/tests는 PARTIAL로 checkpoint할 수 있다. 실패 테스트를 PASS로 표시하지 않는다.

Push 성공은 remote ref SHA로 확인한다. log 문구만으로 주장하지 않는다. main 직접 push/force push는 금지하고 PR별 explicit merge 승인 필요. deploy/tag/release는 각각 독립 승인을 요구한다.

## 6. 문서와 raw bytes

승인 plan과 역사 checksum을 재format하지 않는다. CRLF/LF·Unicode normalization·JSON ordering이 raw digest를 바꿀 수 있으므로 변환 전후 identity를 구분한다. canonical plan digest를 사용할 때 schema/version/정규화 알고리즘을 명시한다.

최종 commit SHA를 그 commit의 파일 안에 써 넣으려 반복 커밋하지 않는다. base SHA/evidence timestamp를 파일에, 새 commit SHA를 최종 보고에 기록한다.

## 7. 문서 유효 범위

패키지 integrity manifest는 배포받은 문서 묶음의 동일성을 확인한다. 살아 있는 프로젝트가 문서를 정상 수정한 뒤 manifest를 자동 덮어써 검증을 회피하면 안 된다. 새 문서 패키지 릴리스를 만들 때만 변경된 목록·검토와 함께 새 manifest를 생성한다.

기존 master와 새 정책의 충돌은 INTEGRATION_DECISIONS로 기록하고 더 넓은 권한이 필요한 부분은 proposed 상태로 남긴다. 설계 기능의 gate를 완화하는 문서 변경도 실제 정책 변경 승인과 구분한다.
